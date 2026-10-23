"""No-network contract tests for the opt-in API agent boundary."""

import asyncio
from hashlib import sha256
import json

import pytest

from dsh_runtime.api_agent_contract import ApiAgentConfig, ApiRole
from dsh_runtime.api_agent_connections import ConnectionCatalog
from dsh_runtime.api_agent_loop import ModelReply, ToolCall, run_api_agent
from dsh_runtime.api_agent_read_tools import WorkspaceReadBroker


def config_document() -> dict:
    def role(model: str) -> dict:
        return {
            "adapter": "api_agent", "provider": "openrouter", "model": model,
            "connection_ref": "trial_openrouter", "max_requests": 3,
            "max_tool_calls": 2, "max_output_tokens": 100,
        }
    return {"schema_version": 2, "roles": {
        "worker": role("vendor/worker:free"),
        "reviewer": role("vendor/reviewer:free"),
        "inspector": role("vendor/inspector:free"),
    }}


def test_v2_is_explicit_and_contains_no_key() -> None:
    config = ApiAgentConfig.from_document(config_document())
    assert config.worker.connection_ref == "trial_openrouter"
    assert config.reviewer.model == "vendor/reviewer:free"


def test_v2_allows_cli_fallback_per_role() -> None:
    document = config_document()
    document["roles"]["worker"] = {"adapter": "codebuddy", "model": None}
    document["roles"]["reviewer"] = {"adapter": "codex", "model": "gpt-review"}
    config = ApiAgentConfig.from_document(document)
    assert config.worker.adapter == "codebuddy"
    assert config.reviewer.model == "gpt-review"
    assert config.inspector.provider == "openrouter"


@pytest.mark.parametrize("change", [
    lambda d: d.update(schema_version=1),
    lambda d: d["roles"]["worker"].update(api_key="secret"),
    lambda d: d["roles"]["worker"].update(max_requests=True),
    lambda d: d["roles"]["reviewer"].update(provider="unknown"),
    lambda d: d["roles"]["inspector"].update(connection_ref="../../secrets"),
])
def test_invalid_configuration_fails_closed(change) -> None:
    document = config_document()
    change(document)
    with pytest.raises(ValueError):
        ApiAgentConfig.from_document(document)


def test_duplicate_configuration_field_is_rejected() -> None:
    raw = json.dumps(config_document()).replace(
        '"schema_version": 2', '"schema_version": 2, "schema_version": 2'
    )
    with pytest.raises(ValueError, match="duplicate"):
        ApiAgentConfig.from_json(raw)


class FakeTransport:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.seen = []

    async def complete(self, **kwargs):
        self.seen.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class FakeBroker:
    def __init__(self):
        self.calls = []

    async def execute(self, name, arguments):
        self.calls.append((name, arguments))
        return "README.md"


def run(role_name, transport, broker, *, write=False):
    role = ApiRole("openrouter", "vendor/model:free", "trial", 3, 2, 100)
    return asyncio.run(run_api_agent(
        role, "inspect", transport, broker,
        role_name=role_name, allow_workspace_write=write,
    ))


def test_read_only_tool_loop_keeps_requested_and_observed_separate() -> None:
    transport = FakeTransport(
        ModelReply(tool_calls=(ToolCall("c1", "read_file", '{"path":"README.md"}'),),
                   observed_model="vendor/model:free", output_tokens=5),
        ModelReply(text="One file", observed_model="vendor/model:free", output_tokens=3),
    )
    broker = FakeBroker()
    result = run("inspector", transport, broker)
    assert result.success and result.text == "One file"
    assert (result.requested_model, result.observed_model) == (
        "vendor/model:free", "vendor/model:free"
    )
    assert result.requests == 2 and result.tool_calls == 1
    assert broker.calls == [("read_file", {"path": "README.md"})]
    assert "apply_patch" not in transport.seen[0]["allowed_tools"]
    assert transport.seen[0]["allowed_tools"] == frozenset({"read_file"})


def test_reviewer_receives_verified_file_bytes_from_real_broker(tmp_path) -> None:
    data = b"RC18_HOST_REVIEW_OK\n"
    (tmp_path / "review.txt").write_bytes(data)
    transport = FakeTransport(
        ModelReply(tool_calls=(ToolCall("c1", "read_file", '{"path":"review.txt"}'),),
                   output_tokens=5),
        ModelReply(text="DSH_VERIFICATION: PASS", output_tokens=5),
    )
    result = run("reviewer", transport, WorkspaceReadBroker(tmp_path))
    assert result.success
    tool_message = transport.seen[1]["messages"][-1]
    response = json.loads(tool_message["content"])
    assert response == {
        "schema_version": 1,
        "byte_length": len(data),
        "sha256": sha256(data).hexdigest(),
        "content": data.decode("utf-8"),
    }
    assert "verified byte_length" in transport.seen[0]["messages"][0]["content"]
    assert "do not reread the same file" in transport.seen[0]["messages"][0]["content"]


def test_reviewer_can_retry_one_rejected_read_without_leaking_path(tmp_path) -> None:
    (tmp_path / "review.txt").write_text("allowed\n", encoding="utf-8")
    transport = FakeTransport(
        ModelReply(tool_calls=(ToolCall("c1", "read_file", '{"path":".env"}'),), output_tokens=2),
        ModelReply(tool_calls=(ToolCall("c2", "read_file", '{"path":"review.txt"}'),), output_tokens=2),
        ModelReply(text="DSH_VERIFICATION: PASS", output_tokens=2),
    )
    result = run("reviewer", transport, WorkspaceReadBroker(tmp_path))
    assert result.success and result.tool_calls == 2 and result.requests == 3
    failed_result = transport.seen[1]["messages"][-1]["content"]
    assert failed_result == "read_file unavailable for that path"
    assert ".env" not in failed_result


def test_reviewer_cannot_pass_after_only_a_rejected_read(tmp_path) -> None:
    transport = FakeTransport(
        ModelReply(tool_calls=(ToolCall("c1", "read_file", '{"path":".env"}'),), output_tokens=2),
        ModelReply(text="DSH_VERIFICATION: PASS", output_tokens=2),
    )
    result = run("reviewer", transport, WorkspaceReadBroker(tmp_path))
    assert result.error_code == "reviewer_no_file_read"
    assert result.tool_calls == 1


@pytest.mark.parametrize("unsafe_tool", ["list_files", "search_text"])
def test_directory_enumeration_is_rejected_before_broker(unsafe_tool) -> None:
    broker = FakeBroker()
    result = run("inspector", FakeTransport(ModelReply(tool_calls=(
        ToolCall("c1", unsafe_tool, "{}"),
    ), output_tokens=1)), broker)
    assert result.error_code == "invalid_tool_call"
    assert broker.calls == []


def test_response_model_mismatch_is_recorded_and_rejected() -> None:
    result = run("inspector", FakeTransport(ModelReply(
        text="answer", observed_model="other/model", output_tokens=2
    )), FakeBroker())
    assert result.error_code == "model_mismatch"
    assert result.requested_model == "vendor/model:free"
    assert result.observed_model == "other/model"


def test_entire_batch_is_validated_before_first_write() -> None:
    transport = FakeTransport(ModelReply(tool_calls=(
        ToolCall("c1", "apply_patch", "{}"),
        ToolCall("c2", "unknown_tool", "{}"),
    ), output_tokens=1))
    broker = FakeBroker()
    result = run("worker", transport, broker, write=True)
    assert result.error_code == "invalid_tool_call" and broker.calls == []


def test_worker_write_flag_does_not_advertise_unqualified_patch() -> None:
    transport = FakeTransport(ModelReply(text="done", output_tokens=1))
    result = run("worker", transport, FakeBroker(), write=True)
    assert result.success
    assert transport.seen[0]["allowed_tools"] == frozenset({"read_file"})


def test_reviewer_cannot_gain_write_tool_from_context() -> None:
    transport = FakeTransport(ModelReply(tool_calls=(
        ToolCall("c1", "apply_patch", "{}"),
    ), output_tokens=1))
    broker = FakeBroker()
    result = run("reviewer", transport, broker, write=True)
    assert result.error_code == "invalid_tool_call" and broker.calls == []


def test_reviewer_must_use_native_read_before_verdict() -> None:
    transport = FakeTransport(ModelReply(
        text="<function=read_file>README.md</function>\nDSH_VERIFICATION: PASS",
        output_tokens=10,
    ))
    result = run("reviewer", transport, FakeBroker())
    assert result.error_code == "reviewer_no_file_read"
    assert result.text is None
    messages = transport.seen[0]["messages"]
    assert messages[0]["role"] == "system"
    assert "native read_file" in messages[0]["content"]


def test_reviewer_accepts_verdict_after_native_read() -> None:
    transport = FakeTransport(
        ModelReply(tool_calls=(ToolCall("c1", "read_file", '{"path":"README.md"}'),), output_tokens=4),
        ModelReply(text="Evidence inspected.\nDSH_VERIFICATION: PASS", output_tokens=6),
    )
    broker = FakeBroker()
    result = run("reviewer", transport, broker)
    assert result.success
    assert result.tool_calls == 1
    assert broker.calls == [("read_file", {"path": "README.md"})]


def test_bounded_text_beside_native_tool_call_is_discarded() -> None:
    transport = FakeTransport(
        ModelReply(text="I will read the file.", tool_calls=(
            ToolCall("c1", "read_file", '{"path":"README.md"}'),
        ), output_tokens=9),
        ModelReply(text="Checked.\nDSH_VERIFICATION: PASS", output_tokens=6),
    )
    broker = FakeBroker()
    result = run("reviewer", transport, broker)
    assert result.success and result.tool_calls == 1
    assert result.text == "Checked.\nDSH_VERIFICATION: PASS"
    assert "I will read the file." not in str(transport.seen[1]["messages"])


def test_oversize_text_beside_tool_call_rejects_before_broker() -> None:
    broker = FakeBroker()
    reply = ModelReply(text="x" * 4097, tool_calls=(
        ToolCall("c1", "read_file", '{"path":"README.md"}'),
    ), output_tokens=9)
    result = run("reviewer", FakeTransport(reply), broker)
    assert result.error_code == "invalid_tool_companion_text"
    assert broker.calls == []


def test_transport_error_is_redacted_and_not_retried() -> None:
    transport = FakeTransport(RuntimeError("Authorization: Bearer sensitive-value"))
    result = run("inspector", transport, FakeBroker())
    assert result.error_code == "provider_error"
    assert "sensitive-value" not in repr(result)
    assert len(transport.seen) == 1


def test_missing_usage_fails_closed() -> None:
    result = run("inspector", FakeTransport(ModelReply(text="done")), FakeBroker())
    assert result.error_code == "missing_or_invalid_token_count"


def test_duplicate_arguments_fail_before_tool() -> None:
    broker = FakeBroker()
    reply = ModelReply(tool_calls=(ToolCall("c1", "read_file", '{"path":"a","path":"b"}'),), output_tokens=1)
    result = run("inspector", FakeTransport(reply), broker)
    assert result.error_code == "invalid_tool_arguments" and broker.calls == []


def test_connection_file_is_outside_git_and_secret_is_not_represented(tmp_path) -> None:
    path = tmp_path / "connections.local.json"
    document = {"schema_version": 1, "connections": {"trial": {
        "provider": "siliconflow", "base_url": "https://api.siliconflow.cn/v1",
        "api_key": "private-test-key-value",
    }}}
    path.write_text(json.dumps(document), encoding="utf-8")
    connection = ConnectionCatalog.from_file(path).get("trial", "siliconflow")
    assert connection.api_key == "private-test-key-value"
    assert "private-test-key-value" not in repr(connection)
    with pytest.raises(ValueError, match="provider does not match"):
        ConnectionCatalog.from_file(path).get("trial", "openrouter")
    (tmp_path / ".git").mkdir()
    with pytest.raises(ValueError, match="outside a Git worktree"):
        ConnectionCatalog.from_file(path)


def test_connection_rejects_unapproved_endpoint_without_echoing_key(tmp_path) -> None:
    path = tmp_path / "connections.local.json"
    path.write_text(json.dumps({"schema_version": 1, "connections": {"trial": {
        "provider": "openrouter", "base_url": "https://example.invalid/v1",
        "api_key": "private-test-key-value",
    }}}), encoding="utf-8")
    with pytest.raises(ValueError, match="endpoint is not allowlisted") as failure:
        ConnectionCatalog.from_file(path)
    assert "private-test-key-value" not in str(failure.value)
