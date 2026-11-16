"""Adaptador HTTP para APIs compatíveis com Chat Completions e tools."""
import httpx

from penal.config import settings


class LLMUnavailable(Exception):
    pass


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
        try:
            async with httpx.AsyncClient(timeout=config.llm_timeout) as client:
                response = await client.post(config.llm_base_url.rstrip("/") + "/chat/completions", json=payload,
                                             headers={"Authorization": f"Bearer {config.llm_api_key}"})
                response.raise_for_status()
                data = response.json()
                message = data["choices"][0]["message"]
                if not isinstance(message, dict):
                    raise ValueError("Mensagem inválida")
                return message
        except httpx.HTTPStatusError as exc:
            # Não propaga corpo, headers ou URL: podem conter credenciais do provedor.
            status = exc.response.status_code
            hint = {401: "Verifique a chave da API.", 403: "Verifique a permissão da API.",
                    404: "Verifique o endpoint e o nome do modelo.", 429: "Limite ou cota da API atingido.",
                    400: "Verifique se o modelo aceita tools, JSON e os parâmetros configurados."}.get(status, "Tente novamente mais tarde.")
            raise LLMUnavailable(f"A API retornou HTTP {status}. {hint}") from None
        except (httpx.HTTPError, KeyError, IndexError, ValueError):
            raise LLMUnavailable("Não foi possível obter uma resposta válida da API. Verifique a conexão e a configuração.") from None
