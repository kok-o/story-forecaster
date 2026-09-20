import pytest
from story_forecaster.domain.scope import ForecastScope
from story_forecaster.domain.canon import CanonRelation
from story_forecaster.canon.registry import CanonDivergenceRegistry

def test_canon_divergence_registry():
    registry = CanonDivergenceRegistry()
    scope = ForecastScope(
        project_id="p1",
        target_work_version_id="v1",
        target_max_discourse_seq=192
    )

    overlays = registry.get_overlays(scope)
    assert len(overlays) >= 5

    summary = registry.get_divergence_summary(scope)
    assert summary["total_canon_elements_tracked"] >= 5
    assert summary["distribution"]["MODIFIED"] >= 1
    assert summary["distribution"]["DEPENDS_ON_CHANGED_CONDITIONS"] >= 1
    assert summary["distribution"]["PRESUMED_INTACT"] >= 2

def test_canon_registry_cutoff():
    registry = CanonDivergenceRegistry()
    early_scope = ForecastScope(
        project_id="p1",
        target_work_version_id="v1",
        target_max_discourse_seq=100  # Before Fujimi events (seq 106+)
    )
    overlays = registry.get_overlays(early_scope)
    # Elements known from seq > 100 must be filtered out
    assert len(overlays) == 0
