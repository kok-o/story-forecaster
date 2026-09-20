from typing import List, Dict, Optional, Any
from ..domain.scope import ForecastScope
from ..domain.canon import (
    CanonOverlay,
    CanonRelation,
    EvidenceStatus,
    DependencyStatus,
    OccurrenceStatus,
    FanficModificationType
)

class CanonDivergenceRegistry:
    """
    Maintains the 5-state defeasible canon alignment registry for Highschool of the Dead (HOTD)
    and crossover lore (KonoSuba, DanMachi).
    Evaluates causality: fanfic actions alter prerequisites without canceling downstream
    events blindly, while separating reader knowledge from in-story protagonist awareness.
    """

    def __init__(self):
        self._overlays: List[CanonOverlay] = []
        self._initialize_canon_overlays()

    def _initialize_canon_overlays(self):
        self._overlays = [
            CanonOverlay(
                element_id="hotd_event_outbreak_gate",
                canon_universe="Highschool of the Dead",
                source_canon_ref="HOTD Manga Act 1: Spring of the Dead",
                description="Вспышка заражения у главных ворот Академии Фудзими, укус сторожа и гибель учителей",
                canon_relation=CanonRelation.MODIFIED,
                fanfic_modification_type=FanficModificationType.EXPLICIT_CHANGE,
                is_known_to_protagonist=True,
                version="v1.0",
                evidence_status=EvidenceStatus.INFERRED,
                dependency_status=DependencyStatus.NEEDS_REVIEW,
                occurrence_status=OccurrenceStatus.NOT_OBSERVED,
                supporting_refs=["chapter_16_scene_1"],
                source_spans=["ch16_sc1_span_40"],
                known_from_seq=140,
                notes="Выяснено, что зомби-апокалипсис порождается 'выбросом' переполненного данжа Фудзими. Хачиман зачищает мобов заранее, отодвигая или меняя условия выброса."
            ),
            CanonOverlay(
                element_id="hotd_event_fujimi_rooftop_stand",
                canon_universe="Highschool of the Dead",
                source_canon_ref="HOTD Manga Act 1: Spring of the Dead",
                description="Такаши Комуро и Рэй Миямото блокированы на крыше Фудзими; смерть и обращение Хисаси",
                canon_relation=CanonRelation.DEPENDS_ON_CHANGED_CONDITIONS,
                fanfic_modification_type=FanficModificationType.INFERRED_DIVERGENCE,
                is_known_to_protagonist=False,  # Protagonist does not micro-track rooftop students
                version="v1.0",
                evidence_status=EvidenceStatus.ABSENT,
                dependency_status=DependencyStatus.NEEDS_REVIEW,
                occurrence_status=OccurrenceStatus.NOT_OBSERVED,
                supporting_refs=["chapter_12_scene_3"],
                source_spans=["ch12_sc3_span_12"],
                known_from_seq=110,
                notes="Поскольку Хачиман поступил в Фудзими на год раньше и готовит укрепления/подчиненных, изоляция на крыше может не повториться в каноническом виде."
            ),
            CanonOverlay(
                element_id="hotd_char_saeko_busujima",
                canon_universe="Highschool of the Dead",
                source_canon_ref="HOTD Manga Act 2: Escape from the Dead",
                description="Саэко Бусуджима — капитан клуба кэндо, старшеклассница Фудзими",
                canon_relation=CanonRelation.PRESUMED_INTACT,
                fanfic_modification_type=FanficModificationType.ORIGINAL_UNTOUCHED,
                is_known_to_protagonist=True,  # Observed directly by Hachiman in the dojo
                version="v1.0",
                evidence_status=EvidenceStatus.EXPLICIT,
                dependency_status=DependencyStatus.VALID,
                occurrence_status=OccurrenceStatus.OBSERVED,
                supporting_refs=["chapter_12_scene_2", "chapter_16_scene_2"],
                source_spans=["ch12_sc2_span_88", "ch16_sc2_span_04"],
                known_from_seq=108,
                notes="Хачиман подтвердил ее присутствие в школе до апокалипсиса; характер и статус соответствуют канону."
            ),
            CanonOverlay(
                element_id="hotd_char_shizuka_marikawa",
                canon_universe="Highschool of the Dead",
                source_canon_ref="HOTD Manga Act 3: Democracy under the Dead",
                description="Сидзука Марикава — школьная медсестра с доступом к медикаментам и ключами от квартиры с Хаммером",
                canon_relation=CanonRelation.PRESUMED_INTACT,
                fanfic_modification_type=FanficModificationType.ORIGINAL_UNTOUCHED,
                is_known_to_protagonist=False,  # Known to reader lore, but Hachiman has not interacted with her yet
                version="v1.0",
                evidence_status=EvidenceStatus.INFERRED,
                dependency_status=DependencyStatus.VALID,
                occurrence_status=OccurrenceStatus.NOT_OBSERVED,
                supporting_refs=["chapter_12_scene_1"],
                source_spans=["ch12_sc1_span_19"],
                known_from_seq=106,
                notes="Школьный медпункт и персонал функционируют в обычном режиме мирного времени."
            ),
            CanonOverlay(
                element_id="hotd_event_takagi_estate_refuge",
                canon_universe="Highschool of the Dead",
                source_canon_ref="HOTD Manga Act 9: The Sword and the Dead",
                description="Эвакуация в укрепленное поместье Соитиро Такаги",
                canon_relation=CanonRelation.PRESUMED_INTACT,
                fanfic_modification_type=FanficModificationType.ORIGINAL_UNTOUCHED,
                is_known_to_protagonist=False,  # External reader knowledge; protagonist has own base
                version="v1.0",
                evidence_status=EvidenceStatus.ABSENT,
                dependency_status=DependencyStatus.VALID,
                occurrence_status=OccurrenceStatus.NOT_OBSERVED,
                supporting_refs=["chapter_12_scene_1"],
                source_spans=["ch12_sc1_span_05"],
                known_from_seq=106,
                notes="Поместье Такаги существует как одна из мощнейших политических баз города; Хачиман упоминает статус Такаги в главе 12."
            ),
            CanonOverlay(
                element_id="konosuba_char_kazuma_luck",
                canon_universe="KonoSuba: God's Blessing on this Wonderful World!",
                source_canon_ref="KonoSuba Light Novel Vol 1, Prologue",
                description="Сато Кадзума — хикикомори с колоссальным показателем скрытого параметра Удачи",
                canon_relation=CanonRelation.CONFIRMED,
                fanfic_modification_type=FanficModificationType.EXPLICIT_CHANGE,
                is_known_to_protagonist=True,
                version="v1.0",
                evidence_status=EvidenceStatus.EXPLICIT,
                dependency_status=DependencyStatus.VALID,
                occurrence_status=OccurrenceStatus.OBSERVED,
                supporting_refs=["chapter_22_scene_1"],
                source_spans=["ch22_sc1_span_20"],
                known_from_seq=182,
                notes="Хачиман целенаправленно находит и выкупает Кадзуму за 400 000 золота именно из-за 100% удачи для крафта."
            )
        ]

    def get_overlays(self, scope: ForecastScope) -> List[CanonOverlay]:
        """Returns all canon alignments established within the allowed scope boundary."""
        return [
            o for o in self._overlays
            if o.known_from_seq <= scope.target_max_discourse_seq
        ]

    def get_divergence_summary(self, scope: ForecastScope) -> Dict[str, Any]:
        """Produces a structured statistical summary of canon alignment."""
        overlays = self.get_overlays(scope)
        counts = {
            "CONFIRMED": 0,
            "MODIFIED": 0,
            "PRESUMED_INTACT": 0,
            "DEPENDS_ON_CHANGED_CONDITIONS": 0,
            "UNKNOWN": 0
        }
        for o in overlays:
            counts[o.canon_relation.value] = counts.get(o.canon_relation.value, 0) + 1

        return {
            "total_canon_elements_tracked": len(overlays),
            "distribution": counts,
            "elements": [o.model_dump() for o in overlays]
        }
