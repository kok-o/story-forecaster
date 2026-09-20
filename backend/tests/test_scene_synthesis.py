import pytest
from typing import Dict, Any, List, Optional, Tuple
from fastapi.testclient import TestClient

from story_forecaster.api.main import app
from story_forecaster.providers.base import BaseLLMProvider, ProviderUnavailableError
from story_forecaster.providers.demo import DemoProvider
from story_forecaster.providers.gemini import GeminiProvider
from story_forecaster.domain.writing import (
    ScenePlan, CharacterVoiceProfile, SceneSynthesisOutput, ProposedStateDelta
)
from story_forecaster.domain.memory import NarrativeSnapshot
from story_forecaster.domain.scope import ForecastScope
from story_forecaster.domain.forecast import ForecastResult
from story_forecaster.domain.canon import ReferenceClassification
from story_forecaster.writing.synthesizer import SceneSynthesizer

@pytest.fixture
def client():
    return TestClient(app)

class MockCustomLLMProvider(BaseLLMProvider):
    """Mock LLM provider returning realistic synthetic prose and structured deltas."""
    model_name = "mock-llm-prose-v1"

    def generate_hypotheses(
        self,
        scope: ForecastScope,
        target_context: Dict[str, Any],
        author_precedents: List[Dict[str, Any]],
        canon_context: List[Dict[str, Any]],
        num_candidates: int = 3
    ) -> ForecastResult:
        raise NotImplementedError

    def classify_reference(self, entity_text: str, context_sentence: str) -> ReferenceClassification:
        return ReferenceClassification.PRIMARY_CANON

    def synthesize_scene_prose(
        self,
        plan: ScenePlan,
        snapshot: NarrativeSnapshot,
        voice_profiles: List[CharacterVoiceProfile],
        recent_scenes: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[str, Dict[str, Any]]:
        prose = (
            "Хачиман стоял посреди полутемного зала склада, внимательно наблюдая за реакцией собеседников. "
            "На столе лежал тяжелый свиток договора с золотым тиснением. "
            "— Если ты соглашаешься на эти условия, обратного пути не будет, — произнес Хачиман ровным голосом. "
            "Кадзума нервно усмехнулся и вытащил из кармана зачарованный кинжал. "
            "— У меня и так не было выбора, так что я беру зачарованный кинжал теней в правую руку, — ответил он."
        )
        delta_dict = {
            "introduced_characters": ["Хачиман Хикигая", "Сато Кадзума"],
            "inventory_changes": [
                {
                    "character": "Сато Кадзума",
                    "item": "зачарованный кинжал теней",
                    "action": "equipped",
                    "span_quote": "я беру зачарованный кинжал теней в правую руку"
                }
            ],
            "injuries_or_statuses": [],
            "epistemic_updates": [
                {
                    "character": "Сато Кадзума",
                    "fact_key": "contract_finalized",
                    "attitude": "KNOWN",
                    "span_quote": "Если ты соглашаешься на эти условия, обратного пути не будет"
                }
            ],
            "dialogue_claims": [],
            "is_synthetic_demonstration": False,
            "provider": self.model_name
        }
        return prose, delta_dict

def make_dummy_snapshot(active_characters=None, epistemic_states=None) -> NarrativeSnapshot:
    return NarrativeSnapshot(
        chapter_num=22,
        through_discourse_seq=182,
        active_threads=[],
        epistemic_states=epistemic_states or [],
        active_characters=active_characters or {},
        world_conditions={},
        snapshot_hash="test_snap_hash"
    )

def test_scene_synthesizer_delegates_to_provider():
    plan = ScenePlan(
        scene_goal="Заключение тайного соглашения на складе",
        pov_character="Хачиман Хикигая",
        participants=["Хачиман Хикигая", "Сато Кадзума"],
        initial_state_summary="В полутемном зале склада тихо.",
        mandatory_beats=["Озвучивание условий контракта", "Принятие условий Кадзумой"],
        desired_outcome="Контракт подписан",
        target_pacing="medium",
        target_length_chars=2000
    )
    snapshot = make_dummy_snapshot()
    vp = CharacterVoiceProfile(
        character_id="Хачиман Хикигая",
        vocabulary_tone="cynical-pragmatic",
        typical_sentence_length="compound",
        dialogue_mannerisms=["сухо произнес", "пожал плечами"]
    )

    mock_provider = MockCustomLLMProvider()
    synthesizer = SceneSynthesizer()

    prose, delta = synthesizer.synthesize(
        branch_id="test_branch_123",
        scene_ordinal=1,
        plan=plan,
        snapshot=snapshot,
        voice_profiles=[vp],
        provider=mock_provider
    )

    assert "зачарованный кинжал теней" in prose
    assert delta.provider_name == "mock-llm-prose-v1"
    assert delta.is_synthetic_demonstration is False
    assert len(delta.inventory_changes) == 1
    assert delta.inventory_changes[0]["item"] == "зачарованный кинжал теней"
    # Verbatim quote verification
    assert delta.inventory_changes[0]["span_quote"] in prose

def test_demo_provider_synthesis_verbatim_quotes():
    plan = ScenePlan(
        scene_goal="Призыв Сато Кадзумы",
        pov_character="Хачиман Хикигая",
        participants=["Хачиман Хикигая", "Сато Кадзума"],
        initial_state_summary="В комнате мерцает меню Системы Зла.",
        mandatory_beats=[
            "Покупка контракта Сато Кадзумы через Систему за 400 000 золотых",
            "Привязка Хорадримского Куба S-ранга к Кадзуме"
        ],
        desired_outcome="Кадзума нанят и принял привязку артефакта.",
        target_pacing="medium",
        target_length_chars=2500
    )
    snapshot = make_dummy_snapshot()

    synthesizer = SceneSynthesizer()
    prose, delta = synthesizer.synthesize(
        branch_id="test_demo_branch",
        scene_ordinal=1,
        plan=plan,
        snapshot=snapshot,
        voice_profiles=[],
        provider=DemoProvider()
    )

    assert delta.is_synthetic_demonstration is True
    assert delta.provider_name == "demo"
    assert len(delta.inventory_changes) >= 1

    # Check all quotes exist verbatim in generated prose
    for inv in delta.inventory_changes:
        assert inv["span_quote"] in prose

    for ep in delta.epistemic_updates:
        assert ep["span_quote"] in prose

def test_gemini_prompt_builder_scene_synthesis_constraints():
    provider = GeminiProvider(api_key="test-api-key-xyz")
    plan = ScenePlan(
        scene_goal="Разведка рынка и вербовка",
        pov_character="Хачиман Хикигая",
        participants=["Хачиман Хикигая", "Фея"],
        initial_state_summary="Шумная ярмарка.",
        known_information={"Хачиман Хикигая": ["рыночные цены"], "Фея": ["секреты пыльцы"]},
        mandatory_beats=["Поиск редких ингредиентов", "Шантаж феи с угрозой"],
        permitted_changes=["приобретение пыльцы"],
        desired_outcome="Сделка заключена",
        target_pacing="fast",
        target_length_chars=3000
    )
    snapshot = make_dummy_snapshot(
        active_characters={
            "Сато Кадзума": {
                "inventory": ["Хорадримский Куб (S)"],
                "statuses": ["panic_and_stress"]
            }
        }
    )
    vp = CharacterVoiceProfile(
        character_id="Фея",
        vocabulary_tone="high-pitched-arrogant",
        typical_sentence_length="short",
        dialogue_mannerisms=["пропищала", "нагло уперев ручки в бока"],
        author_tuning_rationale="N.B. fairy characterisation"
    )

    system_instruction, prompt = provider.build_scene_synthesis_prompt(
        plan=plan,
        snapshot=snapshot,
        voice_profiles=[vp]
    )

    # 1. Check system instructions guardrails
    assert "POINT OF VIEW INTEGRITY" in system_instruction
    assert "EPISTEMIC INTEGRITY (THEORY OF MIND)" in system_instruction
    assert "CHARACTER VOICES" in system_instruction
    assert "VERBATIM" in system_instruction
    assert "dialogue_claims" in system_instruction

    # 2. Check prompt contents
    assert "Хачиман Хикигая" in prompt
    assert "Разведка рынка и вербовка" in prompt
    assert "Фея" in prompt
    assert "high-pitched-arrogant" in prompt
    assert "Хорадримский Куб (S)" in prompt

def test_api_draft_scene_fail_fast_on_missing_gemini(client, monkeypatch):
    # Ensure GEMINI_API_KEY is unset so GeminiProvider is unavailable
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    # 1. Create a branch
    res_b = client.post("/api/writing/branches", json={
        "branch_name": "API Fail Fast Test Branch",
        "cutoff_discourse_seq": 182
    })
    assert res_b.status_code == 200
    branch_id = res_b.json()["id"]

    # 2. Attempt drafting with provider_name='gemini'
    res_draft = client.post(f"/api/writing/branches/{branch_id}/draft", json={
        "scene_ordinal": 1,
        "title": "Unconfigured Gemini Scene",
        "provider_name": "gemini",
        "plan": {
            "scene_goal": "Goal",
            "pov_character": "Хачиман Хикигая",
            "participants": ["Хачиман Хикигая"],
            "initial_state_summary": "Initial",
            "mandatory_beats": ["Beat 1"],
            "desired_outcome": "Outcome",
            "target_pacing": "medium",
            "target_length_chars": 2000
        }
    })

    # Must fail-fast with 400 Bad Request, NOT silently falling back to demo!
    assert res_draft.status_code == 400
    detail = res_draft.json().get("detail", "")
    assert "gemini" in detail.lower() or "unavailable" in detail.lower()

def test_api_draft_scene_succeeds_with_explicit_demo(client):
    res_b = client.post("/api/writing/branches", json={
        "branch_name": "API Explicit Demo Test Branch",
        "cutoff_discourse_seq": 182
    })
    assert res_b.status_code == 200
    branch_id = res_b.json()["id"]

    res_draft = client.post(f"/api/writing/branches/{branch_id}/draft", json={
        "scene_ordinal": 1,
        "title": "Explicit Demo Scene",
        "provider_name": "demo",
        "plan": {
            "scene_goal": "Призыв Сато Кадзумы",
            "pov_character": "Хачиман Хикигая",
            "participants": ["Хачиман Хикигая", "Сато Кадзума"],
            "initial_state_summary": "В комнате мерцает меню Системы Зла.",
            "mandatory_beats": [
                "Покупка контракта Сато Кадзумы через Систему за 400 000 золотых",
                "Привязка Хорадримского Куба S-ранга к Кадзуме"
            ],
            "desired_outcome": "Кадзума нанят и принял привязку артефакта.",
            "target_pacing": "medium",
            "target_length_chars": 2500
        }
    })

    assert res_draft.status_code == 200
    data = res_draft.json()
    assert data["status"] == "DRAFT"
    delta = data["proposed_state_delta"]
    assert delta["is_synthetic_demonstration"] is True
    assert delta["provider_name"] == "demo"
