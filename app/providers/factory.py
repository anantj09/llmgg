from app.config import Settings
from app.providers.base import ChatProvider
from app.providers.mock import MockProvider
from app.providers.openai_compatible import OpenAICompatibleProvider


def build_provider(settings: Settings) -> ChatProvider:
    if settings.provider == "mock":
        return MockProvider(latency_ms=settings.mock_latency_ms)
    if settings.provider == "openai_compatible":
        return OpenAICompatibleProvider(
            base_url=settings.upstream_base_url,
            api_key=settings.upstream_api_key,
            timeout_s=settings.upstream_timeout_s,
        )
    raise ValueError(f"Unknown provider '{settings.provider}'")
