from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./talentmatch.db"
    redis_url: str = "redis://localhost:6379/0"
    auto_create_tables: bool = True  # MVP; em produção, usar migrações (Alembic)

    openai_api_key: str = ""  # chave do provedor (OpenAI, OpenRouter, Google...)
    llm_base_url: str = ""  # vazio = OpenAI; ou endpoint compatível (OpenRouter, Gemini)
    llm_structured_mode: str = "json_schema"  # "json_schema" (estrito) | "json_object" (schema vai no prompt)
    llm_send_seed: bool = True  # desligue se o provedor rejeitar o parâmetro 'seed'
    llm_model: str = "gpt-4o-mini-2024-07-18"  # snapshot fixo, nunca alias móvel
    llm_temperature: float = 0.0
    llm_seed: int = 42
    llm_timeout_s: float = 30.0
    llm_max_completion_tokens: int = 800
    llm_max_attempts: int = 3  # 1 chamada + até 2 correções de schema

    api_keys: str = ""  # "client_id:secret,client_id2:secret2"

    retention_days: int = 180
    max_upload_bytes: int = 5 * 1024 * 1024
    max_pdf_pages: int = 10
    max_text_chars: int = 20_000
    min_text_chars: int = 50

    @property
    def api_key_pairs(self) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        for item in self.api_keys.split(","):
            client_id, sep, secret = item.strip().partition(":")
            if sep and client_id and secret:
                pairs.append((client_id, secret))
        return pairs


@lru_cache
def get_settings() -> Settings:
    return Settings()
