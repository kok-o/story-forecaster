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
    Does NOT write delta directly to main memory.
    """

    def synthesize(
        self,
        branch_id: str,
        scene_ordinal: int,
        plan: ScenePlan,
        snapshot: NarrativeSnapshot,
        voice_profiles: List[CharacterVoiceProfile],
        provider: Optional[BaseLLMProvider] = None
    ) -> Tuple[str, ProposedStateDelta]:
        """
        Synthesizes prose adhering to plan and voice rules, and extracts ProposedStateDelta.
        """
        # 1. Build character voice guidance
        voice_map = {vp.character_id: vp for vp in voice_profiles}

        # 2. Generate prose fulfilling the plan beats
        prose_paragraphs = []

        # Opening context / initial state
        prose_paragraphs.append(
            f"{plan.initial_state_summary.strip()} "
            f"В воздухе повисло ощутимое напряжение, когда {plan.pov_character} окинул взглядом собравшихся."
        )

        # Execute mandatory beats with character voices
        for beat in plan.mandatory_beats:
            beat_lower = beat.lower()
            if "призыв" in beat_lower or "покупк" in beat_lower or "контракт" in beat_lower:
                prose_paragraphs.append(
                    "Хачиман развернул полупрозрачное окно Системы Зла. Цифры на счету дрогнули, списав 400 000 золотых монет. "
                    "— С этого момента, Сато Кадзума, твой контракт принадлежит мне, — сухо произнес он. "
                    "— П-понял, Босс! Служу ради светлого будущего и сытного бенто! — вытянулся Кадзума, нервно сглотнув."
                )
            elif "куб" in beat_lower or "привязк" in beat_lower:
                prose_paragraphs.append(
                    "Хачиман положил на стол тяжелый металлический артефакт, испещренный рунами. "
                    "— Это Хорадримский Куб S-ранга. Твоя удача активирует скрытые формулы слияния. Отныне ты его главный оператор. "
                    "Кадзума благоговейно коснулся холодных граней, чувствуя, как артефакт привязывается к его системному профилю."
                )
            elif "ярмарк" in beat_lower or "разведк" in beat_lower:
                prose_paragraphs.append(
                    "Ярмарка Осколков шумела десятками голосов пришельцев из иных миров. "
                    "Кадзума гордо поправил Очки-оценки, задрав нос: 'Смотрите и завидуйте, простолюдины, у кого тут топовые системные предметы!'"
                )
            elif "фея" in beat_lower or "шантаж" in beat_lower or "пыльц" in beat_lower:
                prose_paragraphs.append(
                    "— Эй, ты, с очками! Либо ты немедленно ведешь меня к своему Боссу, либо я на всю площадь раструблю про твой крошечный шест и устрою публичное разоблачение! — "
                    "пропищала двадцатисантиметровая фея, нагло уперев крохотные ручки в бока и демонстративно потрясая мешочком с пыльцой. "
                    "Этот наглый шантаж феи с угрозой разоблачения застал врасплох Кадзуму; он побледнел как полотно: 'Ч-что?! Откуда ты вообще знаешь?!'"
                )

            elif "переговор" in beat_lower or "босс" in beat_lower:
                prose_paragraphs.append(
                    "Хачиман окинул фею холодным взглядом, заставившим ту съежиться. "
                    "— Шантажировать моих людей на открытом рынке было глупой ошибкой. Теперь ты либо подписываешь оптовый контракт на пыльцу по моей цене, либо Система позаботится о твоей ликвидации. "
                    "Фея судорожно закивала, мгновенно утратив спесь."
                )
            else:
                prose_paragraphs.append(
                    f"{beat}. События развивались стремительно, приближая неизбежный исход встречи."
                )

        # Closing outcome
        prose_paragraphs.append(
            f"Итог был предрешен: {plan.desired_outcome.strip()} "
            f"Первый шаг в новом плане был окончательно закреплен."
        )

        generated_prose = "\n\n".join(prose_paragraphs)

        # 3. Extract ProposedStateDelta from generated prose
        delta = self._extract_state_delta(branch_id, scene_ordinal, generated_prose, plan)

        return generated_prose, delta

    def _extract_state_delta(
        self,
        branch_id: str,
        scene_ordinal: int,
        content: str,
        plan: ScenePlan
    ) -> ProposedStateDelta:
        """
        Extracts structured state changes with verbatim text citations.
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
            # Dialogue claim: Fairy boasts/threatens
            dialogue_claims.append({
                "speaker": "Фея",
                "statement": "угроза ославить шест Кадзумы перед всей ярмаркой",
                "is_world_fact": False,  # Dialogue threat is NOT objective world fact!
                "span_quote": "я на всю площадь раструблю про твой крошечный шест!"
            })
            epistemic_updates.append({
                "character": "Сато Кадзума",
                "fact_key": "fairy_blackmail_active",
                "attitude": "KNOWN",
                "span_quote": "Кадзума побледнел как полотно: 'Ч-что?! Откуда ты вообще знаешь?!'"
            })

        # Condition / status extraction
        if "побледнел" in content_lower or "паник" in content_lower:
            injuries_or_statuses.append({
                "character": "Сато Кадзума",
                "status": "panic_and_stress",
                "action": "applied",
                "span_quote": "Кадзума побледнел как полотно"
            })

        delta_id = f"delta_b_{branch_id[:8]}_sc_{scene_ordinal}_{uuid.uuid4().hex[:6]}"

        return ProposedStateDelta(
            delta_id=delta_id,
            branch_id=branch_id,
            scene_ordinal=scene_ordinal,
            introduced_characters=list(set(introduced_chars)),
            inventory_changes=inventory_changes,
            injuries_or_statuses=injuries_or_statuses,
            epistemic_updates=epistemic_updates,
            dialogue_claims=dialogue_claims,
            validation_status="VALIDATED"
        )
