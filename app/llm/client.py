import json
import time
from dataclasses import dataclass
from typing import Any, Protocol

from app.config import Settings
from app.llm.schema import to_strict_schema
from app.schemas import ExtractionWire


class LLMTransientError(Exception):
    """Rate limit, timeout, conexão ou 5xx: vale tentar de novo (backoff no Celery)."""


class LLMPermanentError(Exception):
    """Credencial inválida, requisição inválida etc.: repetir não resolve."""


@dataclass(frozen=True)
class LLMCallResult:
    raw_content: str
    finish_reason: str
    model: str
    system_fingerprint: str | None
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int


class LLMClient(Protocol):
    def extract(self, messages: list[dict[str, str]]) -> LLMCallResult: ...


class OpenAIClient:
    def __init__(self, settings: Settings, client: Any | None = None):
        self._settings = settings
        if client is None:
            import openai

            client = openai.OpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.llm_base_url or None,
                timeout=settings.llm_timeout_s,
                max_retries=0,
            )
        self._client = client
        self._schema = to_strict_schema(ExtractionWire)

    def _build_request(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        cfg = self._settings
        request: dict[str, Any] = {
            "model": cfg.llm_model,
            "messages": messages,
            "temperature": cfg.llm_temperature,
        }
        if cfg.llm_send_seed:
            request["seed"] = cfg.llm_seed
        # OpenAI: max_completion_tokens. Endpoints compatíveis: max_tokens é o denominador comum.
        limit_param = "max_tokens" if cfg.llm_base_url else "max_completion_tokens"
        request[limit_param] = cfg.llm_max_completion_tokens
        if cfg.llm_structured_mode == "json_object":
            # Sem enforcement de schema no provedor: o schema vai no prompt e o nosso loop valida.
            schema_note = (
                "\n\nResponda APENAS com um objeto JSON válido, sem markdown, que siga este JSON Schema:\n"
                + json.dumps(self._schema, ensure_ascii=False)
            )
            first, *rest = messages
            request["messages"] = [{**first, "content": first["content"] + schema_note}, *rest]
            request["response_format"] = {"type": "json_object"}
        else:
            request["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "cv_extraction", "strict": True, "schema": self._schema},
            }
        return request

    def extract(self, messages: list[dict[str, str]]) -> LLMCallResult:
        import openai

        request = self._build_request(messages)
        start = time.perf_counter()
        try:
            completion = self._client.chat.completions.create(**request)
        except (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError) as exc:
            raise LLMTransientError(f"{type(exc).__name__}: {str(getattr(exc, 'message', ''))[:200]}") from exc
        except openai.APIStatusError as exc:
            if exc.status_code >= 500:
                raise LLMTransientError(f"HTTP {exc.status_code}: {str(exc.message)[:200]}") from exc
            raise LLMPermanentError(f"HTTP {exc.status_code}: {str(exc.message)[:200]}") from exc
        latency_ms = int((time.perf_counter() - start) * 1000)

        choice = completion.choices[0]
        usage = completion.usage
        return LLMCallResult(
            raw_content=choice.message.content or "",
            finish_reason=choice.finish_reason or "",
            model=completion.model,
            system_fingerprint=getattr(completion, "system_fingerprint", None),
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            latency_ms=latency_ms,
        )


def build_llm_client(settings: Settings) -> LLMClient:
    return OpenAIClient(settings)
