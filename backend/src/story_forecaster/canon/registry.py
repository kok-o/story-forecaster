from typing import List, Dict, Optional, Any
from ..domain.scope import ForecastScope
from ..domain.canon import (
    CanonOverlay,
    CanonRelation,
    EvidenceStatus,
    DependencyStatus,
    OccurrenceStatus,
    ReferenceClassification
)

class CanonDivergenceRegistry:
    """
    Maintains the 5-state defeasible canon alignment registry for Highschool of the Dead (HOTD).
    Evaluates causality: fanfic actions alter prerequisites without canceling downstream
    events blindly, using the 4 orthogonal axes.
    """

    def __init__(self):
        self._overlays: List[CanonOverlay] = []
        self._initialize_hotd_canon()

    def _initialize_hotd_canon(self):
        self._overlays = [
            CanonOverlay(
                element_id="hotd_event_outbreak_gate",
                canon_universe="Highschool of the Dead (Manga / Anime)",
                description="Вспышка заражения у главных ворот Академии Фудзими, укус сторожа и гибель учителей",
                canon_relation=CanonRelation.MODIFIED,
                evidence_status=EvidenceStatus.INFERRED,
                dependency_status=DependencyStatus.NEEDS_REVIEW,
                occurrence_status=OccurrenceStatus.NOT_OBSERVED,
                supporting_refs=["chapter_16_scene_1"],
                known_from_seq=140,
                notes="Выяснено, что зомби-апокалипсис порождается 'выбросом' переполненного данжа Фудзими. Хачиман зачищает мобов заранее, отодвигая или меняя условия выброса."
            ),
            CanonOverlay(
                element_id="hotd_event_fujimi_rooftop_stand",
                canon_universe="Highschool of the Dead",
                description="Такаши Комуро и Рэй Миямото блокированы на крыше Фудзими; смерть и обращение Хисаси",
                canon_relation=CanonRelation.DEPENDS_ON_CHANGED_CONDITIONS,
                evidence_status=EvidenceStatus.ABSENT,
                dependency_status=DependencyStatus.NEEDS_REVIEW,
                occurrence_status=OccurrenceStatus.NOT_OBSERVED,
                supporting_refs=["chapter_12_scene_3"],
                known_from_seq=110,
                notes="Поскольку Хачиман поступил в Фудзими на год раньше и готовит укрепления/подчиненных, изоляция на крыше может не повториться в каноническом виде."
            ),
            CanonOverlay(
                element_id="hotd_char_saeko_busujima",
                canon_universe="Highschool of the Dead",
                description="Саэко Бусуджима — капитан клуба кэндо, старшеклассница Фудзими",
                canon_relation=CanonRelation.PRESUMED_INTACT,
                evidence_status=EvidenceStatus.EXPLICIT,
                dependency_status=DependencyStatus.VALID,
                occurrence_status=OccurrenceStatus.OBSERVED,
                supporting_refs=["chapter_12_scene_2", "chapter_16_scene_2"],
                known_from_seq=108,
                notes="Хачиман подтвердил ее присутствие в школе до апокалипсиса; характер и статус соответствуют канону."
            ),
            CanonOverlay(
                element_id="hotd_char_shizuka_marikawa",
                canon_universe="Highschool of the Dead",
                description="Сидзука Марикава — школьная медсестра с доступом к медикаментам и ключами от квартиры с Хаммером",
                canon_relation=CanonRelation.PRESUMED_INTACT,
                evidence_status=EvidenceStatus.INFERRED,
                dependency_status=DependencyStatus.VALID,
                occurrence_status=OccurrenceStatus.NOT_OBSERVED,
                supporting_refs=["chapter_12_scene_1"],
                known_from_seq=106,
                notes="Школьный медпункт и персонал функционируют в обычном режиме мирного времени."
            ),
            CanonOverlay(
                element_id="hotd_event_takagi_estate_refuge",
                canon_universe="Highschool of the Dead",
                description="Эвакуация в укрепленное поместье Соитиро Такаги",
                canon_relation=CanonRelation.PRESUMED_INTACT,
                evidence_status=EvidenceStatus.ABSENT,
                dependency_status=DependencyStatus.VALID,
                occurrence_status=OccurrenceStatus.NOT_OBSERVED,
                supporting_refs=["chapter_12_scene_1"],
                known_from_seq=106,
                notes="Поместье Такаги существует как одна из мощнейших политических баз города; Хачиман упоминает статус Такаги в главе 12."
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
            counts[o.canon_relation.value] += 1

        return {
            "total_canon_elements_tracked": len(overlays),
            "distribution": counts,
            "elements": [o.model_dump() for o in overlays]
        }
