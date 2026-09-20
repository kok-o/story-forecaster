import json
import pytest
from unittest.mock import MagicMock
from story_forecaster.providers.gemini import GeminiProvider
from story_forecaster.domain.scope import ForecastScope
from story_forecaster.domain.forecast import ForecastResult, PredictionCandidate, ChapterTopology, PlotBeat, NarrativeMode

def test_gemini_provider_unconfigured_raises_error():
    provider = GeminiProvider(api_key=None)
    # Ensure client is None
    provider.client = None
    assert provider.is_available() is False

    scope = ForecastScope(
        project_id="proj_1",
        target_work_version_id="ver_1",
        target_max_discourse_seq=184
    )

    with pytest.raises(RuntimeError) as exc_info:
        provider.generate_hypotheses(
            scope=scope,
            target_context={"chapter_num": 22},
            author_precedents=[],
            canon_context=[]
        )
    assert "Gemini provider requested, but GEMINI_API_KEY is not configured" in str(exc_info.value)

def test_gemini_provider_prompt_assembly():
    provider = GeminiProvider(api_key="test-api-key")
    scope = ForecastScope(
        project_id="proj_1",
        target_work_version_id="ver_1",
        target_max_discourse_seq=184
    )
    target_context = {
        "chapter_num": 22,
        "discourse_seq": 184,
        "characters": ["Хачиман Хикигая", "Юкиносита Юкино"],
        "world_conditions": {"weather": "rain"},
        "active_threads": [{"thread_id": "thread_crafting"}],
        "epistemic_states": [{"character": "Хачиман Хикигая", "known_facts": ["Куб готов"], "false_beliefs": []}],
        "recent_scenes": [{"chapter_ordinal": 22, "discourse_seq": 184, "summary": "Хачиман активирует руны."}],
        "retrieved_excerpts": [{"chapter_ordinal": 5, "snippet": "Первая встреча с торговцем."}]
    }
    author_precedents = [{"abstract_situation": "Шантаж", "author_resolution": "Торг"}]
    canon_context = [{"entity_id": "cube", "defeasible_status": "CANONICAL"}]

    sys_instruction, prompt = provider.build_forecast_prompt(
        scope=scope,
        target_context=target_context,
        author_precedents=author_precedents,
        canon_context=canon_context,
        num_candidates=2
    )

    assert "Хачиман активирует руны" in prompt
    assert "Первая встреча с торговцем" in prompt
    assert "Шантаж" in prompt
    assert "CANONICAL" in prompt
    assert "ZERO-FUTURE-LEAKAGE" in sys_instruction

def test_gemini_provider_with_mock_client():
    provider = GeminiProvider(api_key="mock-key")
    mock_client = MagicMock()
    provider.client = mock_client

    sample_cand = {
        "candidate_id": "gemini_hyp_1",
        "title": "Новый путь развития",
        "topology": {
            "pov_character": "Хачиман Хикигая",
            "narrative_mode": "ACTION",
            "is_direct_continuation": True,
            "focal_thread_id": "thread_crafting",
            "estimated_pacing": "fast"
        },
        "key_events": [
            {
                "ordinal": 1,
                "summary": "Хачиман тестирует руны в безопасной зоне.",
                "participants": ["Хачиман Хикигая"],
                "conflict_type": "Эксперимент",
                "epistemic_change": "Обнаружены новые свойства."
            }
        ],
        "character_motivations": {"Хачиман Хикигая": "Безопасность"},
        "potential_twist": None,
        "confidence_label": "High",
        "rationale": "Логично следует из предыдущей сцены.",
        "assumptions": [],
        "continuity_verified": False,
        "continuity_status": "not_checked",
        "verification_notes": None
    }

    mock_result_json = json.dumps({
        "target_work": "work_1",
        "cutoff_chapter": 22,
        "candidates": [sample_cand],
        "author_precedent_citations": ["Шантаж"],
        "generated_at_utc": "2026-09-20T21:00:00Z",
        "scope_manifest_hash": "placeholder_hash",
        "provider": "gemini-3.8-flash",
        "is_synthetic_demonstration": False
    })

    mock_response = MagicMock()
    mock_response.text = mock_result_json
    mock_client.models.generate_content.return_value = mock_response

    scope = ForecastScope(
        project_id="proj_1",
        target_work_version_id="ver_1",
        target_max_discourse_seq=184
    )

    res = provider.generate_hypotheses(
        scope=scope,
        target_context={"chapter_num": 22},
        author_precedents=[],
        canon_context=[],
        num_candidates=1
    )

    assert res.provider == "gemini-3.8-flash"
    assert res.is_synthetic_demonstration is False
    assert len(res.candidates) == 1
    assert res.candidates[0].candidate_id == "gemini_hyp_1"
    assert res.scope_manifest_hash == scope.manifest_hash()
