"""Adaptador HTTP para APIs compatíveis com Chat Completions e tools."""
import asyncio
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from penal.config import settings


class LLMUnavailable(Exception):
    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


TRANSIENT_STATUS = {408, 500, 502, 503, 504}


def retry_delay(attempt: int, retry_after: str | None, base: float) -> float:
    delay = base * 2 ** attempt
    if retry_after:
        try:
            requested = float(retry_after)
        except ValueError:
            try:
                requested = (parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)).total_seconds()
            except (ValueError, TypeError, OverflowError):
                requested = 0
        delay = max(delay, requested)
    return max(0.0, delay)


def is_configured() -> bool:
    config = settings()
    return bool(config.llm_api_key and config.llm_base_url and config.llm_model)


class LLM:
    async def complete(self, messages: list[dict], tools: list[dict] | None = None,
                       require_tool: bool = False, structured: bool = False) -> dict:
        config = settings()
        if not is_configured():
            raise LLMUnavailable("Configure a API no arquivo .env: LLM_BASE_URL, LLM_MODEL e LLM_API_KEY. Use configurar_api.ps1.")
        payload = {"model": config.llm_model, "messages": messages,
                   "max_tokens": config.llm_max_tokens, "temperature": 0.1}
        if tools:
            payload.update(tools=tools, tool_choice="required" if require_tool else "auto")
        if structured:
            payload["response_format"] = {"type": "json_object"}
        deadline = time.monotonic() + config.llm_timeout
        async with httpx.AsyncClient(timeout=config.llm_timeout) as client:
            for attempt in range(config.llm_max_attempts):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise LLMUnavailable("O serviço de IA excedeu o tempo de resposta.", retryable=True)
                try:
                    response = await client.post(config.llm_base_url.rstrip("/") + "/chat/completions", json=payload,
                                                 headers={"Authorization": f"Bearer {config.llm_api_key}"}, timeout=remaining)
                    if response.status_code in TRANSIENT_STATUS:
                        delay = retry_delay(attempt, response.headers.get("Retry-After"), config.llm_retry_delay)
                        if attempt + 1 < config.llm_max_attempts and delay <= 10 and delay < deadline - time.monotonic():
                            await asyncio.sleep(delay)
                            continue
                    response.raise_for_status()
                    data = response.json()
                    message = data["choices"][0]["message"]
                    if not isinstance(message, dict):
                        raise ValueError("Mensagem inválida")
                    return message
                except httpx.HTTPStatusError as exc:
                    # Não propaga corpo, headers ou URL: podem conter credenciais.
                    status = exc.response.status_code
                    hint = {401: "Verifique a chave da API.", 403: "Verifique a permissão da API.",
                            404: "Verifique o endpoint e o nome do modelo.", 429: "Limite ou cota da API atingido.",
                            400: "Verifique se o modelo aceita tools, JSON e os parâmetros configurados."}.get(status, "O serviço de IA está temporariamente indisponível. Tente novamente mais tarde.")
                    raise LLMUnavailable(f"A API retornou HTTP {status}. {hint}", retryable=status in TRANSIENT_STATUS) from None
                except httpx.RequestError:
                    delay = config.llm_retry_delay * 2 ** attempt
                    if attempt + 1 < config.llm_max_attempts and delay < deadline - time.monotonic():
                        await asyncio.sleep(delay)
                        continue
                    raise LLMUnavailable("Não foi possível conectar ao serviço de IA após as tentativas automáticas.", retryable=True) from None
                except (KeyError, IndexError, ValueError, TypeError):
                    raise LLMUnavailable("Não foi possível obter uma resposta válida da API. Verifique a configuração do modelo.") from None
