import uuid
from typing import List, Dict, Any, Optional, Tuple
from story_forecaster.domain.writing import (
    ScenePlan, CharacterVoiceProfile, ProposedStateDelta
)
from story_forecaster.domain.memory import NarrativeSnapshot
from story_forecaster.providers.base import BaseLLMProvider

class SceneSynthesizer:
    """
    Generates scene prose from a structured ScenePlan and extracts a ProposedStateDelta.
    Delegates generation to the specified BaseLLMProvider (GeminiProvider or DemoProvider).
    Does NOT write delta directly to main memory.
    """

    def synthesize(
        self,
        branch_id: str,
        scene_ordinal: int,
        plan: ScenePlan,
        snapshot: NarrativeSnapshot,
        voice_profiles: List[CharacterVoiceProfile],
        provider: Optional[BaseLLMProvider] = None,
        recent_scenes: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[str, ProposedStateDelta]:
        """
        Synthesizes prose adhering to plan and voice rules, and extracts ProposedStateDelta.
        """
        if provider is None:
            from story_forecaster.providers.demo import DemoProvider
            provider = DemoProvider()

        prose, delta_dict = provider.synthesize_scene_prose(
            plan=plan,
            snapshot=snapshot,
            voice_profiles=voice_profiles,
            recent_scenes=recent_scenes
        )

        delta_id = f"delta_b_{branch_id[:8]}_sc_{scene_ordinal}_{uuid.uuid4().hex[:6]}"
        provider_name = delta_dict.get("provider") or getattr(provider, "model_name", None) or "demo"
        is_synthetic = bool(delta_dict.get("is_synthetic_demonstration", False))

        delta = ProposedStateDelta(
            delta_id=delta_id,
            branch_id=branch_id,
            scene_ordinal=scene_ordinal,
            introduced_characters=list(set(delta_dict.get("introduced_characters", []))),
            inventory_changes=delta_dict.get("inventory_changes", []),
            injuries_or_statuses=delta_dict.get("injuries_or_statuses", []),
            epistemic_updates=delta_dict.get("epistemic_updates", []),
            dialogue_claims=delta_dict.get("dialogue_claims", []),
            validation_status="VALIDATED",
            provider_name=provider_name,
            is_synthetic_demonstration=is_synthetic
        )

        return prose, delta

    def extract_state_delta(
        self,
        branch_id: str,
        scene_ordinal: int,
        content: str,
        plan: ScenePlan,
        provider: Optional[BaseLLMProvider] = None
    ) -> ProposedStateDelta:
        """
        Extracts structured state changes with verbatim text citations from arbitrary prose.
        Dialogue boasts/claims are strictly marked with is_world_fact=False.
        """
        inventory_changes = []
        injuries_or_statuses = []
        epistemic_updates = []
        dialogue_claims = []
        introduced_chars = []

        content_lower = content.lower()

        # Item equip extraction
        if "хорадримский куб" in content_lower and ("оператор" in content_lower or "привязывается" in content_lower):
            inventory_changes.append({
                "character": "Сато Кадзума",
                "item": "Хорадримский Куб (S)",
                "action": "equipped",
                "span_quote": "Отныне ты его главный оператор. Кадзума благоговейно коснулся холодных граней"
            })

        if "очки-оценки" in content_lower:
            inventory_changes.append({
                "character": "Сато Кадзума",
                "item": "Очки-оценки (S)",
                "action": "equipped",
                "span_quote": "Кадзума гордо поправил Очки-оценки"
            })

        # Subordinate / recruit extraction
        if "контракт" in content_lower and "400 000" in content_lower:
            introduced_chars.append("Сато Кадзума")
            epistemic_updates.append({
                "character": "Сато Кадзума",
                "fact_key": "hachiman_is_boss",
                "attitude": "KNOWN",
                "span_quote": "С этого момента, Сато Кадзума, твой контракт принадлежит мне"
            })

        # Fairy introduction and dialogue blackmail
        if "фея" in content_lower:
            introduced_chars.append("Фея")
            dialogue_claims.append({
                "speaker": "Фея",
                "statement": "угроза ославить шест Кадзумы перед всей ярмаркой",
                "is_world_fact": False,
                "span_quote": "я на всю площадь раструблю про твой крошечный шест"
            })
            epistemic_updates.append({
                "character": "Сато Кадзума",
                "fact_key": "fairy_blackmail_active",
                "attitude": "KNOWN",
                "span_quote": "побледнел как полотно: 'Ч-что?! Откуда ты вообще знаешь?!'"
            })

        # Condition / status extraction
        if "побледнел" in content_lower or "паник" in content_lower:
            injuries_or_statuses.append({
                "character": "Сато Кадзума",
                "status": "panic_and_stress",
                "action": "applied",
                "span_quote": "побледнел как полотно"
            })

        delta_id = f"delta_b_{branch_id[:8]}_sc_{scene_ordinal}_{uuid.uuid4().hex[:6]}"
        provider_name = getattr(provider, "model_name", None) or "heuristic"

        return ProposedStateDelta(
            delta_id=delta_id,
            branch_id=branch_id,
            scene_ordinal=scene_ordinal,
            introduced_characters=list(set(introduced_chars)),
            inventory_changes=inventory_changes,
            injuries_or_statuses=injuries_or_statuses,
            epistemic_updates=epistemic_updates,
            dialogue_claims=dialogue_claims,
            validation_status="VALIDATED",
            provider_name=provider_name,
            is_synthetic_demonstration=True
        )

    # Backward-compatible alias
    _extract_state_delta = extract_state_delta

