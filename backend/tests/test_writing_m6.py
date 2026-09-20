import pytest
from story_forecaster.db.session import SessionLocal
from story_forecaster.db.models import (
    Work, WorkVersion, Chapter, Scene, Branch, BranchScene
)
from story_forecaster.domain.writing import ScenePlan, CharacterVoiceProfile
from story_forecaster.domain.memory import EpistemicAttitude
from story_forecaster.memory.engine import NarrativeMemoryEngine
from story_forecaster.writing.voice import VoiceRegistry
from story_forecaster.writing.validator import SceneValidator
from story_forecaster.writing.synthesizer import SceneSynthesizer
from story_forecaster.writing.branch_service import BranchService


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


def test_original_work_and_database_immutability(db_session, target_work_context):
    """
    Criterion: Original book (work_versions, chapters, scenes) MUST NEVER be modified
    by fanfic branches, drafting, revisions, or deletions.
    """
    work, version = target_work_context

    # 1. Capture baseline state of original canonical entities
    initial_versions_count = db_session.query(WorkVersion).count()
    initial_chapters_count = db_session.query(Chapter).count()
    initial_scenes_count = db_session.query(Scene).count()

    initial_chapters = [(c.id, c.ordinal, c.title) for c in db_session.query(Chapter).all()]
    initial_scenes_content_lengths = [len(s.content or "") for s in db_session.query(Scene).all()]


    # 2. Perform fanfic operations
    service = BranchService()
    branch = service.create_branch(
        session=db_session,
        project_id=work.project_id,
        parent_work_version_id=version.id,
        cutoff_discourse_seq=182,
        branch_name="Branch Immutability Test"
    )

    plan = ScenePlan(
        scene_goal="Тест изоляции",
        pov_character="Хачиман Хикигая",
        participants=["Хачиман Хикигая", "Сато Кадзума"],
        initial_state_summary="Хачиман открывает Систему Зла.",
        mandatory_beats=["Покупка контракта Сато Кадзумы через Систему за 400 000 золотых"],
        desired_outcome="Кадзума нанят."
    )

    sc, val, delta = service.draft_scene(
        session=db_session,
        branch_id=branch.id,
        scene_ordinal=1,
        title="Сцена найма",
        plan=plan
    )
    service.accept_scene(db_session, sc.id)

    # 3. Assert original tables are 100% UNCHANGED
    assert db_session.query(WorkVersion).count() == initial_versions_count
    assert db_session.query(Chapter).count() == initial_chapters_count
    assert db_session.query(Scene).count() == initial_scenes_count

    current_chapters = [(c.id, c.ordinal, c.title) for c in db_session.query(Chapter).all()]
    assert current_chapters == initial_chapters

    current_scenes_content_lengths = [len(s.content or "") for s in db_session.query(Scene).all()]
    assert current_scenes_content_lengths == initial_scenes_content_lengths



def test_character_voice_registry_and_profiles():
    """
    Criterion: Implement CharacterVoiceProfile with vocabulary tone, sentence length,
    dialogue mannerisms, and interpersonal shifts.
    """
    registry = VoiceRegistry()
    hachiman_voice = registry.get_profile("Хачиман Хикигая")
    assert hachiman_voice is not None
    assert "циничный" in hachiman_voice.vocabulary_tone
    assert len(hachiman_voice.dialogue_mannerisms) >= 3
    assert "Сато Кадзума" in hachiman_voice.interpersonal_nuance

    kazuma_voice = registry.get_profile("Сато Кадзума")
    assert kazuma_voice is not None
    assert kazuma_voice.typical_sentence_length == "short"
    assert "Босс" in " ".join(kazuma_voice.dialogue_mannerisms)

    fairy_voice = registry.get_profile("Фея")
    assert fairy_voice is not None
    assert "вымогательский" in fairy_voice.vocabulary_tone

    saeko_voice = registry.get_profile("Саэко Бусуджима")
    assert saeko_voice is not None
    assert "традиционно-вежливый" in saeko_voice.vocabulary_tone


def test_full_consecutive_scenes_cycle_and_snapshot_replay(db_session, target_work_context):
    """
    Criterion: 3-5 consecutive scenes pass full cycle:
    ScenePlan -> SceneSynthesizer -> SceneValidator -> BranchScene (ACCEPTED) -> Snapshot replay.
    """
    work, version = target_work_context
    service = BranchService()

    branch = service.create_branch(
        session=db_session,
        project_id=work.project_id,
        parent_work_version_id=version.id,
        cutoff_discourse_seq=182,
        branch_name="Хроники Ярмарки: Линия Кадзумы"
    )

    # --- Scene 1: Contract & Horadric Cube ---
    plan_sc1 = ScenePlan(
        scene_goal="Призыв Сато Кадзумы и вручение Хорадримского Куба",
        pov_character="Хачиман Хикигая",
        participants=["Хачиман Хикигая", "Сато Кадзума"],
        initial_state_summary="В штабе Хачимана мерцает меню Системы Зла.",
        mandatory_beats=[
            "Покупка контракта Сато Кадзумы через Систему за 400 000 золотых",
            "Привязка Хорадримского Куба S-ранга к Кадзуме"
        ],
        desired_outcome="Кадзума становится оператором Куба с 100% удачей.",
        target_pacing="medium"
    )

    sc1, val1, delta1 = service.draft_scene(
        session=db_session,
        branch_id=branch.id,
        scene_ordinal=1,
        title="Контракт удачливого отаку",
        plan=plan_sc1
    )
    assert val1.passed is True
    assert val1.plan_compliance_score >= 0.70
    assert len(val1.pov_violations) == 0
    assert len(val1.epistemic_violations) == 0

    service.accept_scene(db_session, sc1.id)

    snap1 = service.get_branch_snapshot(db_session, branch.id, through_scene_ordinal=1)
    assert "Сато Кадзума" in snap1.active_characters
    assert "Хорадримский Куб (S)" in snap1.active_characters["Сато Кадзума"]["equipped"]

    # --- Scene 2: Shard Trade Fair & Assessment Glasses ---
    plan_sc2 = ScenePlan(
        scene_goal="Кадзума выходит на Ярмарку Осколков для разведки цен",
        pov_character="Сато Кадзума",
        participants=["Сато Кадзума"],
        initial_state_summary="Шумная ярмарка заполнена торговцами из параллельных миров.",
        mandatory_beats=[
            "Ярмарка Осколков и разведка цен",
            "Кадзума надевает Очки-оценки для сканирования редкостей"
        ],
        desired_outcome="Кадзума осматривается на рынке и подтверждает системные цены.",
        target_pacing="medium"
    )

    sc2, val2, delta2 = service.draft_scene(
        session=db_session,
        branch_id=branch.id,
        scene_ordinal=2,
        title="Очки-оценки на Ярмарке",
        plan=plan_sc2
    )
    assert val2.passed is True
    service.accept_scene(db_session, sc2.id)

    snap2 = service.get_branch_snapshot(db_session, branch.id, through_scene_ordinal=2)
    equipped_items_sc2 = snap2.active_characters["Сато Кадзума"]["equipped"]
    assert "Хорадримский Куб (S)" in equipped_items_sc2
    assert "Очки-оценки (S)" in equipped_items_sc2

    # --- Scene 3: Meeting the Fairy & Negotiation with Hachiman ---
    plan_sc3 = ScenePlan(
        scene_goal="Фея пытается шантажировать Кадзуму, но сталкивается с Хачиманом",
        pov_character="Хачиман Хикигая",
        participants=["Хачиман Хикигая", "Сато Кадзума", "Фея"],
        initial_state_summary="В переулке у ярмарочного прилавка раздается писклявый голос.",
        mandatory_beats=[
            "Шантаж феи пыльцой и угрозой разоблачения",
            "Переговоры с Хачиманом и подписание контракта"
        ],
        desired_outcome="Фея вынуждена уступить и подписать соглашение на поставку пыльцы.",
        target_pacing="fast"
    )

    sc3, val3, delta3 = service.draft_scene(
        session=db_session,
        branch_id=branch.id,
        scene_ordinal=3,
        title="Укрощение строптивой феи",
        plan=plan_sc3
    )
    assert val3.passed is True
    service.accept_scene(db_session, sc3.id)

    snap3 = service.get_branch_snapshot(db_session, branch.id, through_scene_ordinal=3)
    assert "Фея" in snap3.active_characters
    # Verify epistemic update: Kazuma knows fairy blackmail active
    kazuma_epistemic = [e for e in snap3.epistemic_states if e.character_id == "Сато Кадзума" and e.fact_key == "fairy_blackmail_active"]
    assert len(kazuma_epistemic) == 1
    assert kazuma_epistemic[0].attitude == EpistemicAttitude.KNOWN


def test_rejected_scene_isolation_never_mutates_branch_memory(db_session, target_work_context):
    """
    Criterion: Rejected scene state delta NEVER mutates the branch narrative snapshot.
    """
    work, version = target_work_context
    service = BranchService()

    branch = service.create_branch(
        session=db_session,
        project_id=work.project_id,
        parent_work_version_id=version.id,
        cutoff_discourse_seq=180,
        branch_name="Branch Rejection Quarantine Test"
    )

    baseline_snap = service.get_branch_snapshot(db_session, branch.id)
    baseline_hash = baseline_snap.snapshot_hash

    # Draft a scene that will be rejected
    plan_rogue = ScenePlan(
        scene_goal="Самовольный бунт",
        pov_character="Хачиман Хикигая",
        participants=["Хачиман Хикигая", "Сато Кадзума"],
        initial_state_summary="Взбалмошный инцидент.",
        mandatory_beats=["Покупка контракта Сато Кадзумы"],
        desired_outcome="Отказ от канона."
    )

    sc, val, delta = service.draft_scene(
        session=db_session,
        branch_id=branch.id,
        scene_ordinal=1,
        title="Бракованная сцена",
        plan=plan_rogue
    )

    # Reject scene
    service.reject_scene(db_session, sc.id, reason="OOC and unapproved rogue deviation")

    # Snapshot after rejection must remain identical to baseline
    post_rejection_snap = service.get_branch_snapshot(db_session, branch.id)
    assert post_rejection_snap.snapshot_hash == baseline_hash
    assert "Сато Кадзума" not in post_rejection_snap.active_characters



def test_dialogue_boast_does_not_become_world_fact(db_session, target_work_context):
    """
    Criterion: Dialogue claims/boasts (e.g. fairy blackmailing or characters bragging)
    are strictly marked is_world_fact=False and do NOT alter physical world facts in snapshot.
    """
    work, version = target_work_context
    service = BranchService()

    branch = service.create_branch(
        session=db_session,
        project_id=work.project_id,
        parent_work_version_id=version.id,
        cutoff_discourse_seq=182,
        branch_name="Branch Dialogue Truth Test"
    )

    plan = ScenePlan(
        scene_goal="Угроза феи",
        pov_character="Хачиман Хикигая",
        participants=["Хачиман Хикигая", "Сато Кадзума", "Фея"],
        initial_state_summary="Встреча в переулке.",
        mandatory_beats=["Шантаж феи пыльцой и шестом", "Переговоры с Хачиманом"],
        desired_outcome="Переговоры начаты."
    )

    sc, val, delta = service.draft_scene(
        session=db_session,
        branch_id=branch.id,
        scene_ordinal=1,
        title="Диалог с феей",
        plan=plan
    )

    # Check ProposedStateDelta: dialogue claims must have is_world_fact == False
    assert len(delta.dialogue_claims) >= 1
    boast_claim = next(c for c in delta.dialogue_claims if c["speaker"] == "Фея")
    assert boast_claim["is_world_fact"] is False
    assert "раструблю" in boast_claim["span_quote"]

    service.accept_scene(db_session, sc.id)

    # In NarrativeSnapshot, world_conditions and physical states must NOT turn fairy threat into fact
    snap = service.get_branch_snapshot(db_session, branch.id)
    assert "разоблачение перед ярмаркой" not in snap.world_conditions.values()


def test_injury_rollback_removes_status_from_subsequent_snapshots(db_session, target_work_context):
    """
    Criterion: Canceled injury or healed status is cleanly removed from subsequent snapshots.
    """
    work, version = target_work_context
    service = BranchService()

    branch = service.create_branch(
        session=db_session,
        project_id=work.project_id,
        parent_work_version_id=version.id,
        cutoff_discourse_seq=182,
        branch_name="Branch Status Healing Test"
    )

    plan_sc1 = ScenePlan(
        scene_goal="Сцена со стрессом",
        pov_character="Хачиман Хикигая",
        participants=["Хачиман Хикигая", "Сато Кадзума", "Фея"],
        initial_state_summary="Встреча в переулке.",
        mandatory_beats=[
            "Покупка контракта Сато Кадзумы",
            "Шантаж феи пыльцой и паника Кадзумы"
        ],
        desired_outcome="Кадзума бледен от паники."
    )

    sc1, val1, delta1 = service.draft_scene(
        session=db_session,
        branch_id=branch.id,
        scene_ordinal=1,
        title="Паника Кадзумы",
        plan=plan_sc1
    )
    service.accept_scene(db_session, sc1.id)

    # Snapshot at scene 1 has status 'panic_and_stress'
    snap_before = service.get_branch_snapshot(db_session, branch.id, through_scene_ordinal=1)
    assert "panic_and_stress" in snap_before.active_characters["Сато Кадзума"]["statuses"]

    # Roll back status
    service.rollback_injury(
        session=db_session,
        branch_id=branch.id,
        character_id="Сато Кадзума",
        injury_status="panic_and_stress"
    )

    # Snapshot after rollback MUST exclude 'panic_and_stress'
    snap_after = service.get_branch_snapshot(db_session, branch.id)
    assert "panic_and_stress" not in snap_after.active_characters["Сато Кадзума"]["statuses"]


def test_scene_validator_detects_pov_and_epistemic_violations(db_session, target_work_context):
    """
    Criterion: SceneValidator detects POV leakage (non-POV internal monologue)
    and epistemic violations (acting on unrevealed knowledge).
    """
    validator = SceneValidator()
    memory_engine = NarrativeMemoryEngine(db_session=db_session)
    from story_forecaster.domain.scope import ForecastScope
    scope = ForecastScope(
        project_id="p1",
        target_work_version_id="v1",
        target_max_discourse_seq=192
    )
    snapshot = memory_engine.get_snapshot(scope)

    # 1. Test POV violation: Narration describes non-POV character's internal unspoken thought
    plan_hachiman_pov = ScenePlan(
        scene_goal="План от лица Хачимана",
        pov_character="Хачиман Хикигая",
        participants=["Хачиман Хикигая", "Сато Кадзума"],
        initial_state_summary="В комнате.",
        mandatory_beats=["Разговор о крафте"],
        desired_outcome="Согласие."
    )
    leaky_content = (
        "Хачиман посмотрел на Кадзуму. "
        "Кадзума подумал про себя, что Босс выглядит устрашающе. "
        "Разговор о крафте завершился успешно."
    )
    val_pov_leak = validator.validate_scene(plan_hachiman_pov, leaky_content, snapshot)
    assert val_pov_leak.passed is False
    assert len(val_pov_leak.pov_violations) >= 1
    assert "Сато Кадзума" in val_pov_leak.pov_violations[0]

    # 2. Test Epistemic violation: Hachiman acting on fairy blackmail before Kazuma mentions it
    plan_epistemic = ScenePlan(
        scene_goal="Тест эпистемики",
        pov_character="Хачиман Хикигая",
        participants=["Хачиман Хикигая", "Сато Кадзума"],
        initial_state_summary="В комнате.",
        mandatory_beats=["Разговор о делах"],
        desired_outcome="Конец сцены."
    )
    epistemic_breach_content = (
        "Хачиман вошел в комнату. "
        "— Кадзума, я знаю, что фея устроила шантаж на ярмарке, так что займись крафтом. "
        "Разговор о делах завершился успешно."
    )
    val_epistemic = validator.validate_scene(plan_epistemic, epistemic_breach_content, snapshot)
    assert val_epistemic.passed is False
    assert len(val_epistemic.epistemic_violations) >= 1
    assert "fairy_blackmail_threat" in val_epistemic.epistemic_violations[0]


def test_scene_revision_supersedes_and_recomputes_downstream(db_session, target_work_context):
    """
    Criterion: Revisions supersede previous revisions without deleting history
    and recompute downstream snapshot deltas.
    """
    work, version = target_work_context
    service = BranchService()

    branch = service.create_branch(
        session=db_session,
        project_id=work.project_id,
        parent_work_version_id=version.id,
        cutoff_discourse_seq=182,
        branch_name="Branch Revisioning Test"
    )

    plan = ScenePlan(
        scene_goal="Вводная сцена",
        pov_character="Хачиман Хикигая",
        participants=["Хачиман Хикигая", "Сато Кадзума"],
        initial_state_summary="В штабе.",
        mandatory_beats=["Покупка контракта Сато Кадзумы"],
        desired_outcome="Кадзума принят."
    )

    sc1, val1, d1 = service.draft_scene(db_session, branch.id, 1, "Черновик v1", plan)
    service.accept_scene(db_session, sc1.id)

    # Revise scene with improved prose matching beat
    improved_prose = (
        "В штабе Хачимана мерцает системный экран. "
        "Хачиман подтвердил покупку контракта Сато Кадзумы за 400 000 золотых монет. "
        "Хачиман вручил ему Хорадримский Куб S-ранга: 'Отныне ты его главный оператор.' "
        "Кадзума благоговейно коснулся холодных граней артефакта."
    )
    rev_sc, rev_val, rev_delta = service.revise_scene(
        session=db_session,
        scene_id=sc1.id,
        new_content=improved_prose
    )
    assert rev_val.passed is True


    # Check old scene status
    db_session.refresh(sc1)
    assert sc1.status == "SUPERSEDED"
    assert rev_sc.revision_num == 2
    assert rev_sc.status == "ACCEPTED"

    # Verify downstream snapshot picks up the revised scene delta
    snap = service.get_branch_snapshot(db_session, branch.id)
    assert "Хорадримский Куб (S)" in snap.active_characters["Сато Кадзума"]["equipped"]


def test_export_branch_markdown_and_txt(db_session, target_work_context):
    """
    Criterion: Export fanfic branch cleanly to structured Markdown and TXT formats.
    """
    work, version = target_work_context
    service = BranchService()

    branch = service.create_branch(
        session=db_session,
        project_id=work.project_id,
        parent_work_version_id=version.id,
        cutoff_discourse_seq=182,
        branch_name="Золотой Путь Кадзумы",
        description="Альтернативное развитие союза Хачимана и Кадзумы"
    )

    plan = ScenePlan(
        scene_goal="Встреча союзников",
        pov_character="Хачиман Хикигая",
        participants=["Хачиман Хикигая", "Сато Кадзума"],
        initial_state_summary="Начало пути.",
        mandatory_beats=["Покупка контракта Сато Кадзумы"],
        desired_outcome="Союз заключен."
    )

    sc, _, _ = service.draft_scene(db_session, branch.id, 1, "Первый Контракт", plan)
    service.accept_scene(db_session, sc.id)

    # 1. Export to Markdown
    md_output = service.export_branch(db_session, branch.id, format="markdown")
    assert "# Золотой Путь Кадзумы" in md_output
    assert "## Сцена 1: Первый Контракт" in md_output
    assert "**POV:** Хачиман Хикигая" in md_output
    assert "---" in md_output

    # 2. Export to Plain Text
    txt_output = service.export_branch(db_session, branch.id, format="txt")
    assert "=== ВЕТКА: Золотой Путь Кадзумы ===" in txt_output
    assert "--- СЦЕНА 1: Первый Контракт (POV: Хачиман Хикигая) ---" in txt_output
    assert "#" not in txt_output
