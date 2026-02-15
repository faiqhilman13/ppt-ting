from app.config import settings
from app.providers.anthropic_provider import AnthropicProvider
from app.providers.base import BaseLLMProvider
from app.providers.mock_provider import MockProvider
from app.providers.openai_provider import OpenAIProvider


def get_provider(name: str | None = None) -> BaseLLMProvider:
    candidate = (name or settings.default_llm_provider).lower()

    if candidate == "openai" and settings.openai_api_key:
        return OpenAIProvider(settings.openai_api_key)
    if candidate == "anthropic" and settings.anthropic_api_key:
        return AnthropicProvider(settings.anthropic_api_key)

    return MockProvider()
