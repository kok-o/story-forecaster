import pytest
from story_forecaster.domain.scope import ForecastScope

def test_scope_discourse_boundary():
    scope = ForecastScope(
        project_id="p1",
        target_work_version_id="v1",
        target_max_discourse_seq=150,
        mode="retrospective"
    )
    assert scope.is_discourse_allowed(100) is True
    assert scope.is_discourse_allowed(150) is True
    assert scope.is_discourse_allowed(151) is False
    assert scope.is_discourse_allowed(200) is False

def test_scope_coverage_validation():
    scope = ForecastScope(
        project_id="p1",
        target_work_version_id="target_v1",
        target_max_discourse_seq=150
    )
    # Inside target work
    assert scope.validate_coverage("target_v1", 140) is True
    assert scope.validate_coverage("target_v1", 160) is False

    # External reference work (different version)
    assert scope.validate_coverage("author_v2", 500) is True

def test_scope_immutability():
    scope = ForecastScope(
        project_id="p1",
        target_work_version_id="v1",
        target_max_discourse_seq=150
    )
    with pytest.raises(Exception):
        scope.target_max_discourse_seq = 200

def test_scope_manifest_hash_uniqueness():
    s1 = ForecastScope(
        project_id="p1",
        target_work_version_id="v1",
        target_max_discourse_seq=150,
        allowed_author_manifest_id="manifest_a"
    )
    s2 = ForecastScope(
        project_id="p1",
        target_work_version_id="v1",
        target_max_discourse_seq=150,
        allowed_author_manifest_id="manifest_b"
    )
    assert s1.manifest_hash() != s2.manifest_hash()

