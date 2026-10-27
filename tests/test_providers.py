import asyncio
import json

import httpx
import pytest

from app.config import Settings
from app.core.errors import UpstreamError
from app.providers.factory import build_provider
from app.providers.mock import FAKE_LEAK, MockProvider
from app.providers.openai_compatible import OpenAICompatibleProvider

MESSAGES = [{"role": "user", "content": "hello <EMAIL_1>"}]


def run(coro):
    return asyncio.run(coro)


def test_mock_echoes_what_it_received():
    resp = run(MockProvider(latency_ms=0).complete(MESSAGES, "m", {}))
    assert "hello <EMAIL_1>" in resp.content
    assert resp.prompt_tokens and resp.completion_tokens


def test_mock_can_simulate_a_leak():
    resp = run(MockProvider(latency_ms=0).complete([{"role": "user", "content": "simulate leak"}], "m", {}))
    assert resp.content == FAKE_LEAK


def _provider(handler):
    return OpenAICompatibleProvider("https://llm.test/v1", "key", transport=httpx.MockTransport(handler))


def test_openai_compatible_parses_response_and_forwards_params():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "model": "gpt-oss-20b",
            "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 1},
        })

    resp = run(_provider(handler).complete(MESSAGES, "gpt-oss-20b", {"temperature": 0.2}))
    assert (resp.content, resp.prompt_tokens, resp.completion_tokens) == ("hi", 3, 1)
    assert seen["path"] == "/v1/chat/completions"
    assert seen["auth"] == "Bearer key"
    assert seen["body"]["temperature"] == 0.2 and seen["body"]["stream"] is False


def test_openai_compatible_raises_on_http_error():
    with pytest.raises(UpstreamError):
        run(_provider(lambda r: httpx.Response(429, text="rate limited")).complete(MESSAGES, "m", {}))


def test_openai_compatible_raises_on_unexpected_shape():
    with pytest.raises(UpstreamError):
        run(_provider(lambda r: httpx.Response(200, json={"oops": True})).complete(MESSAGES, "m", {}))


def test_factory_requires_key_for_real_provider():
    with pytest.raises(ValueError):
        build_provider(Settings(provider="openai_compatible", upstream_api_key=""))
    with pytest.raises(ValueError):
        build_provider(Settings(provider="nope"))
    assert build_provider(Settings(provider="mock")).name == "mock"
