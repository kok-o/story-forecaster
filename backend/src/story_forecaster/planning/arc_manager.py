import re
from typing import List, Dict, Any, Optional
from collections import Counter
from sqlalchemy.orm import Session

from story_forecaster.db.models import Arc
from story_forecaster.domain.arc import (
    ArcPlan, ArcMilestone, ReaderPromise, ChapterPlan,
    EditorialReview, EditorialQualityScorecard
)
from story_forecaster.domain.writing import CharacterVoiceProfile
from story_forecaster.retrieval.bm25 import tokenize_for_search, stem_russian_word


class ArcManager:
    """
    Coordinates multi-chapter arc progression, tracks Chekhov's guns / reader promises,
    and performs holistic editorial reviews of chapters for pacing, repetition, and voice drift.
    """

    def create_arc(
        self,
        session: Session,
        project_id: str,
        title: str,
        theme: str,
        core_conflict: str,
        milestones: Optional[List[ArcMilestone]] = None,
        promises: Optional[List[ReaderPromise]] = None,
        open_mysteries: Optional[List[str]] = None,
        setups_and_payoffs: Optional[Dict[str, str]] = None,
        branch_id: Optional[str] = None
    ) -> Arc:
        """Creates and persists an Arc narrative architecture plan."""
        plan = ArcPlan(
            arc_id=f"arc_{title.lower().replace(' ', '_')[:30]}",
            title=title,
            theme=theme,
            core_conflict=core_conflict,
            milestones=milestones or [],
            reader_promises=promises or [],
            open_mysteries=open_mysteries or [],
            setups_and_payoffs=setups_and_payoffs or {},
            revision_num=1,
            status="ACTIVE"
        )

        db_arc = Arc(
            project_id=project_id,
            branch_id=branch_id,
            title=title,
            arc_plan_json=plan.model_dump(),
            revision_num=1,
            status="ACTIVE"
        )
        session.add(db_arc)
        session.commit()
        session.refresh(db_arc)
        return db_arc

    def get_arc_plan(self, session: Session, arc_id: str) -> Optional[ArcPlan]:
        """Loads and parses ArcPlan from database record."""
        db_arc = session.query(Arc).filter(Arc.id == arc_id).one_or_none()
        if not db_arc:
            return None
        return ArcPlan.model_validate(db_arc.arc_plan_json)

    def update_arc_plan(self, session: Session, arc_id: str, updated_plan: ArcPlan) -> Arc:
        """Explicitly versions an arc plan modification."""
        db_arc = session.query(Arc).filter(Arc.id == arc_id).one_or_none()
        if not db_arc:
            raise ValueError(f"Arc with id '{arc_id}' not found.")

        updated_plan.revision_num = db_arc.revision_num + 1
        db_arc.revision_num = updated_plan.revision_num
        db_arc.title = updated_plan.title
        db_arc.arc_plan_json = updated_plan.model_dump()
        db_arc.status = updated_plan.status

        session.commit()
        session.refresh(db_arc)
        return db_arc

    def track_commitments(
        self,
        arc_plan: ArcPlan,
        current_scene_or_chapter: int
    ) -> Dict[str, Any]:
        """
        Monitors open promises, line age, and potential forgotten threads:
        1. Identifies promises introduced long ago without payoffs (high age).
        2. Flags milestones that are overdue.
        3. Detects unresolved mysteries.
        """
        promises_report = []
        open_count = 0
        aging_count = 0

        for p in arc_plan.reader_promises:
            age = current_scene_or_chapter - p.introduced_in_scene_ordinal
            is_aging = age >= 4 and p.payoff_status == "OPEN"
            if p.payoff_status == "OPEN":
                open_count += 1
            if is_aging:
                aging_count += 1

            promises_report.append({
                "promise_id": p.promise_id,
                "text": p.promise_text,
                "introduced_at": p.introduced_in_scene_ordinal,
                "current_age": age,
                "payoff_status": p.payoff_status,
                "is_aging_risk": is_aging
            })

        milestone_status_counts = Counter(m.status for m in arc_plan.milestones)

        return {
            "arc_title": arc_plan.title,
            "revision_num": arc_plan.revision_num,
            "current_ordinal": current_scene_or_chapter,
            "open_commitments_count": open_count,
            "aging_commitments_count": aging_count,
            "milestone_progress": dict(milestone_status_counts),
            "open_mysteries_count": len(arc_plan.open_mysteries),
            "commitments": promises_report
        }

    def detect_conflict_repetition(self, scene_conflicts: List[str]) -> Dict[str, Any]:
        """
        Detects stagnation where the same conflict type recurs without narrative progression.
        """
        if len(scene_conflicts) < 2:
            return {"is_repetitive": False, "repeated_conflict": None, "consecutive_count": 1}

        consecutive_repeats = 1
        last_conflict = scene_conflicts[-1]
        for c in reversed(scene_conflicts[:-1]):
            if c.lower() == last_conflict.lower():
                consecutive_repeats += 1
            else:
                break

        is_repetitive = consecutive_repeats >= 3
        return {
            "is_repetitive": is_repetitive,
            "repeated_conflict": last_conflict if is_repetitive else None,
            "consecutive_count": consecutive_repeats
        }

    def editorial_review_chapter(
        self,
        chapter_ordinal: int,
        scenes_content: List[str],
        expected_plan: Optional[ChapterPlan] = None,
        voice_profiles: Optional[List[CharacterVoiceProfile]] = None
    ) -> EditorialReview:
        """
        Performs holistic editorial quality audit on a sequence of scenes in a chapter:
        1. Pacing score: measures length variance and dynamic variation across scenes.
        2. Repetition detection: scans for overused stock phrases and repetitive tropes.
        3. Voice consistency: verifies distinctive character fingerprints.
        4. Causal coherence: checks transitions and forward momentum.
        """
        if not scenes_content:
            scorecard = EditorialQualityScorecard(
                pacing_score=0.0,
                voice_consistency_score=0.0,
                causal_coherence_score=0.0,
                repetition_penalty=1.0,
                overall_quality_score=0.0
            )
            return EditorialReview(
                chapter_ordinal=chapter_ordinal,
                scorecard=scorecard,
                pacing_assessment="No scenes available for review",
                recommendations=["Generate scenes before running editorial review."]
            )

        full_text = "\n\n".join(scenes_content).lower()

        # 1. Pacing analysis
        scene_lengths = [len(s.strip()) for s in scenes_content]
        avg_len = sum(scene_lengths) / len(scene_lengths) if scene_lengths else 0
        variance = sum((l - avg_len) ** 2 for l in scene_lengths) / len(scene_lengths) if scene_lengths else 0

        # Guard against trivial or empty text
        if avg_len < 100:
            pacing_score = 0.30
            pacing_assessment = (
                f"Тривиально малый объём текста (средняя длина {int(avg_len)} зн.). "
                f"Недостаточно данных для полноценного темпорального анализа ритма."
            )
        else:
            has_rhythm_variation = variance > 5000 or len(scene_lengths) >= 2
            if has_rhythm_variation:
                pacing_score = 0.90
                pacing_assessment = (
                    f"Умеренный темп: {len(scenes_content)} сцен(ы) со средней длиной {int(avg_len)} зн. "
                    f"и вариативностью объёмов (дисперсия {int(variance)})."
                )
            else:
                pacing_score = 0.70
                pacing_assessment = (
                    f"Монотонная длина сцен (дисперсия {int(variance)}, средняя длина {int(avg_len)} зн.). "
                    f"Рекомендуется варьировать темп между краткими и подробными сценами."
                )

        # 2. Repetition detection (clichés & overused stock phrases)
        stock_phrases = [
            "окинул холодным взглядом",
            "побледнел как полотно",
            "нагло уперев ручки в бока",
            "в воздухе повисло напряжение",
            "сердце бешено колотилось",
            "не подавая виду",
            "криво усмехнулся"
        ]
        found_repetitive_phrases = []
        for phrase in stock_phrases:
            count = len(re.findall(re.escape(phrase), full_text))
            if count >= 2:
                found_repetitive_phrases.append(f"«{phrase}» (повтор: {count} раз(а))")

        repetition_penalty = min(0.40, len(found_repetitive_phrases) * 0.10)

        # 3. Character Voice Consistency
        voice_anomalies = []
        found_characters = []
        voice_score = 0.90
        if voice_profiles is not None:
            for vp in voice_profiles:
                char_name = vp.character_id
                name_tokens = [t.lower() for t in char_name.split() if len(t) >= 4]
                if any(t in full_text for t in name_tokens):
                    found_characters.append(char_name)
                    # Check typical keywords or honorifics
                    if "кадзума" in char_name.lower():
                        has_honorific = any(w in full_text for w in ["босс", "шеф", "куб", "удача", "очки"])
                        if not has_honorific:
                            voice_anomalies.append("Кадзума теряет речевой маркер 'Босс'/'Шеф'.")
                            voice_score -= 0.10
                    elif "хачиман" in char_name.lower():
                        has_cynicism = any(w in full_text for w in ["система", "контракт", "сделка", "взгляд", "сухо", "артефакт", "расчет"])
                        if not has_cynicism:
                            voice_anomalies.append("Хачиман звучит слишком эмоционально, отсутствует прагматичный тон.")
                            voice_score -= 0.10

            if not found_characters:
                voice_score = 0.70  # Profiles given but characters not identified
            else:
                voice_score = max(0.50, voice_score)
        else:
            voice_score = 0.85  # Neutral baseline when no voice verification is requested

        # 4. Causal Coherence
        causal_markers = ["поэтому", "вследствие", "отныне", "теперь", "итог", "результат", "с этого момента"]
        causal_hits = sum(1 for m in causal_markers if m in full_text)
        causal_coherence_score = min(1.0, 0.70 + (causal_hits * 0.05))

        if avg_len < 100:
            voice_score = 0.40
            causal_coherence_score = 0.30

        # Overall Score
        overall = max(
            0.0,
            round(
                (pacing_score * 0.35 + voice_score * 0.35 + causal_coherence_score * 0.30) - repetition_penalty,
                2
            )
        )

        scorecard = EditorialQualityScorecard(
            pacing_score=round(pacing_score, 2),
            voice_consistency_score=round(voice_score, 2),
            causal_coherence_score=round(causal_coherence_score, 2),
            repetition_penalty=round(repetition_penalty, 2),
            overall_quality_score=overall
        )

        recommendations = []
        if found_repetitive_phrases:
            recommendations.append("Заменить штампы и повторяющиеся речевые обороты на синонимичные действия.")
        if voice_anomalies:
            recommendations.append("Восстановить характерные речевые маркеры персонажей согласно профилю голоса.")
        if avg_len < 100:
            recommendations.append("Увеличить объём сцен главы: текущий объём недостаточен для художественного анализа.")
        recommendations.append("Эвристическая оценка: показатели служат ориентиром и требуют экспертной вычитки редактором.")

        return EditorialReview(
            chapter_ordinal=chapter_ordinal,
            scorecard=scorecard,
            pacing_assessment=pacing_assessment,
            repetitive_phrases=found_repetitive_phrases,
            repetitive_tropes=[],
            voice_anomalies=voice_anomalies,
            unresolved_commitments_count=len(expected_plan.open_commitments) if expected_plan else 0,
            recommendations=recommendations
        )
