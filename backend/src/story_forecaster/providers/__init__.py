from .base import BaseLLMProvider
from .demo import DemoProvider
from .gemini import GeminiProvider

def get_provider(prefer_gemini: bool = True) -> BaseLLMProvider:
    """Returns GeminiProvider if API key is active and configured, else DemoProvider."""
    if prefer_gemini:
        provider = GeminiProvider()
        if provider.is_available():
            return provider
    return DemoProvider()

__all__ = ["BaseLLMProvider", "DemoProvider", "GeminiProvider", "get_provider"]
