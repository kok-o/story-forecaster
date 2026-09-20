import pytest
from story_forecaster.domain.scope import ForecastScope
from story_forecaster.providers.demo import DemoProvider
from story_forecaster.domain.canon import ReferenceClassification

def test_demo_provider_forecast():
    scope = ForecastScope(
        project_id="test_proj",
        target_work_version_id="work_nb_evil",
        target_max_discourse_seq=192
    )
    provider = DemoProvider()
    result = provider.generate_hypotheses(
        scope=scope,
        target_context={"last_chapter": 23},
        author_precedents=[],
        canon_context=[],
        num_candidates=3
    )

    assert len(result.candidates) == 3
    assert result.target_work == "Система Абсолютного З.Л.А."
    assert result.provider == "demo"
    assert result.is_synthetic_demonstration is True

    for cand in result.candidates:
        assert cand.continuity_verified is False
        assert cand.verification_notes is not None
        assert len(cand.key_events) >= 3
        assert cand.topology.pov_character is not None

def test_demo_provider_classification():
    provider = DemoProvider()
    assert provider.classify_reference("Коносуба", "Кадзума прибыл из Коносубы") == ReferenceClassification.CROSSOVER_ENTITY
    assert provider.classify_reference("Хорадримский куб", "Использую Куб для крафта") == ReferenceClassification.BORROWED_MECHANIC
    assert provider.classify_reference("Саэко Бусуджима", "Саэко машет катаной") == ReferenceClassification.PRIMARY_CANON

def test_forecast_engine_continuity_verification():
    from story_forecaster.forecast.engine import ForecastEngine
    from story_forecaster.domain.forecast import ChapterTopology, PlotBeat, NarrativeMode, PredictionCandidate

    engine = ForecastEngine()
    scope = ForecastScope(
        project_id="test_proj",
        target_work_version_id="ver_test",
        target_max_discourse_seq=100
    )

    # Candidate with an illegal, unintroduced character
    cand_invalid = PredictionCandidate(
        candidate_id="cand_bad",
        title="Тест нарушения континуитета",
        topology=ChapterTopology(
            pov_character="Хачиман Хикигая",
            narrative_mode=NarrativeMode.ACTION
        ),
        key_events=[
            PlotBeat(
                ordinal=1,
                summary="Встреча с незнакомцем",
                participants=["Хачиман Хикигая", "НесуществующийПерсонажИкс"]
            )
        ],
        confidence_label="Low",
        rationale="Тестовый кандидат",
        continuity_verified=False
    )

    engine._verify_candidate_continuity(
        cand=cand_invalid,
        scope=scope,
        active_characters=["Хачиман Хикигая", "Юкиносита Юкино"],
        epistemic_states=[]
    )

    assert cand_invalid.continuity_verified is False
    assert cand_invalid.continuity_status == "failed"
    assert "НесуществующийПерсонажИкс" in cand_invalid.verification_notes

    # Candidate with valid characters
    cand_valid = PredictionCandidate(
        candidate_id="cand_good",
        title="Тест валидного континуитета",
        topology=ChapterTopology(
            pov_character="Хачиман Хикигая",
            narrative_mode=NarrativeMode.ACTION
        ),
        key_events=[
            PlotBeat(
                ordinal=1,
                summary="Разговор в штабе",
                participants=["Хачиман Хикигая", "Юкиносита Юкино", "Горожанин"]
            )
        ],
        confidence_label="High",
        rationale="Тестовый кандидат",
        continuity_verified=False
    )

    engine._verify_candidate_continuity(
        cand=cand_valid,
        scope=scope,
        active_characters=["Хачиман Хикигая", "Юкиносита Юкино"],
        epistemic_states=[]
    )

    assert cand_valid.continuity_verified is True
    assert cand_valid.continuity_status == "passed"
    assert "Verified" in cand_valid.verification_notes

def test_forecast_engine_full_run_with_demo():
    from story_forecaster.forecast.engine import ForecastEngine
    from story_forecaster.db import SessionLocal
    from story_forecaster.db.models import Work, WorkVersion

    db = SessionLocal()
    try:
        work = db.query(Work).filter_by(role="target").first()
        if not work:
            pytest.skip("No target work in DB")
        ver = db.query(WorkVersion).filter_by(work_id=work.id).first()
        if not ver:
            pytest.skip("No work version in DB")

        scope = ForecastScope(
            project_id=work.project_id,
            target_work_version_id=ver.id,
            target_max_discourse_seq=184,
            mode="retrospective"
        )
        engine = ForecastEngine()
        result = engine.run_forecast(scope=scope, num_candidates=2, persist_run=True)
        assert len(result.candidates) >= 1
        assert result.provider == "demo"
        assert result.candidates[0].continuity_status == "not_checked"
    finally:
        db.close()


