import pytest
from story_forecaster.domain.scope import ForecastScope
from story_forecaster.domain.memory import EpistemicAttitude
from story_forecaster.memory.engine import NarrativeMemoryEngine

def test_memory_engine_snapshot():
    engine = NarrativeMemoryEngine()
    scope = ForecastScope(
        project_id="test_p",
        target_work_version_id="v1",
        target_max_discourse_seq=192
    )

    snapshot = engine.get_snapshot(scope)
    assert snapshot.through_discourse_seq == 192
    assert len(snapshot.active_threads) >= 3
    assert len(snapshot.epistemic_states) >= 4

    # Check Theory of Mind asymmetry:
    # Kazuma knows about the fairy blackmail, but Hachiman is IGNORANT
    kazuma_blackmail = next(
        e for e in snapshot.epistemic_states
        if e.character_id == "Сато Кадзума" and e.fact_key == "fairy_blackmail_threat"
    )
    hachiman_blackmail = next(
        e for e in snapshot.epistemic_states
        if e.character_id == "Хачиман Хикигая" and e.fact_key == "fairy_blackmail_threat"
    )

    assert kazuma_blackmail.attitude == EpistemicAttitude.KNOWN
    assert hachiman_blackmail.attitude == EpistemicAttitude.IGNORANT

def test_memory_engine_cutoff_filtering():
    engine = NarrativeMemoryEngine()
    # If scope cutoff is earlier (e.g. seq 120, before Kazuma was introduced at seq 182)
    early_scope = ForecastScope(
        project_id="test_p",
        target_work_version_id="v1",
        target_max_discourse_seq=120
    )
    snapshot = early_scope_snapshot = engine.get_snapshot(early_scope)
    thread_ids = [t.thread_id for t in snapshot.active_threads]
    # Kazuma fairy dust was introduced at seq 188, so it MUST NOT leak into seq 120!
    assert "thread_kazuma_fairy_dust" not in thread_ids
    assert "thread_horadric_crafting" not in thread_ids
    assert "Сато Кадзума" not in snapshot.active_characters
    assert "Фея" not in snapshot.active_characters
    assert snapshot.chapter_num <= 13

def test_memory_engine_zero_leakage_chapter_1():
    engine = NarrativeMemoryEngine()
    ch1_scope = ForecastScope(
        project_id="test_p",
        target_work_version_id="v1",
        target_max_discourse_seq=1
    )
    snap = engine.get_snapshot(ch1_scope)
    assert snap.chapter_num == 1
    assert "Сато Кадзума" not in snap.active_characters
    assert "Фея" not in snap.active_characters
    assert snap.active_characters["Хачиман Хикигая"]["active_subordinates"] == []
    assert snap.world_conditions["subordinate_dimension"] == "None (не открыта)"

