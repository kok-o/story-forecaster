import pytest
from fastapi.testclient import TestClient

from story_forecaster.db.session import SessionLocal
from story_forecaster.db.models import Work, WorkVersion, Arc, AsyncTask, Branch
from story_forecaster.domain.arc import (
    ArcPlan, ArcMilestone, ReaderPromise, ChapterPlan, EditorialReview
)
from story_forecaster.domain.writing import ScenePlan
from story_forecaster.writing.branch_service import BranchService
from story_forecaster.planning.arc_manager import ArcManager
from story_forecaster.tasks.queue import TaskQueue
from story_forecaster.api.main import app



@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def target_work_context(db_session):
    work = db_session.query(Work).filter_by(role="target").first()
    if not work:
        pytest.skip("Target work not found in test database.")
    version = db_session.query(WorkVersion).filter_by(work_id=work.id).first()
    if not version:
        pytest.skip("Target work version not found in test database.")
    return work, version


@pytest.fixture
def api_client():
    return TestClient(app)


def test_arc_plan_creation_and_versioning(db_session, target_work_context):
    """
    Criterion: Formalize ArcPlan with milestones, reader promises, and setups/payoffs.
    Enforce explicit versioning on plan modifications.
    """
    work, version = target_work_context
    mgr = ArcManager()

    milestones = [
        ArcMilestone(milestone_id="m1", title="Призыв Кадзумы", order=1, status="ACHIEVED"),
        ArcMilestone(milestone_id="m2", title="Разведка Ярмарки Осколков", order=2, status="IN_PROGRESS"),
        ArcMilestone(milestone_id="m3", title="Контракт с феей на пыльцу", order=3, status="PENDING")
    ]
    promises = [
        ReaderPromise(
            promise_id="p1",
            introduced_in_scene_ordinal=1,
            promise_text="Хорадримский Куб S-ранга окупит затраты 400к золотых",
            payoff_status="OPEN"
        ),
        ReaderPromise(
            promise_id="p2",
            introduced_in_scene_ordinal=2,
            promise_text="Фея поплатится за попытку шантажа перед всей ярмаркой",
            payoff_status="OPEN"
        )
    ]

    arc = mgr.create_arc(
        session=db_session,
        project_id=work.project_id,
        title="Арка Ярмарки Осколков",
        theme="Утилитарное использование Системы Зла и торговых лазеек",
        core_conflict="Шантаж феи против холодной прагматики Хачимана",
        milestones=milestones,
        promises=promises,
        open_mysteries=["Истинное происхождение порталов ярмарки"],
        setups_and_payoffs={"Очки-оценки куплены на рынке": "Позволят разоблачить фальшивые артефакты"}
    )

    assert arc.id is not None
    assert arc.revision_num == 1
    assert arc.status == "ACTIVE"

    # Test explicit plan modification versioning
    plan = mgr.get_arc_plan(db_session, arc.id)
    assert plan is not None
    assert len(plan.milestones) == 3
    assert len(plan.reader_promises) == 2

    # Add a new milestone and update
    plan.milestones.append(
        ArcMilestone(milestone_id="m4", title="Открытие лавки Куба", order=4, status="PENDING")
    )
    updated_arc = mgr.update_arc_plan(db_session, arc.id, plan)
    assert updated_arc.revision_num == 2
    assert len(updated_arc.arc_plan_json["milestones"]) == 4


def test_commitment_age_tracking_and_stagnation_detection():
    """
    Criterion: Track open reader promises, line age, and detect repetitive conflicts.
    Flag forgotten lines where age >= 4 without payoff.
    """
    mgr = ArcManager()
    plan = ArcPlan(
        arc_id="arc_test",
        title="Тестовая арка",
        theme="Тест",
        core_conflict="Тест",
        milestones=[
            ArcMilestone(milestone_id="m1", title="Шаг 1", order=1, status="ACHIEVED"),
            ArcMilestone(milestone_id="m2", title="Шаг 2", order=2, status="PENDING")
        ],
        reader_promises=[
            ReaderPromise(
                promise_id="p_recent",
                introduced_in_scene_ordinal=4,
                promise_text="Свежее обещание",
                payoff_status="OPEN"
            ),
            ReaderPromise(
                promise_id="p_aged",
                introduced_in_scene_ordinal=1,
                promise_text="Старое незакрытое обещание о дуэли",
                payoff_status="OPEN"
            ),
            ReaderPromise(
                promise_id="p_fulfilled",
                introduced_in_scene_ordinal=1,
                promise_text="Выполненное обещание",
                payoff_status="PAID_OFF"
            )
        ],
        open_mysteries=["Загадка рун"],
        revision_num=1
    )

    # Evaluate at current scene ordinal = 6
    report = mgr.track_commitments(plan, current_scene_or_chapter=6)
    assert report["open_commitments_count"] == 2
    assert report["aging_commitments_count"] == 1  # p_aged (age = 6 - 1 = 5 >= 4)
    assert report["open_mysteries_count"] == 1

    aged_item = next(c for c in report["commitments"] if c["promise_id"] == "p_aged")
    assert aged_item["current_age"] == 5
    assert aged_item["is_aging_risk"] is True

    # Test conflict repetition detector
    conflicts_stagnant = ["extortion", "extortion", "extortion"]
    rep_result = mgr.detect_conflict_repetition(conflicts_stagnant)
    assert rep_result["is_repetitive"] is True
    assert rep_result["consecutive_count"] == 3

    conflicts_progressing = ["extortion", "negotiation", "crafting"]
    norm_result = mgr.detect_conflict_repetition(conflicts_progressing)
    assert norm_result["is_repetitive"] is False


def test_chapter_editorial_review_and_quality_scorecard():
    """
    Criterion: Perform post-chapter editorial audit on rhythm, clichés/repetition,
    character voice consistency, and causal coherence.
    """
    mgr = ArcManager()

    scenes = [
        (
            "Хачиман положил артефакт на стол. — Контракт на Сато Кадзуму заключен. "
            "С этого момента ты оператор Хорадримского Куба. "
            "В воздухе повисло напряжение, но расчет был точен."
        ),
        (
            "Ярмарка шумела десятками голосов. Кадзума поправил Очки-оценки. "
            "— Босс будет доволен такой добычей! Удача меня не подведет! "
            "В воздухе повисло напряжение, когда в переулке раздался писк."
        ),
        (
            "— Либо ты ведешь меня к Боссу, либо я всем все расскажу! — пропищала фея. "
            "Кадзума побледнел как полотно. Повторный шантаж был очевиден, поэтому он повел ее к Хачиману."
        )
    ]

    from story_forecaster.writing.voice import VoiceRegistry
    reg = VoiceRegistry()
    profiles = [reg.get_profile("Хачиман Хикигая"), reg.get_profile("Сато Кадзума")]

    review = mgr.editorial_review_chapter(
        chapter_ordinal=24,
        scenes_content=scenes,
        voice_profiles=profiles
    )

    assert isinstance(review, EditorialReview)
    sc = review.scorecard
    assert 0.0 <= sc.pacing_score <= 1.0
    assert 0.0 <= sc.voice_consistency_score <= 1.0
    assert 0.0 <= sc.causal_coherence_score <= 1.0
    assert sc.overall_quality_score >= 0.70

    # Verify repetition detection caught the duplicate stock phrase
    assert any("в воздухе повисло напряжение" in p for p in review.repetitive_phrases)
    assert sc.repetition_penalty > 0.0


def test_persistent_task_queue_progress_cancellation_and_budget_caps(db_session):
    """
    Criterion: SQLite-backed worker queue supporting progress tracking, spend caps,
    and graceful cancellation.
    """
    queue = TaskQueue()

    # 1. Enqueue task
    task = queue.enqueue(
        session=db_session,
        task_type="forecast_batch",
        params={"steps": 5, "unit_cost_usd": 0.02},
        project_id=None
    )

    assert task.status == "QUEUED"
    assert task.progress_pct == 0
    assert task.cost_usd == 0.0

    # 2. Execute worker cycle within budget
    completed_task = queue.execute_worker_cycle(
        session=db_session,
        task_id=task.id,
        max_cost_limit_usd=0.20
    )
    assert completed_task.status == "COMPLETED"
    assert completed_task.progress_pct == 100
    assert completed_task.cost_usd == pytest.approx(0.10, rel=1e-3)
    assert completed_task.result_json.get("steps_completed") == 5

    # 3. Test budget cap enforcement
    task_expensive = queue.enqueue(
        session=db_session,
        task_type="arc_synthesis",
        params={"steps": 10, "unit_cost_usd": 0.10}
    )
    capped_task = queue.execute_worker_cycle(
        session=db_session,
        task_id=task_expensive.id,
        max_cost_limit_usd=0.15  # Will halt after step 1
    )
    assert capped_task.status == "FAILED"
    assert "Budget cap exceeded" in capped_task.error_message

    # 4. Test explicit task cancellation
    task_to_cancel = queue.enqueue(
        session=db_session,
        task_type="ablation_run",
        params={"steps": 5, "unit_cost_usd": 0.01}
    )
    cancelled_task = queue.cancel_task(session=db_session, task_id=task_to_cancel.id)
    assert cancelled_task.status == "CANCELLED"

    # Worker respects cancellation
    cycle_result = queue.execute_worker_cycle(
        session=db_session,
        task_id=cancelled_task.id
    )
    assert cycle_result.status == "CANCELLED"


def test_api_endpoints_writing_arcs_and_tasks_integration(api_client, target_work_context):
    """
    Criterion: Full HTTP API integration for branch drafting, revisions,
    arc commitments tracking, editorial review, and task execution.
    """
    work, version = target_work_context

    # 1. Create branch via API
    resp_branch = api_client.post("/api/writing/branches", json={
        "branch_name": "API Integration Branch",
        "cutoff_discourse_seq": 182,
        "description": "Created via FastAPI integration test"
    })
    assert resp_branch.status_code == 200
    branch_data = resp_branch.json()
    branch_id = branch_data["id"]

    # 2. Draft scene via API
    resp_draft = api_client.post(f"/api/writing/branches/{branch_id}/draft", json={
        "scene_ordinal": 1,
        "title": "Сцена найма",
        "plan": {
            "scene_goal": "Наем Кадзумы",
            "pov_character": "Хачиман Хикигая",
            "participants": ["Хачиман Хикигая", "Сато Кадзума"],
            "initial_state_summary": "Хачиман в комнате.",
            "mandatory_beats": ["Покупка контракта Сато Кадзумы за 400 000 золотых"],
            "desired_outcome": "Кадзума соглашается служить.",
            "target_pacing": "medium",
            "target_length_chars": 2000
        }
    })
    assert resp_draft.status_code == 200
    draft_data = resp_draft.json()
    scene_id = draft_data["scene_id"]
    assert draft_data["status"] == "DRAFT"
    assert "validation" in draft_data
    assert "proposed_state_delta" in draft_data

    # 3. Accept scene
    resp_accept = api_client.post(f"/api/writing/scenes/{scene_id}/accept")
    assert resp_accept.status_code == 200
    assert resp_accept.json()["status"] == "ACCEPTED"

    # 4. Export branch
    resp_export = api_client.get(f"/api/writing/branches/{branch_id}/export?format=markdown")
    assert resp_export.status_code == 200
    assert "# API Integration Branch" in resp_export.json()["content"]

    # 5. Create Arc & check commitments
    resp_arc = api_client.post("/api/arcs", json={
        "title": "Арка Ярмарки API",
        "theme": "Тема API",
        "core_conflict": "Конфликт API",
        "promises": [
            {
                "promise_id": "p_api",
                "introduced_in_scene_ordinal": 1,
                "promise_text": "Обещание API",
                "payoff_status": "OPEN"
            }
        ]
    })
    assert resp_arc.status_code == 200
    arc_id = resp_arc.json()["id"]

    resp_comm = api_client.get(f"/api/arcs/{arc_id}/commitments?current_scene=3")
    assert resp_comm.status_code == 200
    assert resp_comm.json()["open_commitments_count"] == 1

    # 6. Editorial Review via API
    resp_rev = api_client.post("/api/editor/review", json={
        "chapter_ordinal": 24,
        "scenes_content": ["Хачиман оценил обстановку. Сделка состоялась.", "Кадзума кивнул: 'Да, Босс!'"]
    })
    assert resp_rev.status_code == 200
    assert "scorecard" in resp_rev.json()

    # 7. Task Queue via API
    resp_task = api_client.post("/api/tasks", json={
        "task_type": "forecast_batch",
        "params": {"steps": 3, "unit_cost_usd": 0.01},
        "max_cost_limit_usd": 0.50
    })
    assert resp_task.status_code == 200
    task_id = resp_task.json()["task_id"]

    resp_run = api_client.post(f"/api/tasks/{task_id}/run")
    assert resp_run.status_code == 200
    assert resp_run.json()["status"] == "COMPLETED"
    assert resp_run.json()["progress_pct"] == 100


def test_pilot_quality_journal_three_to_five_scenes_trajectory(db_session, target_work_context):
    """
    Criterion: Measure quality trajectory on 3-5 chapter/scene pilot:
    Verify contradiction count = 0, forgotten lines = 0, and consistent causal progression.
    """
    work, version = target_work_context
    service = BranchService()
    arc_mgr = ArcManager()

    # 1. Establish Branch
    branch = service.create_branch(
        session=db_session,
        project_id=work.project_id,
        parent_work_version_id=version.id,
        cutoff_discourse_seq=182,
        branch_name="Пилотный прогон 3 сцен"
    )

    # 2. Establish Arc
    arc = arc_mgr.create_arc(
        session=db_session,
        project_id=work.project_id,
        title="Пилотная арка: Автокрафт",
        theme="Эволюция союза Хачимана и Кадзумы",
        core_conflict="Шантаж феи и экспансия на Ярмарке",
        milestones=[
            ArcMilestone(milestone_id="pm1", title="Призыв Кадзумы", order=1, status="PENDING"),
            ArcMilestone(milestone_id="pm2", title="Разведка цен", order=2, status="PENDING"),
            ArcMilestone(milestone_id="pm3", title="Подавление шантажа", order=3, status="PENDING")
        ],
        promises=[
            ReaderPromise(promise_id="pp1", introduced_in_scene_ordinal=1, promise_text="Кадзума окупит 400 000 золотых", payoff_status="OPEN"),
            ReaderPromise(promise_id="pp2", introduced_in_scene_ordinal=3, promise_text="Фея согласится на оптовую поставку", payoff_status="OPEN")
        ]
    )

    # 3. Step 1: Summon Kazuma
    sc1, val1, _ = service.draft_scene(
        session=db_session,
        branch_id=branch.id,
        scene_ordinal=1,
        title="Сцена 1: Покупка",
        plan=ScenePlan(
            scene_goal="Покупка контракта",
            pov_character="Хачиман Хикигая",
            participants=["Хачиман Хикигая", "Сато Кадзума"],
            initial_state_summary="В штабе.",
            mandatory_beats=["Покупка контракта Сато Кадзумы за 400 000 золотых"],
            desired_outcome="Кадзума привязан."
        )
    )
    assert val1.passed is True
    service.accept_scene(db_session, sc1.id)

    # 4. Step 2: Scout Market
    sc2, val2, _ = service.draft_scene(
        session=db_session,
        branch_id=branch.id,
        scene_ordinal=2,
        title="Сцена 2: Рынок",
        plan=ScenePlan(
            scene_goal="Разведка рынка",
            pov_character="Сато Кадзума",
            participants=["Сато Кадзума"],
            initial_state_summary="На рынке.",
            mandatory_beats=["Ярмарка Осколков и разведка цен", "Очки-оценки"],
            desired_outcome="Цены подтверждены."
        )
    )
    assert val2.passed is True
    service.accept_scene(db_session, sc2.id)

    # 5. Step 3: Fairy Confrontation
    sc3, val3, _ = service.draft_scene(
        session=db_session,
        branch_id=branch.id,
        scene_ordinal=3,
        title="Сцена 3: Переговоры",
        plan=ScenePlan(
            scene_goal="Переговоры с феей",
            pov_character="Хачиман Хикигая",
            participants=["Хачиман Хикигая", "Сато Кадзума", "Фея"],
            initial_state_summary="В переулке.",
            mandatory_beats=["Шантаж феи пыльцой и угрозой разоблачения", "Переговоры с Хачиманом"],
            desired_outcome="Контракт подписан."
        )
    )
    assert val3.passed is True
    service.accept_scene(db_session, sc3.id)

    # Quality Journal Assessment:
    # A) Contradictions count in memory snapshot
    final_snap = service.get_branch_snapshot(db_session, branch.id, through_scene_ordinal=3)
    assert len(final_snap.conflicts) == 0  # Zero factual contradictions!

    # B) Reader commitments status
    arc_plan = arc_mgr.get_arc_plan(db_session, arc.id)
    commitments_rep = arc_mgr.track_commitments(arc_plan, current_scene_or_chapter=3)
    assert commitments_rep["aging_commitments_count"] == 0  # No forgotten/aging lines

    # C) Holistic editorial scorecard
    review = arc_mgr.editorial_review_chapter(
        chapter_ordinal=24,
        scenes_content=[sc1.content, sc2.content, sc3.content]
    )
    assert review.scorecard.overall_quality_score >= 0.75
    assert review.scorecard.causal_coherence_score >= 0.70
