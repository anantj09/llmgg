"""Application settings, loaded from environment variables (or a .env file)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "LLM Guardrail Gateway"
    log_level: str = "INFO"

    # Upstream LLM provider. "mock" needs no API key and is ideal for demos/tests.
    provider: str = "mock"  # mock | openai_compatible
    upstream_base_url: str = "https://api.groq.com/openai/v1"
    upstream_api_key: str = ""
    default_model: str = "openai/gpt-oss-20b"
    upstream_timeout_s: float = 60.0
    mock_latency_ms: int = 40

    # Guardrail policy and persistence
    policy_path: str = "policies/default.yaml"
    db_path: str = "data/gateway.db"

    # Comma-separated keys clients must send as "Authorization: Bearer <key>".
    # Leave empty to disable auth (local demo only).
    gateway_api_keys: str = ""

    # Pricing used for cost estimates (USD per 1K tokens)
    cost_per_1k_input: float = 0.000075
    cost_per_1k_output: float = 0.0003

    @property
    def api_keys(self) -> set[str]:
        return {k.strip() for k in self.gateway_api_keys.split(",") if k.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
