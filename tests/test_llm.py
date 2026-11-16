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
