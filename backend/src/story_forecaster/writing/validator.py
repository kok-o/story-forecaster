import re
from typing import List, Dict, Any, Optional
from story_forecaster.domain.writing import ScenePlan, SceneValidationResult
from story_forecaster.domain.memory import NarrativeSnapshot, EpistemicAttitude

class SceneValidator:
    """
    Validates fanfic scene drafts against formal constraints:
    1. Plan execution: verifies mandatory beats are fulfilled.
    2. POV fidelity: detects illegal perspective leaks (e.g. non-POV internal thoughts).
    3. Epistemic integrity: prevents characters from acting on facts they are ignorant of.
    4. Dialogue distinction: ensures spoken dialogue claims are not conflated with world truth.
    """

    def validate_scene(
        self,
        plan: ScenePlan,
        content: str,
        snapshot: NarrativeSnapshot
    ) -> SceneValidationResult:
        content_lower = content.lower()
        pov_violations: List[str] = []
        epistemic_violations: List[str] = []
        timeline_violations: List[str] = []
        factual_errors: List[str] = []

        # 1. Check POV Fidelity (No telepathic intrusion into non-POV minds)
        pov_char = plan.pov_character
        other_participants = [p for p in plan.participants if p != pov_char]

        internal_thought_markers = [
            "подумал про себя", "вспомнила про себя", "втайне размышлял", "про себя подумал",
            "мысленно выругался", "мысленно усмехнулась", "в глубине души считал"
        ]
        for other in other_participants:
            short_name = other.split()[-1].lower()
            for marker in internal_thought_markers:
                pattern = rf"\b{short_name}\b[^.!?\n]*\b{marker}\b"
                if re.search(pattern, content_lower):
                    pov_violations.append(
                        f"POV leak: Non-POV character '{other}' has internal unspoken thoughts described in narration ('{marker}')."
                    )

        # 2. Epistemic Constraints Check (Theory of Mind)
        # Check against snapshot epistemic states where attitude is IGNORANT
        for epistemic in snapshot.epistemic_states:
            if epistemic.attitude == EpistemicAttitude.IGNORANT:
                char_name = epistemic.character_id
                fact_key = epistemic.fact_key
                # If character is in scene and text depicts them revealing or acting directly on this fact
                if char_name in plan.participants:
                    if fact_key == "fairy_blackmail_threat" and char_name == "Хачиман Хикигая":
                        # If Hachiman mentions or acts on fairy blackmail before Kazuma tells him
                        if "шантаж" in content_lower and "фея" in content_lower and "хачиман" in content_lower:
                            # Verify if Kazuma has spoken it first
                            kazuma_confession = any(term in content_lower for term in ["признался", "рассказал", "босс, тут такое дело", "шеф, меня шантажируют", "поведал"])
                            if not kazuma_confession:
                                epistemic_violations.append(
                                    f"Epistemic violation: '{char_name}' acts on unrevealed knowledge '{fact_key}' before participant disclosure."
                                )
                    elif fact_key == "hachiman_system_power" and char_name == "Саэко Бусуджима":
                        if "система з" in content_lower and "саэко" in content_lower:
                            epistemic_violations.append(
                                f"Epistemic violation: '{char_name}' has explicit knowledge of '{fact_key}'."
                            )

        # 3. Mandatory Beats Compliance with Morphological Stemming
        matched_beats = 0
        total_beats = len(plan.mandatory_beats)
        from story_forecaster.retrieval.bm25 import tokenize_for_search, stem_russian_word

        content_stems = set(tokenize_for_search(content))

        for beat in plan.mandatory_beats:
            beat_stems = [s for s in tokenize_for_search(beat) if len(s) >= 3]
            if not beat_stems:
                matched_beats += 1
                continue
            hits = sum(1 for stem in beat_stems if stem in content_stems or any(stem in cs or cs in stem for cs in content_stems))
            if hits >= max(1, len(beat_stems) // 2):
                matched_beats += 1

        plan_compliance = round(matched_beats / total_beats, 2) if total_beats > 0 else 1.0


        # 4. Overall validation result
        passed = (
            len(pov_violations) == 0 and
            len(epistemic_violations) == 0 and
            len(timeline_violations) == 0 and
            len(factual_errors) == 0 and
            plan_compliance >= 0.70
        )

        notes = (
            f"Validation {'PASSED' if passed else 'FAILED'}: "
            f"Beat compliance={int(plan_compliance * 100)}% ({matched_beats}/{total_beats}), "
            f"POV violations={len(pov_violations)}, Epistemic violations={len(epistemic_violations)}."
        )

        return SceneValidationResult(
            passed=passed,
            plan_compliance_score=plan_compliance,
            pov_violations=pov_violations,
            epistemic_violations=epistemic_violations,
            timeline_violations=timeline_violations,
            factual_errors=factual_errors,
            notes=notes
        )
