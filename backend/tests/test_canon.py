import pytest
from story_forecaster.domain.canon import (
    ReferenceClassification,
    CanonRelation,
    EvidenceStatus,
    DependencyStatus,
    OccurrenceStatus,
    CanonOverlay
)

def test_canon_overlay_creation():
    overlay = CanonOverlay(
        element_id="event_fujimi_bus_escape",
        canon_universe="Highschool of the Dead",
        description="Прорыв выживших учеников на школьном автобусе",
        canon_relation=CanonRelation.MODIFIED,
        evidence_status=EvidenceStatus.EXPLICIT,
        dependency_status=DependencyStatus.NEEDS_REVIEW,
        occurrence_status=OccurrenceStatus.NOT_OBSERVED,
        supporting_refs=["chapter_04_scene_2"],
        known_from_seq=45
    )
    assert overlay.canon_relation == CanonRelation.MODIFIED
    assert overlay.dependency_status == DependencyStatus.NEEDS_REVIEW
    assert "chapter_04_scene_2" in overlay.supporting_refs
