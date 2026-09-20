import pytest
from story_forecaster.db.session import SessionLocal
from story_forecaster.db.models import (
    Project, Work, WorkVersion, Chapter, Scene, Branch, BranchScene, AsyncTask
)
from story_forecaster.domain.scope import ForecastScope
from story_forecaster.domain.resolver import resolve_scope
from story_forecaster.domain.forecast import PredictionCandidate, ChapterTopology, PlotBeat
from story_forecaster.domain.memory import CharacterEpistemicState, EpistemicAttitude
from story_forecaster.domain.writing import ScenePlan
from story_forecaster.writing.branch_service import BranchService
from story_forecaster.forecast.engine import ForecastEngine
from story_forecaster.providers.gemini import GeminiProvider
from story_forecaster.tasks.queue import TaskQueue


@pytest.fixture
def clean_db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def synthetic_project(clean_db):
    project = Project(title="Audit Remediation Test")
    clean_db.add(project)
    clean_db.flush()

    work1 = Work(project_id=project.id, title="Book 1", author_name="Author", role="target")
    work2 = Work(project_id=project.id, title="Book 2", author_name="Author", role="reference")
    clean_db.add_all([work1, work2])
    clean_db.flush()

    v1 = WorkVersion(work_id=work1.id, original_sha256="a"*64, normalized_sha256="a"*64)
    v2 = WorkVersion(work_id=work2.id, original_sha256="b"*64, normalized_sha256="b"*64)
    clean_db.add_all([v1, v2])
    clean_db.flush()

    ch1 = Chapter(work_version_id=v1.id, ordinal=1, title="Intro", char_count=500)
    clean_db.add(ch1)
    clean_db.flush()

    sc1 = Scene(chapter_id=ch1.id, ordinal=1, discourse_seq=1, start_char=0, end_char=500, content="Initial text", summary="Scene 1")
    clean_db.add(sc1)
    clean_db.commit()

    return {
        "project": project,
        "work1": work1,
        "work2": work2,
        "v1": v1,
        "v2": v2,
        "ch1": ch1
    }


def test_accept_scene_rejects_unvalidated_draft_p1_01(clean_db, synthetic_project):
    """P1-01: accept_scene must refuse to accept an invalid draft unless force_override is True."""
    v1 = synthetic_project["v1"]
    p = synthetic_project["project"]
    svc = BranchService()
    branch = svc.create_branch(clean_db, p.id, v1.id, 1, "Validation Guard Branch")

    plan = ScenePlan(
        scene_goal="Retrieve Sapphire",
        pov_character="Alice",
        participants=["Alice"],
        initial_state_summary="Alice waiting",
        mandatory_beats=["Alice retrieves sapphire"],
        desired_outcome="Sapphire retrieved"
    )

    # Content does NOT fulfill mandatory beats -> validation will fail
    draft = BranchScene(
        branch_id=branch.id,
        scene_ordinal=1,
        revision_num=1,
        title="Invalid Scene",
        scene_plan_json=plan.model_dump(),
        content="Nothing happens.",
        status="DRAFT",
        state_delta_json={
            "inventory_changes": [{
                "character": "Alice",
                "item": "SAPPHIRE",
                "action": "acquired",
                "span_quote": "ABSENT"
            }]
        }
    )
    clean_db.add(draft)
    clean_db.commit()

    # Attempt to accept without override MUST raise ValueError
    with pytest.raises(ValueError, match="validation failed"):
        svc.accept_scene(clean_db, draft.id, force_override=False)

    # Draft remains DRAFT in DB
    clean_db.refresh(draft)
    assert draft.status == "DRAFT"

    # Explicit override allows acceptance with marker
    accepted = svc.accept_scene(clean_db, draft.id, force_override=True)
    assert accepted.status == "ACCEPTED"
    assert accepted.state_delta_json.get("validation_override") is True


def test_revise_scene_preserves_accepted_history_on_failure_p1_02(clean_db, synthetic_project):
    """P1-02: A failed revision must stay DRAFT and NOT supersede the existing ACCEPTED revision."""
    v1 = synthetic_project["v1"]
    p = synthetic_project["project"]
    svc = BranchService()
    branch = svc.create_branch(clean_db, p.id, v1.id, 1, "Revision Integrity Branch")

    plan = ScenePlan(
        scene_goal="Meeting",
        pov_character="Alice",
        participants=["Alice"],
        initial_state_summary="Alice enters",
        mandatory_beats=["Meeting takes place"],
        desired_outcome="Agreement reached"
    )

    # Valid accepted scene revision 1
    scene_v1 = BranchScene(
        branch_id=branch.id,
        scene_ordinal=1,
        revision_num=1,
        title="Scene 1",
        scene_plan_json=plan.model_dump(),
        content="Alice enters the hall. Meeting takes place and agreement reached.",
        status="ACCEPTED",
        state_delta_json={}
    )
    clean_db.add(scene_v1)
    clean_db.commit()

    # Now revise with invalid text that fails mandatory beats
    new_scene, validation, delta = svc.revise_scene(clean_db, scene_v1.id, "Completely off topic text.")
    assert not validation.passed
    assert new_scene.status == "DRAFT"

    # Crucial guarantee: old scene v1 is STILL ACCEPTED!
    clean_db.refresh(scene_v1)
    assert scene_v1.status == "ACCEPTED"

    # Branch still has 1 accepted scene
    accepted_count = clean_db.query(BranchScene).filter_by(branch_id=branch.id, status="ACCEPTED").count()
    assert accepted_count == 1


def test_epistemic_verification_catches_ignorant_revelations_p1_05():
    """P1-05: Epistemic checker correctly flags ignorant character acting on secret."""
    scope = ForecastScope(project_id="p", target_work_version_id="v", target_max_discourse_seq=1)
    engine = ForecastEngine()

    cand = PredictionCandidate(
        candidate_id="c1",
        title="Leak Secret",
        topology=ChapterTopology(pov_character="Alice", narrative_mode="ACTION"),
        key_events=[PlotBeat(ordinal=1, summary="Alice reveals SECRET at the plaza", participants=["Alice"])],
        rationale="test"
    )

    epistemic_states = [
        CharacterEpistemicState(
            character_id="Alice",
            fact_key="SECRET",
            attitude=EpistemicAttitude.IGNORANT,
            known_from_discourse_seq=10
        )
    ]

    engine._verify_candidate_continuity(cand, scope, active_characters=["Alice"], epistemic_states=epistemic_states)
    assert cand.continuity_status == "failed"
    assert "reveals/acts on ignorant fact" in cand.verification_notes


def test_gemini_prompt_includes_memory_and_boundaries_p1_05():
    """P1-05: build_forecast_prompt serializes character epistemic limits and reflects changes."""
    scope = ForecastScope(project_id="p", target_work_version_id="v", target_max_discourse_seq=1)
    gp = GeminiProvider(api_key=None)

    base_context = {"chapter_num": 1, "formatted_source_text": "TEXT"}

    prompt_a = gp.build_forecast_prompt(
        scope=scope,
        target_context={
            **base_context,
            "epistemic_states": [{"character_id": "Alice", "fact_key": "SECRET", "attitude": "IGNORANT"}],
            "characters": {"Alice": {"status": "ACTIVE"}}
        },
        author_precedents=[],
        canon_context=[]
    )

    prompt_b = gp.build_forecast_prompt(
        scope=scope,
        target_context={
            **base_context,
            "epistemic_states": [{"character_id": "Bob", "fact_key": "TREASURE", "attitude": "KNOWN"}],
            "characters": {"Bob": {"status": "ACTIVE"}}
        },
        author_precedents=[],
        canon_context=[]
    )

    assert "SECTION 2.5: NARRATIVE MEMORY & CHARACTER EPISTEMIC LIMITS" in prompt_a[1]
    assert "Alice" in prompt_a[1]
    assert prompt_a[1] != prompt_b[1]


def test_resolver_fail_closed_on_alien_version_p1_06(clean_db, synthetic_project):
    """P1-06: resolve_scope refuses to link work1 with work2's version."""
    w1 = synthetic_project["work1"]
    v2 = synthetic_project["v2"]  # belongs to work2

    with pytest.raises(ValueError, match="does not exist for work"):
        resolve_scope(clean_db, work_id=w1.id, version_id=v2.id)


def test_task_queue_budget_preservation_p2_17(clean_db, synthetic_project):
    """P2-17: TaskQueue stores and enforces custom max_cost_limit_usd."""
    queue = TaskQueue()
    task = queue.enqueue(
        session=clean_db,
        task_type="BATCH_TEST",
        params={"steps": 5, "unit_cost_usd": 0.02},
        max_cost_limit_usd=0.03
    )
    assert task.max_cost_limit_usd == 0.03

    # Running worker cycle should fail due to 0.02 * 2 > 0.03 cap
    result = queue.execute_worker_cycle(clean_db, task.id)
    assert result.status == "FAILED"
    assert "Budget cap exceeded" in result.error_message
