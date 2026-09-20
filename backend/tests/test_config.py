import pytest
from story_forecaster.config import get_settings, AppSettings
from story_forecaster.providers import get_provider, ProviderUnavailableError

def test_config_loader_validation():
    settings = get_settings(reload=True)
    assert isinstance(settings, AppSettings)
    assert settings.app.name == "Story Forecaster"
    assert settings.llm.model == "gemini-3.8-flash"
    assert settings.llm.timeout_seconds > 0
    assert settings.retrieval.bm25_k1 > 0
    assert settings.forecast.min_desired_candidates >= 3

    # Test dictionary-like backwards compatibility
    assert settings.get("retrieval")["bm25_k1"] == settings.retrieval.bm25_k1
    assert settings["forecast"]["input_soft_cap_tokens"] == settings.forecast.input_soft_cap_tokens
    assert settings.get("non_existent_key", "default_val") == "default_val"

def test_provider_resolution_rules():
    # Demo provider
    p_demo = get_provider("demo")
    assert p_demo is not None

    # Auto fallback
    p_auto = get_provider("auto")
    assert p_auto is not None

    # Gemini without API key must raise ProviderUnavailableError
    with pytest.raises(ProviderUnavailableError) as exc_info:
        get_provider("gemini")
    assert "Gemini provider selected, but GEMINI_API_KEY is not set" in str(exc_info.value)

    # Unknown provider must raise ProviderUnavailableError
    with pytest.raises(ProviderUnavailableError) as exc_info2:
        get_provider("unsupported_provider_xyz")
    assert "Unknown provider" in str(exc_info2.value)
