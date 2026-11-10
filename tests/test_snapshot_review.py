import asyncio
import hashlib
from io import BytesIO
from types import SimpleNamespace

import pytest

from dsh_runtime.api_agent_loop import ModelReply, ToolCall, TransportFailure
from dsh_runtime import snapshot_review
from dsh_runtime.snapshot_review import review_patch


class RecordingTransport:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    async def complete(self, **kwargs):
        self.calls.append(kwargs)
        return self.reply


def test_snapshot_review_sends_exact_patch_once_and_no_tools():
    patch = "--- a/test.txt\n+++ b/test.txt\n@@ -1 +1 @@\n-old\n+新\n"
    model = "deepseek-ai/DeepSeek-V3.2"
    transport = RecordingTransport(ModelReply("Finding\nDSH_SNAPSHOT_REVIEW: FAIL", (), model, 14))
    reply = asyncio.run(review_patch(patch, model, transport))
    assert len(transport.calls) == 1
    request = transport.calls[0]
    assert request["model"] == model
    assert request["messages"][1:] == ({"role": "user", "content": patch},)
    assert request["allowed_tools"] == frozenset()
    assert reply == {
        "patch_sha256": hashlib.sha256(patch.encode()).hexdigest(),
        "observed_model": model,
        "verdict": "FAIL",
        "report": "Finding",
    }


@pytest.mark.parametrize("reply", [
    ModelReply("DSH_SNAPSHOT_REVIEW: PASS", (ToolCall("id", "read_file", "{}"),), None, 1),
    ModelReply("uncertain", (), None, 1),
    ModelReply("DSH_SNAPSHOT_REVIEW: PASS", (), None, 1537),
])
def test_snapshot_review_never_retries_invalid_response(reply):
    transport = RecordingTransport(reply)
    with pytest.raises(ValueError):
        asyncio.run(review_patch("patch", "model", transport))
    assert len(transport.calls) == 1


def test_snapshot_review_helper_preserves_timeout_without_provider_diagnostics(monkeypatch, capsys):
    role = SimpleNamespace(adapter="api_agent", model="model", provider="siliconflow", connection_ref="test")
    monkeypatch.setattr(snapshot_review, "RoleConfig", SimpleNamespace(from_environment=lambda: SimpleNamespace(reviewer=role)))
    monkeypatch.setattr(snapshot_review, "ConnectionCatalog", SimpleNamespace(
        from_file=lambda path: SimpleNamespace(get=lambda *args: object())))
    monkeypatch.setattr(snapshot_review, "ChatCompletionsTransport", lambda *args, **kwargs: object())
    monkeypatch.setenv("DSH_API_AGENT_CONNECTIONS_PATH", "unused")
    monkeypatch.setattr(snapshot_review.sys, "stdin", SimpleNamespace(buffer=BytesIO(b'"patch"')))

    async def timeout(*args):
        raise TransportFailure("provider_timeout")

    monkeypatch.setattr(snapshot_review, "review_patch", timeout)
    assert snapshot_review.main() == 3
    assert capsys.readouterr() == ("", "")
