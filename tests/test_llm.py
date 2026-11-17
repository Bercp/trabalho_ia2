import asyncio

import httpx
import pytest

import penal.llm as adapter
from penal.config import Settings


def test_reports_missing_configuration_without_network(monkeypatch):
    monkeypatch.setattr(adapter, "is_configured", lambda: False)
    with pytest.raises(adapter.LLMUnavailable, match="Configure a API"):
        asyncio.run(adapter.LLM().complete([{"role": "user", "content": "Direito Penal"}]))


def test_http_error_never_includes_secret_body(monkeypatch):
    config = Settings(_env_file=None, llm_base_url="https://example.invalid/v1", llm_api_key="fake-test-secret", llm_model="test")
    monkeypatch.setattr(adapter, "settings", lambda: config)
    monkeypatch.setattr(adapter, "is_configured", lambda: True)
    original = httpx.AsyncClient

    def respond(request):
        return httpx.Response(401, json={"error": "fake-test-secret"}, request=request)

    monkeypatch.setattr(adapter.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs))
    with pytest.raises(adapter.LLMUnavailable) as error:
        asyncio.run(adapter.LLM().complete([{"role": "user", "content": "Direito Penal"}]))
    assert "401" in str(error.value)
    assert "fake-test-secret" not in str(error.value)


def test_sends_tools_and_json_mode_to_compatible_api(monkeypatch):
    config = Settings(_env_file=None, llm_base_url="https://example.invalid/v1/", llm_api_key="test-key", llm_model="test")
    monkeypatch.setattr(adapter, "settings", lambda: config)
    monkeypatch.setattr(adapter, "is_configured", lambda: True)
    original = httpx.AsyncClient
    captured = []

    def respond(request):
        import json
        captured.append(json.loads(request.content))
        assert str(request.url) == "https://example.invalid/v1/chat/completions"
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "{}"}}]}, request=request)

    monkeypatch.setattr(adapter.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs))
    asyncio.run(adapter.LLM().complete([], tools=[{"type": "function"}], require_tool=True))
    asyncio.run(adapter.LLM().complete([], structured=True))
    assert captured[0]["tool_choice"] == "required"
    assert captured[1]["response_format"] == {"type": "json_object"}


def configure_transport(monkeypatch, respond):
    config = Settings(_env_file=None, llm_base_url="https://example.invalid/v1", llm_api_key="test-key", llm_model="test", llm_retry_delay=0)
    monkeypatch.setattr(adapter, "settings", lambda: config)
    monkeypatch.setattr(adapter, "is_configured", lambda: True)
    original = httpx.AsyncClient
    monkeypatch.setattr(adapter.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs))


def test_retries_transient_503_without_changing_request(monkeypatch):
    bodies = []

    def respond(request):
        bodies.append(request.content)
        if len(bodies) < 3:
            return httpx.Response(503, json={"error": "unavailable"}, request=request)
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]}, request=request)

    configure_transport(monkeypatch, respond)
    result = asyncio.run(adapter.LLM().complete([{"role": "user", "content": "O que é legítima defesa?"}]))
    assert result["content"] == "ok"
    assert len(bodies) == 3 and len(set(bodies)) == 1


def test_persistent_503_is_bounded_and_marked_temporary(monkeypatch):
    attempts = []

    def respond(request):
        attempts.append(1)
        return httpx.Response(503, text="test-key must not leak", request=request)

    configure_transport(monkeypatch, respond)
    with pytest.raises(adapter.LLMUnavailable) as error:
        asyncio.run(adapter.LLM().complete([]))
    assert len(attempts) == 3
    assert error.value.retryable
    assert "test-key" not in str(error.value)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429])
def test_does_not_repeat_permanent_errors_or_spend_quota(monkeypatch, status):
    attempts = []

    def respond(request):
        attempts.append(1)
        return httpx.Response(status, request=request)

    configure_transport(monkeypatch, respond)
    with pytest.raises(adapter.LLMUnavailable) as error:
        asyncio.run(adapter.LLM().complete([]))
    assert len(attempts) == 1
    assert not error.value.retryable


def test_respects_retry_after_without_waiting_too_long(monkeypatch):
    attempts = []

    def respond(request):
        attempts.append(1)
        return httpx.Response(503, headers={"Retry-After": "60"}, request=request)

    configure_transport(monkeypatch, respond)
    with pytest.raises(adapter.LLMUnavailable):
        asyncio.run(adapter.LLM().complete([]))
    assert len(attempts) == 1
    assert adapter.retry_delay(0, "3", 1.5) == 3
