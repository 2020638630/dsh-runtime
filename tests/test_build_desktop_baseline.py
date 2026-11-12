"""Keyless packaging boundaries; no Host, CLI executor, login or model is started."""

import importlib.util
from pathlib import Path
import tarfile

import pytest


spec = importlib.util.spec_from_file_location(
    "desktop_baseline_build", Path(__file__).parents[1] / "scripts/build_desktop_baseline.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def runtime_fixture(root):
    activity = root / "dsh_runtime/observability/activity.py"
    activity.parent.mkdir(parents=True)
    activity.write_bytes(b"# fixture\r\n")
    policy = root / builder.POLICY
    policy.parent.mkdir(parents=True)
    policy.write_bytes(b"{}\r\n")
    return activity


def test_runtime_payload_excludes_credentials_caches_and_other_json(tmp_path):
    activity = runtime_fixture(tmp_path)
    runtime = tmp_path / "dsh_runtime"
    for name in ("auth.json", ".credentials.yaml", ".env", "connections.json"):
        (runtime / name).write_text("PRIVATE FIXTURE", encoding="utf-8")
    cache = runtime / "__pycache__"
    cache.mkdir()
    (cache / "excluded.py").write_text("PRIVATE FIXTURE", encoding="utf-8")
    paths = builder.runtime_inputs(tmp_path)
    assert {p.relative_to(tmp_path).as_posix() for p in paths} == {
        "dsh_runtime/observability/activity.py", builder.POLICY,
    }
    assert builder.source_bytes(tmp_path, activity) == b"# fixture\n"
    assert activity.read_bytes() == b"# fixture\r\n"


def test_missing_matching_runtime_is_rejected(tmp_path):
    (tmp_path / "dsh_runtime").mkdir()
    with pytest.raises(builder.BuildError, match="matching activity Runtime"):
        builder.runtime_inputs(tmp_path)


def test_existing_outputs_and_checkout_outputs_are_never_overwritten(tmp_path):
    repo = tmp_path / "checkout"
    repo.mkdir()
    existing = tmp_path / "existing"
    existing.mkdir()
    sentinel = existing / "sentinel"
    sentinel.write_bytes(b"keep")
    with pytest.raises(builder.BuildError, match="nonexistent"):
        builder.reserve_output(repo, existing)
    with pytest.raises(builder.BuildError, match="outside"):
        builder.reserve_output(repo, repo / "output")
    assert sentinel.read_bytes() == b"keep"
    assert not (repo / "output").exists()
    assert builder.reserve_output(repo, tmp_path / "new-output").is_dir()


def test_desktop_manifest_keeps_shared_host_services_out_of_dependencies():
    source = {"version": "dev", "engines": {"node": ">=24.19.0"},
              "dependencies": {"zod": "4.6.6", "@deepseek-ai/dsh-tools": "old"},
              "devDependencies": {"typescript": "6.0.3"}, "scripts": {"build": "unused"},
              "dsh": {"client": {"platform": "web"}}, "bin": {"copy": "./scripts/copy.mjs"}}
    built = builder.desktop_manifest(source)
    assert source["version"] == "dev" and "devDependencies" in source
    assert built["version"] == "0.1.0-rc.37-test.10"
    assert built["dependencies"] == {"zod": "4.6.6"}
    assert built["peerDependencies"]["@deepseek-ai/dsh-tools"] == "0.2.2-rc.1"
    assert "ACTIVITY_HISTORY_CONTRACT.txt" in built["files"]
    assert "scripts" not in built and "devDependencies" not in built


def test_archives_are_order_independent_and_have_no_machine_metadata(tmp_path):
    first, second = tmp_path / "first.tgz", tmp_path / "second.tgz"
    entries = {"package/lib/client.js": b"client\n", "package/scripts/copy.mjs": b"copy\n"}
    builder.write_archive(first, entries, {"package/scripts/copy.mjs"})
    builder.write_archive(second, dict(reversed(list(entries.items()))), {"package/scripts/copy.mjs"})
    assert first.read_bytes() == second.read_bytes()
    with tarfile.open(first, "r:gz") as archive:
        members = archive.getmembers()
        assert all(m.mtime == m.uid == m.gid == 0 and not m.uname and not m.gname for m in members)
        assert archive.getmember("package/scripts/copy.mjs").mode == 0o755
        assert archive.extractfile("package/lib/client.js").read() == b"client\n"
    with pytest.raises(FileExistsError):
        builder.write_archive(first, entries)


def test_linked_runtime_source_is_rejected_without_reading_its_target(tmp_path):
    activity = runtime_fixture(tmp_path)
    private = tmp_path / "private.txt"
    private.write_text("PRIVATE FIXTURE", encoding="utf-8")
    linked = activity.parent / "linked.py"
    try:
        linked.symlink_to(private)
    except OSError:
        pytest.skip("Creating Windows symlinks requires additional OS permission")
    with pytest.raises(builder.BuildError, match="Linked source"):
        builder.runtime_inputs(tmp_path)
