"""Build the desktop plugin and its matching Runtime without a Host or user home."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tarfile


VERSION = "0.1.0-rc.37-test.10"
HOST_VERSION = "0.2.2-rc.1"
POLICY = "dsh_runtime/resources/selection_policy/selection-v2.json"
ASSETS = (
    "cordis.patch.yml",
    "EVIDENCE_RELOCATION_DESIGN.md",
    "DEPENDENCY_SECURITY_RC31.md",
    "HOST_COMPATIBILITY_GATE.md",
    "SUPPORTED_HOSTS.md",
    "ACTIVITY_HISTORY_CONTRACT.txt",
    "scripts/cli-login.py",
    "scripts/migrate-legacy-home.mjs",
    "scripts/copy-terminal-evidence.mjs",
)


class BuildError(Exception):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_bytes(root: Path, path: Path) -> bytes:
    """Read only regular, link-free text inputs below the selected source root."""
    part = root
    for name in path.relative_to(root).parts:
        part /= name
        if part.is_symlink() or part.is_junction():
            raise BuildError("Linked source input is not supported")
    if not stat.S_ISREG(path.stat().st_mode):
        raise BuildError("Source input is not a regular file")
    data = path.read_bytes()
    data.decode("utf-8")
    return data.replace(b"\r\n", b"\n")


def tree_files(root: Path, suffix: str) -> list[Path]:
    result = []
    for base, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(name for name in dirs if name != "__pycache__")
        for name in dirs:
            path = Path(base) / name
            if path.is_symlink() or path.is_junction():
                raise BuildError("Linked source directory is not supported")
        result.extend(Path(base) / name for name in sorted(files) if name.endswith(suffix))
    return sorted(result)


def runtime_inputs(repo: Path) -> list[Path]:
    paths = tree_files(repo / "dsh_runtime", ".py") + [repo / POLICY]
    if not paths or not (repo / "dsh_runtime/observability/activity.py").is_file():
        raise BuildError("The matching activity Runtime source is required")
    for path in paths:
        source_bytes(repo, path)
    return sorted(paths)


def desktop_manifest(source: dict) -> dict:
    manifest = json.loads(json.dumps(source))
    manifest["version"] = VERSION
    manifest.setdefault("engines", {})["dsh"] = HOST_VERSION
    manifest["peerDependencies"] = {
        "@deepseek-ai/dsh-brand": HOST_VERSION,
        "@deepseek-ai/dsh-subagent": HOST_VERSION,
        "@deepseek-ai/dsh-subprocess": HOST_VERSION,
        "@deepseek-ai/dsh-tools": HOST_VERSION,
        "@deepseek-ai/schemastery": "3.19.0",
    }
    manifest["dsh"]["client"]["inject"] = [
        "@deepseek-ai/dsh-client-ui-plugin-manager",
        "@deepseek-ai/dsh-client-ui-settings",
    ]
    manifest["dependencies"] = {"zod": manifest["dependencies"]["zod"]}
    manifest["files"] = ["lib", *ASSETS]
    manifest.pop("devDependencies", None)
    manifest.pop("scripts", None)
    return manifest


def write_archive(target: Path, entries: dict[str, bytes], executables=()) -> None:
    """Fixed headers and LF payloads; never archive filesystem/home metadata."""
    with target.open("xb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as zipped:
            with tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for name, data in sorted(entries.items()):
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    info.mode = 0o755 if name in executables else 0o644
                    info.mtime = info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    archive.addfile(info, io.BytesIO(data))


def reserve_output(repo: Path, output: Path) -> Path:
    # Fail before touching anything if an output or a symlink already exists.
    if output.exists() or output.is_symlink() or output.is_junction():
        raise BuildError("Output must be a new, nonexistent directory")
    output = output.parent.resolve(strict=True) / output.name
    if output.is_relative_to(repo):
        raise BuildError("Output must be outside the source checkout")
    output.mkdir()  # Exclusive; preserve partial output on failure, never clean old files.
    return output


def build(repo: Path, output: Path, node: str) -> dict:
    repo = repo.resolve(strict=True)
    plugin = repo / "integrations/deepseek-harness"
    manifest_path = plugin / "package.json"
    manifest = json.loads(source_bytes(repo, manifest_path))
    compiler = plugin / "node_modules/typescript/bin/tsc"
    compiler_manifest = compiler.parent.parent / "package.json"
    if not compiler.is_file():
        raise BuildError("Install the frozen plugin dependencies first")
    typescript = json.loads(compiler_manifest.read_text(encoding="utf-8"))["version"]
    if typescript != manifest["devDependencies"]["typescript"]:
        raise BuildError("Installed TypeScript does not match package.json")
    version = subprocess.run([node, "--version"], capture_output=True, check=True,
                             text=True, timeout=10).stdout.strip()
    numbers = tuple(int(p) for p in version.removeprefix("v").split(".")[:3])
    if numbers < (24, 19, 0):
        raise BuildError("Node.js >=24.19.0 is required")
    runtime = runtime_inputs(repo)
    inputs = set(runtime + tree_files(plugin / "src", ".ts"))
    inputs.update(plugin / name for name in (
        *ASSETS, "src/client.js", "package.json", "pnpm-lock.yaml",
        "pnpm-workspace.yaml", "tsconfig.json", "tsconfig.build.json",
    ))
    inputs.add(repo / "scripts/build_desktop_baseline.py")
    source_hashes = {p.relative_to(repo).as_posix(): digest(source_bytes(repo, p))
                     for p in sorted(inputs)}
    output = reserve_output(repo, output)
    stage = output / "plugin-stage/package"
    lib = stage / "lib"
    lib.mkdir(parents=True)
    completed = subprocess.run([
        node, str(compiler), "-p", str(plugin / "tsconfig.build.json"),
        "--outDir", str(lib), "--newLine", "lf",
    ], cwd=plugin, capture_output=True, timeout=120)
    if completed.returncode:
        raise BuildError("TypeScript compilation failed; partial output retained")
    for name in ASSETS:
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source_bytes(repo, plugin / name))
    (lib / "client.js").write_bytes(source_bytes(repo, plugin / "src/client.js"))
    staged_manifest = desktop_manifest(manifest)
    (stage / "package.json").write_text(
        json.dumps(staged_manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    plugin_entries = {"package/" + p.relative_to(stage).as_posix(): source_bytes(output, p)
                      for p in sorted(stage.rglob("*")) if p.is_file()}
    runtime_entries = {}
    for path in runtime:
        name = path.relative_to(repo).as_posix()
        data = source_bytes(repo, path)
        target = output / "runtime-source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        runtime_entries[name] = data
    # Guard against a concurrent edit while the compiler was running.
    if any(digest(source_bytes(repo, repo / name)) != expected
           for name, expected in source_hashes.items()):
        raise BuildError("Source changed during build; partial output retained")
    plugin_archive = output / f"dsh-runtime-harness-plugin-{VERSION}.tgz"
    runtime_archive = output / f"dsh-runtime-source-{VERSION}.tar.gz"
    executable_names = {"package/" + name.removeprefix("./")
                        for name in staged_manifest["bin"].values()}
    executable_names.add("package/scripts/cli-login.py")
    write_archive(plugin_archive, plugin_entries, executable_names)
    write_archive(runtime_archive, runtime_entries)
    source_json = json.dumps(source_hashes, sort_keys=True, separators=(",", ":")).encode()
    result = {
        "schemaVersion": 1, "version": VERSION, "desktopHost": HOST_VERSION,
        "toolchain": {"node": version, "typescript": typescript, "python": sys.version.split()[0]},
        "textPolicy": "UTF-8; CRLF normalized to LF; archive headers fixed",
        "sourceTreeSha256": digest(source_json), "sourceFiles": source_hashes,
        "plugin": {"filename": plugin_archive.name, "sha256": digest(plugin_archive.read_bytes()),
                   "files": {n: digest(b) for n, b in sorted(plugin_entries.items())}},
        "runtime": {"filename": runtime_archive.name, "sha256": digest(runtime_archive.read_bytes()),
                    "directory": "runtime-source", "files": {n: digest(b) for n, b in sorted(runtime_entries.items())}},
        "historicalTest10ByteIdentityClaimed": False,
    }
    (output / "build-manifest.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="New output directory outside the source checkout")
    args = parser.parse_args()
    node = shutil.which("node")
    if not node:
        parser.error("Node.js is required")
    try:
        result = build(Path(__file__).resolve().parents[1], args.output, node)
    except (BuildError, OSError, ValueError, subprocess.SubprocessError):
        print("Baseline build failed; existing source/home untouched, partial output retained.", file=sys.stderr)
        return 1
    print(json.dumps({"version": VERSION, "plugin": result["plugin"]["sha256"],
                      "runtime": result["runtime"]["sha256"],
                      "sourceTreeSha256": result["sourceTreeSha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
