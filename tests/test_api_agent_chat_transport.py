import asyncio

import httpx
import pytest

from dsh_runtime.api_agent_chat_transport import ChatCompletionsTransport
from dsh_runtime.api_agent_connections import Connection
from dsh_runtime.api_agent_loop import TransportFailure


@pytest.mark.parametrize("provider,url", [
    ("openrouter", "https://openrouter.ai/api/v1/chat/completions"),
    ("siliconflow", "https://api.siliconflow.cn/v1/chat/completions"),
])
def test_provider_request_is_single_bounded_and_uses_pinned_endpoint(provider, url):
    requests = []

    def handler(request):
        requests.append(request)
        body = __import__("json").loads(request.content)
        assert str(request.url) == url
        assert request.headers["Authorization"] == "Bearer private-test-key"
        assert body["model"] == "vendor/model:free"
        assert body["stream"] is False
        assert body["tools"][0]["function"]["name"] == "read_file"
        if provider == "openrouter":
            assert body["provider"] == {
                "allow_fallbacks": False, "require_parameters": True,
            }
        else:
            assert "provider" not in body
        return httpx.Response(200, json={
            "model": "vendor/model:free", "choices": [{"finish_reason": "tool_calls", "message": {
                "content": None, "tool_calls": [{"id": "c1", "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path":"README.md"}'}}],
            }}], "usage": {"completion_tokens": 7},
        })

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            transport = ChatCompletionsTransport(Connection(
                provider, url.removesuffix("/chat/completions"), "private-test-key"
            ), client=client)
            return await transport.complete(
                model="vendor/model:free", messages=({"role": "user", "content": "inspect"},),
                allowed_tools=frozenset({"read_file"}), max_output_tokens=100,
            )

    reply = asyncio.run(scenario())
    assert reply.tool_calls[0].name == "read_file"
    assert reply.output_tokens == 7
    assert len(requests) == 1


@pytest.mark.parametrize("status,code", [
    (401, "provider_auth_error"), (429, "provider_rate_limited"),
    (503, "provider_http_error"),
])
def test_provider_failures_do_not_expose_response_or_retry(status, code):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, text="private-test-key")

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            transport = ChatCompletionsTransport(Connection(
                "openrouter", "https://openrouter.ai/api/v1", "private-test-key"
            ), client=client)
            return await transport.complete(
                model="vendor/model", messages=({"role": "user", "content": "hi"},),
                allowed_tools=frozenset(), max_output_tokens=10,
            )

    with pytest.raises(TransportFailure) as failure:
        asyncio.run(scenario())
    assert failure.value.code == code
    assert "private-test-key" not in str(failure.value)
    assert len(requests) == 1


def test_transport_rejects_unapproved_endpoint():
    with pytest.raises(ValueError, match="allowlisted"):
        ChatCompletionsTransport(Connection("openrouter", "https://example.invalid", "key"))


def test_truncated_completion_is_rejected():
    async def scenario():
        def handler(_request):
            return httpx.Response(200, json={
                "model": "vendor/model", "choices": [{
                    "finish_reason": "length", "message": {"content": "partial"},
                }], "usage": {"completion_tokens": 10},
            })
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            transport = ChatCompletionsTransport(Connection(
                "openrouter", "https://openrouter.ai/api/v1", "private-test-key"
            ), client=client)
            return await transport.complete(
                model="vendor/model", messages=({"role": "user", "content": "hi"},),
                allowed_tools=frozenset(), max_output_tokens=10,
            )
    with pytest.raises(TransportFailure, match="provider_response_invalid"):
        asyncio.run(scenario())
