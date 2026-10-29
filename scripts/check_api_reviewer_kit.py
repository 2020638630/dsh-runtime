"""Verify private preview ZIP contents without printing connection secrets."""

from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sys
import tarfile
import zipfile


def _all_blobs(blob: bytes, *, depth: int = 0):
    if depth > 3:
        raise ValueError("nested archive depth is excessive")
    if zipfile.is_zipfile(BytesIO(blob)):
        with zipfile.ZipFile(BytesIO(blob)) as archive:
            for item in archive.infolist():
                if item.is_dir() or item.file_size > 10_000_000:
                    continue
                content = archive.read(item)
                yield content
                yield from _all_blobs(content, depth=depth + 1)
    elif blob[:2] == b"\x1f\x8b":
        with tarfile.open(fileobj=BytesIO(blob), mode="r:gz") as archive:
            for item in archive:
                if not item.isfile() or item.size > 10_000_000:
                    continue
                member = archive.extractfile(item)
                if member is None:
                    continue
                content = member.read()
                yield content
                yield from _all_blobs(content, depth=depth + 1)


def check(kit_path: Path, connection_path: Path) -> dict[str, int | bool]:
    kit = kit_path.read_bytes()
    connection = json.loads(connection_path.read_text(encoding="utf-8"))
    secrets = {
        value["api_key"].encode("utf-8")
        for value in connection["connections"].values()
        if isinstance(value, dict) and isinstance(value.get("api_key"), str)
        and len(value["api_key"]) >= 10
    }
    if not secrets:
        raise ValueError("no API keys available for leak scan")
    with zipfile.ZipFile(BytesIO(kit)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        if manifest["schema_version"] != 3 or len(manifest["python_wheels"]) != 7:
            raise ValueError("kit schema or wheel list is unexpected")
        expected = {
            manifest["plugin"]["file"]: manifest["plugin"]["sha256"],
            manifest["runtime"]["file"]: manifest["runtime"]["sha256"],
            **{f"wheels/{entry['file']}": entry["sha256"]
               for entry in manifest["python_wheels"]},
        }
        for name, digest in expected.items():
            if sha256(archive.read(name)).hexdigest().upper() != digest.upper():
                raise ValueError("a packaged artifact hash does not match manifest")
        top_level_count = len([entry for entry in archive.infolist() if not entry.is_dir()])
    scanned = 0
    hits = 0
    for content in _all_blobs(kit):
        scanned += 1
        hits += sum(secret in content for secret in secrets)
    if hits:
        raise ValueError("a local API key was found in the package")
    return {
        "manifest_hashes_valid": True,
        "top_level_files": top_level_count,
        "scanned_blobs": scanned,
        "key_count": len(secrets),
        "key_hits": hits,
    }


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: check_api_reviewer_kit.py KIT_ZIP CONNECTION_JSON")
    print(json.dumps(check(Path(sys.argv[1]), Path(sys.argv[2])), sort_keys=True))
