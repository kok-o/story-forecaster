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


def test_evidence_record_exact_coordinates_length_p1_04():
    """P1-04: Baseline EvidenceRecords must have exact coordinates where (end_char - start_char) == len(source_text)."""
    import hashlib
    from story_forecaster.memory.engine import NarrativeMemoryEngine

    engine = NarrativeMemoryEngine()
    records = engine.get_evidence()
    assert len(records) >= 8

    for ev in records:
        assert (ev.end_char - ev.start_char) == len(ev.source_text), f"Coordinate mismatch for {ev.evidence_id}"
        expected_sha = hashlib.sha256(ev.source_text.encode("utf-8")).hexdigest()
        assert ev.fragment_sha256 == expected_sha, f"Hash mismatch for {ev.evidence_id}"


def test_reducer_isolates_by_work_version_id_p1_04(clean_db, synthetic_project):
    """P1-04: EvidenceReducer isolates chapter resolution and excludes records from foreign versions."""
    from story_forecaster.memory.reducer import EvidenceReducer
    from story_forecaster.domain.memory import EvidenceRecord, EvidenceKind

    v1 = synthetic_project["v1"]
    v2 = synthetic_project["v2"]

    ev_v1 = EvidenceRecord(
        evidence_id="ev_v1_scoped",
        kind=EvidenceKind.OBSERVED_EVENT,
        reader_availability_seq=10,
        chapter_ordinal=1,
        scene_discourse_seq=10,
        start_char=0,
        end_char=10,
        fragment_sha256="dummy",
        source_text="Test v1 txt",
        subject="Subject",
        predicate="action",
        work_version_id=v1.id
    )

    ev_v2 = EvidenceRecord(
        evidence_id="ev_v2_alien",
        kind=EvidenceKind.OBSERVED_EVENT,
        reader_availability_seq=10,
        chapter_ordinal=1,
        scene_discourse_seq=10,
        start_char=0,
        end_char=10,
        fragment_sha256="dummy",
        source_text="Test v2 txt",
        subject="Subject",
        predicate="alien_action",
        work_version_id=v2.id
    )

    snapshot_v1 = EvidenceReducer.reduce(
        cutoff_seq=20,
        evidence_records=[ev_v1, ev_v2],
        threads=[],
        epistemic_states=[],
        db_session=clean_db,
        work_version_id=v1.id
    )

    # Alien record ev_v2 must be excluded when reducing for v1
    evidence_ids = [e.evidence_id for e in snapshot_v1.evidence_records]
    assert "ev_v1_scoped" in evidence_ids
    assert "ev_v2_alien" not in evidence_ids


def test_author_precedents_scope_isolation_p1_07():
    """P1-07: AuthorPrecedentLibrary tracks provenance status and honors scope ablation."""
    from story_forecaster.author.precedents import AuthorPrecedentLibrary
    from story_forecaster.domain.scope import ForecastScope

    lib = AuthorPrecedentLibrary()
    profile = lib.get_profile()

    # Baseline transitions must be explicitly marked as curated heuristic rules
    assert len(profile.transitions) >= 4
    for t in profile.transitions:
        assert t.is_corpus_verified is False
        assert t.provenance_status == "curated_heuristic_rule"

    # Ablated scope disallowing author manifest must return empty precedents list
    ablated_scope = ForecastScope(
        project_id="test_proj",
        target_work_version_id="ver_1",
        target_max_discourse_seq=182,
        allowed_author_manifest_id="none"
    )
    res = lib.query_precedents(ablated_scope, tags=["fairy_blackmail"])
    assert len(res) == 0

    # Normal scope returns matching precedents
    normal_scope = ForecastScope(
        project_id="test_proj",
        target_work_version_id="ver_1",
        target_max_discourse_seq=182
    )
    res_normal = lib.query_precedents(normal_scope, tags=["fairy_blackmail"])
    assert len(res_normal) >= 1


def test_sqlite_foreign_keys_enforced_p2_16():
    """P2-16: enable_sqlite_foreign_keys guarantees foreign key enforcement in SQLite."""
    from sqlalchemy import create_engine, text
    from story_forecaster.db.session import enable_sqlite_foreign_keys
    from sqlalchemy.exc import IntegrityError

    test_engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(test_engine)

    with test_engine.connect() as conn:
        res = conn.execute(text("PRAGMA foreign_keys;")).scalar()
        assert res == 1, "PRAGMA foreign_keys must be ON"

        # Create parent and child tables to verify integrity enforcement
        conn.execute(text("CREATE TABLE parent (id TEXT PRIMARY KEY);"))
        conn.execute(text("CREATE TABLE child (id TEXT PRIMARY KEY, parent_id TEXT REFERENCES parent(id));"))
        conn.commit()

        # Inserting child with invalid foreign key must raise IntegrityError
        with pytest.raises(IntegrityError):
            conn.execute(text("INSERT INTO child (id, parent_id) VALUES ('c1', 'nonexistent');"))
            conn.commit()


def test_api_auth_protection_on_mutating_endpoints_p2_16(clean_db, monkeypatch):
    """P2-16: Mutating endpoints require authentication when STORY_FORECASTER_API_KEY is configured."""
    from fastapi.testclient import TestClient
    from story_forecaster.api.main import app, get_db

    app.dependency_overrides[get_db] = lambda: clean_db
    client = TestClient(app)

    monkeypatch.setenv("STORY_FORECASTER_API_KEY", "test-secret-key-12345")

    # Mutating request without auth header must be 401 Unauthorized
    resp_unauth = client.post("/api/tasks", json={"task_type": "DRAFT_SCENE", "params": {}})
    assert resp_unauth.status_code == 401
    assert "Invalid or missing API key" in resp_unauth.json()["detail"]

    # Mutating request with incorrect key must be 401
    resp_wrong = client.post("/api/tasks", json={"task_type": "DRAFT_SCENE", "params": {}}, headers={"X-API-Key": "wrong-key"})
    assert resp_wrong.status_code == 401

    # Mutating request with valid X-API-Key header succeeds
    resp_auth = client.post("/api/tasks", json={"task_type": "DRAFT_SCENE", "params": {}}, headers={"X-API-Key": "test-secret-key-12345"})
    assert resp_auth.status_code == 200
    assert "task_id" in resp_auth.json()

    # Mutating request with valid Authorization: Bearer token also succeeds
    resp_bearer = client.post("/api/tasks", json={"task_type": "DRAFT_SCENE", "params": {}}, headers={"Authorization": "Bearer test-secret-key-12345"})
    assert resp_bearer.status_code == 200


def test_api_payload_validation_bounds_p2_16(clean_db):
    """P2-16: API models enforce strict maximum length bounds preventing DoS via excessive payloads."""
    from fastapi.testclient import TestClient
    from story_forecaster.api.main import app, get_db

    app.dependency_overrides[get_db] = lambda: clean_db
    client = TestClient(app)

    # Oversized scene in editorial review (>50KB) must be rejected with 422
    giant_scene = "A" * 50001
    resp_review = client.post("/api/editor/review", json={"chapter_ordinal": 1, "scenes_content": [giant_scene]})
    assert resp_review.status_code == 422
    assert "exceeds maximum 50KB limit" in resp_review.text

    # Oversized task params (>64KB) must be rejected with 422
    giant_params = {"big_payload": "X" * 66000}
    resp_task = client.post("/api/tasks", json={"task_type": "TEST", "params": giant_params})
    assert resp_task.status_code == 422
    assert "exceeds maximum 64KB limit" in resp_task.text


def test_api_rate_limiter_p2_16():
    """P2-16: SlidingWindowRateLimiter throttles requests and raises 429 when limit exceeded."""
    from fastapi import HTTPException, Request
    from story_forecaster.api.security import SlidingWindowRateLimiter

    limiter = SlidingWindowRateLimiter(requests_per_window=2, window_seconds=10)

    # Mock request with client host
    class MockRequest:
        def __init__(self, ip: str):
            self.client = type("Client", (), {"host": ip})()
            self.headers = {}

    req = MockRequest("192.168.1.100")

    # First two requests within window pass
    assert limiter.check(req) is True
    assert limiter.check(req) is True

    # Third request within window raises 429
    with pytest.raises(HTTPException) as exc_info:
        limiter.check(req)
    assert exc_info.value.status_code == 429
    assert "Rate limit exceeded" in exc_info.value.detail
    assert "Retry-After" in exc_info.value.headers


def test_ablation_honesty_demo_provider_p1_08():
    """P1-08: AblationBenchmark with DemoProvider remains is_synthetic_demonstration=True even with execute_live=True."""
    from story_forecaster.evaluation.ablation import AblationBenchmark
    from story_forecaster.forecast.engine import ForecastEngine
    from story_forecaster.providers import DemoProvider

    engine = ForecastEngine(provider=DemoProvider())
    bench = AblationBenchmark(engine=engine)
    report = bench.run_benchmark(execute_live=True, include_fine_grained=False)

    # Must be honestly identified as synthetic demonstration because DemoProvider was used
    assert report.is_synthetic_demonstration is True
    assert "[СИНТЕТИЧЕСКИЙ ДЕМО-ПРОГОН" in report.summary_analysis
    assert len(report.runs) >= 4

    for r in report.runs:
        # Separate Best@1 and Oracle@K tracked
        assert hasattr(r, "best_at_1_f1")
        assert hasattr(r, "oracle_at_k_f1")
        assert "disable_retrieval" in r.disable_flags
        assert "disable_memory" in r.disable_flags


def test_editorial_review_honesty_on_trivial_input_p2_09():
    """P2-09: Trivial scenes ('abc', 'abc') must not receive inflated quality scores or false publication clearance."""
    from story_forecaster.planning.arc_manager import ArcManager

    mgr = ArcManager()
    review = mgr.editorial_review_chapter(chapter_ordinal=1, scenes_content=["abc", "abc"])

    # Scorecard must not be inflated
    assert review.scorecard.overall_quality_score < 0.60
    assert review.scorecard.pacing_score <= 0.35
    assert "Тривиально малый объём" in review.pacing_assessment

    # Must NOT contain false publication readiness recommendation
    assert "Глава стилистически и композиционно готова к публикации в ветке." not in review.recommendations
    assert any("требуют экспертной вычитки редактором" in rec for rec in review.recommendations)


def test_task_queue_rejects_unsupported_handler_p2_10(clean_db, synthetic_project):
    """P2-10: Task with unsupported task_type fails immediately instead of simulating completion."""
    from story_forecaster.tasks.queue import TaskQueue

    queue = TaskQueue()
    task = queue.enqueue(session=clean_db, task_type="INVALID_NO_HANDLER", params={})
    assert task.status == "QUEUED"

    result = queue.execute_worker_cycle(clean_db, task.id)
    assert result.status == "FAILED"
    assert "Unsupported task_type: 'INVALID_NO_HANDLER'" in result.error_message


def test_context_builder_strict_budget_truncation_p2_11(clean_db, synthetic_project):
    """P2-11: NarrativeContextBuilder enforces strict budget limit even on first scene."""
    from story_forecaster.forecast.context_builder import NarrativeContextBuilder
    from story_forecaster.domain.scope import ForecastScope

    builder = NarrativeContextBuilder()
    v1 = synthetic_project["v1"]
    scope = ForecastScope(
        project_id="p1",
        target_work_version_id=v1.id,
        target_max_discourse_seq=10
    )

    # Request with tiny budget of 10 chars
    ctx = builder.build_context(db=clean_db, scope=scope, char_budget=10)
    assert ctx.truncation_info["used_chars"] <= 10
    for doc in ctx.sources:
        assert doc.char_count <= 10



