"""Fetch a fixed, hash-verified PyPI wheel set for the private Windows kit.

Run only for a new release staging directory. Never reads local connection
files, credentials, or an existing Home. The release manifest must include
the printed hashes and the installer must verify them before installation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from urllib.request import ProxyHandler, build_opener


PINS = {
    "httpx": "0.28.1",
    "httpcore": "1.0.9",
    "anyio": "4.13.0",
    "certifi": "2026.5.20",
    "idna": "3.18",
    "h11": "0.16.0",
    "typing_extensions": "4.15.0",
}


def build(destination: Path) -> list[dict[str, str]]:
    if destination.exists():
        raise ValueError("wheel destination must not exist")
    destination.mkdir(parents=True)
    # Explicit direct PyPI access for the packager. End-user installation is
    # offline and never contacts PyPI or silently inherits a system proxy.
    opener = build_opener(ProxyHandler({}))
    records: list[dict[str, str]] = []
    for name, version in PINS.items():
        with opener.open(f"https://pypi.org/pypi/{name}/{version}/json", timeout=15) as response:
            release = json.load(response)
        wheels = [item for item in release["urls"] if item["filename"].endswith("-py3-none-any.whl")]
        if len(wheels) != 1:
            raise ValueError(f"expected one universal wheel for {name}=={version}")
        wheel = wheels[0]
        filename = wheel["filename"]
        if Path(filename).name != filename or not filename.endswith(".whl"):
            raise ValueError("wheel filename is invalid")
        with opener.open(wheel["url"], timeout=30) as response:
            content = response.read()
        digest = hashlib.sha256(content).hexdigest()
        if digest != wheel["digests"]["sha256"]:
            raise ValueError(f"PyPI digest mismatch for {name}")
        (destination / filename).write_bytes(content)
        records.append({"file": filename, "sha256": digest.upper()})
    return records


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: build_api_reviewer_wheelhouse.py NEW_DIRECTORY")
    print(json.dumps(build(Path(sys.argv[1])), indent=2))
