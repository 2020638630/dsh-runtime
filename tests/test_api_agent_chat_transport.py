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
        assert len(body["tools"]) == 1
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


def test_final_only_request_sends_no_tool_schema():
    def handler(request):
        body = __import__("json").loads(request.content)
        assert "tools" not in body and "tool_choice" not in body
        return httpx.Response(200, json={
            "model": "vendor/model", "choices": [{"finish_reason": "stop", "message": {
                "content": "DSH_VERIFICATION: FAIL",
            }}], "usage": {"completion_tokens": 5},
        })

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            transport = ChatCompletionsTransport(Connection(
                "siliconflow", "https://api.siliconflow.cn/v1", "private-test-key"
            ), client=client)
            return await transport.complete(
                model="vendor/model", messages=({"role": "user", "content": "verdict"},),
                allowed_tools=frozenset(), max_output_tokens=100,
            )

    reply = asyncio.run(scenario())
    assert reply.text == "DSH_VERIFICATION: FAIL" and reply.tool_calls == ()


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


@pytest.mark.parametrize("unsafe_tool", ["list_files", "search_text", "apply_patch"])
def test_transport_does_not_advertise_unqualified_tools(unsafe_tool):
    transport = ChatCompletionsTransport(Connection(
        "openrouter", "https://openrouter.ai/api/v1", "private-test-key"
    ))
    with pytest.raises(TransportFailure, match="unsupported_tool_schema"):
        asyncio.run(transport.complete(
            model="vendor/model", messages=({"role": "user", "content": "inspect"},),
            allowed_tools=frozenset({unsafe_tool}), max_output_tokens=10,
        ))


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


def test_response_limit_stops_stream_before_consuming_entire_body():
    class LargeStream(httpx.AsyncByteStream):
        chunks_read = 0
        closed = False

        async def __aiter__(self):
            for _ in range(100):
                self.chunks_read += 1
                yield b"x" * 65_536

        async def aclose(self):
            self.closed = True

    stream = LargeStream()

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, stream=stream)
        )) as client:
            transport = ChatCompletionsTransport(Connection(
                "openrouter", "https://openrouter.ai/api/v1", "private-test-key"
            ), client=client)
            await transport.complete(model="vendor/model", messages=(),
                                     allowed_tools=frozenset(), max_output_tokens=10)

    with pytest.raises(TransportFailure, match="provider_response_too_large"):
        asyncio.run(scenario())
    assert stream.chunks_read <= 16
    assert stream.closed


@pytest.mark.parametrize("status,headers,expected", [
    (302, {"location": "https://example.invalid/collect"}, "provider_http_error"),
    (401, {}, "provider_auth_error"),
    (200, {"content-encoding": "gzip"}, "provider_response_invalid"),
])
def test_rejected_response_never_reads_body_or_follows_redirect(status, headers, expected):
    requests = []

    class UnreadBody(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            raise AssertionError("rejected body must not be consumed")
            yield b""

        async def aclose(self):
            self.closed = True

    stream = UnreadBody()

    def handler(request):
        requests.append(request)
        assert request.headers["accept-encoding"] == "identity"
        return httpx.Response(status, headers=headers, stream=stream)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                     follow_redirects=True) as client:
            transport = ChatCompletionsTransport(Connection(
                "openrouter", "https://openrouter.ai/api/v1", "private-test-key"
            ), client=client)
            await transport.complete(model="vendor/model", messages=(),
                                     allowed_tools=frozenset(), max_output_tokens=10)

    with pytest.raises(TransportFailure, match=expected):
        asyncio.run(scenario())
    assert len(requests) == 1
    assert stream.closed


def test_successful_response_can_arrive_in_separate_chunks():
    payload = __import__("json").dumps({
        "model": "vendor/model", "choices": [{"finish_reason": "stop",
            "message": {"content": "reviewed"}}], "usage": {"completion_tokens": 1},
    }).encode()

    class SplitBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            for offset in range(0, len(payload), 7):
                yield payload[offset:offset + 7]

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, stream=SplitBody())
        )) as client:
            return await ChatCompletionsTransport(Connection(
                "openrouter", "https://openrouter.ai/api/v1", "private-test-key"
            ), client=client).complete(model="vendor/model", messages=(),
                                      allowed_tools=frozenset(), max_output_tokens=10)

    assert asyncio.run(scenario()).text == "reviewed"
