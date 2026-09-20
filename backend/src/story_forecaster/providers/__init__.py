from .base import BaseLLMProvider, ProviderUnavailableError
from .demo import DemoProvider
from .gemini import GeminiProvider

def get_provider(provider_name: str = "demo", prefer_gemini: bool = False) -> BaseLLMProvider:
    """
    Returns an LLM provider based on explicit choice or availability:
    - 'demo': Returns deterministic DemoProvider.
    - 'gemini': Returns GeminiProvider if available; raises ProviderUnavailableError if not.
    - 'auto': Returns GeminiProvider if available, otherwise falls back to DemoProvider.
    """
    name = (provider_name or "").lower().strip()
    if name == "gemini":
        provider = GeminiProvider()
        if not provider.is_available():
            raise ProviderUnavailableError(
                "Gemini provider selected, but GEMINI_API_KEY is not set or google-genai is not installed in the environment."
            )
        return provider
    elif name == "auto":
        if prefer_gemini:
            provider = GeminiProvider()
            if provider.is_available():
                return provider
        return DemoProvider()
    elif name == "demo" or not name:
        if prefer_gemini:
            provider = GeminiProvider()
            if provider.is_available():
                return provider
        return DemoProvider()
    else:
        raise ProviderUnavailableError(
            f"Unknown provider '{provider_name}'. Supported options are 'demo', 'gemini', or 'auto'."
        )

__all__ = ["BaseLLMProvider", "ProviderUnavailableError", "DemoProvider", "GeminiProvider", "get_provider"]
