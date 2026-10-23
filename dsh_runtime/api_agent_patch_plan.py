"""Pure, bounded patch planning; no filesystem write authority is granted here."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import re


MAX_PATCH_FILE_BYTES = 32_768
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class PatchPlan:
    old_sha256: str
    new_sha256: str
    new_bytes: bytes = field(repr=False)


def plan_text_patch(
    existing: bytes, *, expected_sha256: str,
    old_text: str, new_text: str,
) -> PatchPlan:
    """Compute one exact replacement after a full-byte optimistic conflict check.

    The caller must separately bind a real opened file to the workspace and
    perform a safe atomic write. This function never opens or mutates a path.
    """
    if not isinstance(existing, bytes) or len(existing) > MAX_PATCH_FILE_BYTES:
        raise ValueError("patch input is not a bounded byte string")
    if (not isinstance(expected_sha256, str)
        or _SHA256.fullmatch(expected_sha256) is None):
        raise ValueError("expected_sha256 must be lowercase SHA-256")
    old_digest = sha256(existing).hexdigest()
    if old_digest != expected_sha256:
        raise ValueError("patch conflict: file hash changed")
    if existing.startswith(b"\xef\xbb\xbf") or b"\x00" in existing:
        raise ValueError("patch target must be plain UTF-8 text")
    try:
        existing.decode("utf-8")
    except UnicodeError:
        raise ValueError("patch target must be plain UTF-8 text") from None
    if not isinstance(old_text, str) or not old_text:
        raise ValueError("old_text must be non-empty")
    if not isinstance(new_text, str) or old_text == new_text:
        raise ValueError("new_text must differ from old_text")
    try:
        old_bytes = old_text.encode("utf-8")
        new_bytes = new_text.encode("utf-8")
    except UnicodeError:
        raise ValueError("patch text must be UTF-8 encodable") from None
    if (b"\x00" in old_bytes or b"\x00" in new_bytes
        or len(old_bytes) > MAX_PATCH_FILE_BYTES
        or len(new_bytes) > MAX_PATCH_FILE_BYTES):
        raise ValueError("patch text is invalid or too large")
    if existing.count(old_bytes) != 1:
        raise ValueError("old_text must match exactly once")
    updated = existing.replace(old_bytes, new_bytes, 1)
    if len(updated) > MAX_PATCH_FILE_BYTES:
        raise ValueError("patched file would be too large")
    return PatchPlan(old_digest, sha256(updated).hexdigest(), updated)
