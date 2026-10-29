"""Pure patch contracts before granting an API worker any write capability."""

from hashlib import sha256

import pytest

from dsh_runtime.api_agent_patch_plan import MAX_PATCH_FILE_BYTES, plan_text_patch


def digest(content: bytes) -> str:
    return sha256(content).hexdigest()


def test_exact_single_match_preserves_other_bytes_and_does_not_mutate_input():
    original = b"first\r\ntarget\r\nlast\r\n"
    plan = plan_text_patch(
        original, expected_sha256=digest(original),
        old_text="target", new_text="changed",
    )
    assert plan.new_bytes == b"first\r\nchanged\r\nlast\r\n"
    assert plan.old_sha256 == digest(original)
    assert plan.new_sha256 == digest(plan.new_bytes)
    assert original == b"first\r\ntarget\r\nlast\r\n"
    assert "changed" not in repr(plan)


def test_stale_hash_rejects_without_returning_a_plan():
    with pytest.raises(ValueError, match="conflict"):
        plan_text_patch(b"current", expected_sha256=digest(b"stale"),
                        old_text="current", new_text="new")


@pytest.mark.parametrize("original,old,new,message", [
    (b"repeat repeat", "repeat", "new", "exactly once"),
    (b"once", "missing", "new", "exactly once"),
    (b"once", "", "new", "non-empty"),
    (b"once", "once", "once", "differ"),
    (b"\xef\xbb\xbfonce", "once", "new", "plain UTF-8"),
    (b"once\x00", "once", "new", "plain UTF-8"),
])
def test_ambiguous_or_non_text_patch_is_rejected(original, old, new, message):
    with pytest.raises(ValueError, match=message):
        plan_text_patch(original, expected_sha256=digest(original),
                        old_text=old, new_text=new)


def test_output_size_bound_is_enforced():
    original = b"x"
    with pytest.raises(ValueError, match="too large"):
        plan_text_patch(original, expected_sha256=digest(original),
                        old_text="x", new_text="y" * (MAX_PATCH_FILE_BYTES + 1))


def test_invalid_hash_spelling_is_rejected():
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        plan_text_patch(b"one", expected_sha256=digest(b"one").upper(),
                        old_text="one", new_text="two")
