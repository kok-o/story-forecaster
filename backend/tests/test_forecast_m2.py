import json
import pytest
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from story_forecaster.db.models import Base, Project, Work, WorkVersion, Chapter, Scene, Run, Candidate
from story_forecaster.domain.scope import ForecastScope
from story_forecaster.domain.forecast import ForecastResult, PredictionCandidate, ChapterTopology, PlotBeat, NarrativeMode
from story_forecaster.forecast.context_builder import NarrativeContextBuilder
from story_forecaster.forecast.citation_verifier import CitationVerifier
from story_forecaster.forecast.engine import ForecastEngine
from story_forecaster.providers.base import BaseLLMProvider, ProviderUnavailableError
from story_forecaster.providers.gemini import GeminiProvider

@pytest.fixture
def m2_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    proj = Project(title="M2 Project")
    work = Work(title="M2 Book", author_name="Author N.B.", role="target", project=proj)
    session.add_all([proj, work])
    session.flush()

    ver = WorkVersion(work=work, original_sha256="sha_v1", normalized_sha256="sha_v1")
    session.add(ver)
    session.flush()

    ch1 = Chapter(work_version_id=ver.id, ordinal=1, title="Глава 1", char_count=5000)
    session.add(ch1)
    session.flush()

    for i in range(1, 6):
        sc = Scene(
            chapter_id=ch1.id,
            ordinal=i,
            discourse_seq=i,
            start_char=(i - 1) * 100,
            end_char=i * 100,
            content=f"Текст сцены {i}. Герой исследует подземелье и находит артефакт {i}.",
            summary=f"Сцена {i}"
        )
        session.add(sc)

    session.commit()
    yield session, ver.id, proj.id
    session.close()

def test_context_builder_volume_bounding_and_provenance(m2_db):
    session, ver_id, proj_id = m2_db
    scope = ForecastScope(
        project_id=proj_id,
        target_work_version_id=ver_id,
        target_max_discourse_seq=3
    )

    builder = NarrativeContextBuilder(default_char_budget=150, default_max_scenes=2)
    res = builder.build_context(db=session, scope=scope)

    # Max discourse_seq is 3, so scenes 4 and 5 must NEVER be considered
    for doc in res.sources:
        assert doc.discourse_seq <= 3
        assert doc.source_id in ["scene_1", "scene_2", "scene_3"]

    # Budget / limit checks
    assert len(res.sources) <= 2
    assert res.truncation_info["total_available_scenes"] == 3
    assert "<source id=" in res.formatted_source_text
    assert "</source_documents>" in res.formatted_source_text

def test_citation_verifier_detects_violations():
    verifier = CitationVerifier()
    scope = ForecastScope(
        project_id="p1",
        target_work_version_id="v1",
        target_max_discourse_seq=3
    )

    valid_sources = {"scene_1", "scene_2", "scene_3"}

    # Candidate 1: valid citation
    cand_valid = PredictionCandidate(
        candidate_id="c1",
        title="Valid Hypothesis",
        topology=ChapterTopology(pov_character="Hero", narrative_mode=NarrativeMode.ACTION),
        key_events=[PlotBeat(ordinal=1, summary="Event 1", source_citations=["scene_2"])],
        source_citations=["scene_1"],
        rationale="Logical",
        confidence_label="HIGH"
    )

    report1 = verifier.verify_citations([cand_valid], valid_sources, scope)
    assert report1.all_valid is True
    assert cand_valid.continuity_status != "citation_violation"

    # Candidate 2: hallucinated source citation
    cand_hallucinated = PredictionCandidate(
        candidate_id="c2",
        title="Hallucinated Citation Hypothesis",
        topology=ChapterTopology(pov_character="Hero", narrative_mode=NarrativeMode.ACTION),
        key_events=[PlotBeat(ordinal=1, summary="Event 1", source_citations=["scene_999"])],
        rationale="Unfounded",
        confidence_label="LOW"
    )

    report2 = verifier.verify_citations([cand_hallucinated], valid_sources, scope)
    assert report2.all_valid is False
    assert cand_hallucinated.continuity_status == "citation_violation"
    assert "scene_999" in cand_hallucinated.verification_notes

    # Candidate 3: future leakage citation (scene_4 > cutoff_seq 3)
    cand_future = PredictionCandidate(
        candidate_id="c3",
        title="Future Leakage Hypothesis",
        topology=ChapterTopology(pov_character="Hero", narrative_mode=NarrativeMode.ACTION),
        key_events=[PlotBeat(ordinal=1, summary="Event 1", source_citations=["scene_4"])],
        rationale="Cheating",
        confidence_label="LOW"
    )

    report3 = verifier.verify_citations([cand_future], valid_sources, scope)
    assert report3.all_valid is False
    assert cand_future.continuity_status == "citation_violation"
    assert "FUTURE_LEAKAGE" in cand_future.verification_notes

class MockInterceptingProvider(BaseLLMProvider):
    def __init__(self, return_error: bool = False):
        self.return_error = return_error
        self.last_target_context = None
        self.model_name = "mock-interceptor-v1"

    def classify_reference(self, entity_text: str, context_sentence: str):
        pass

    def generate_hypotheses(self, scope, target_context, author_precedents, canon_context, num_candidates=3):
        self.last_target_context = target_context
        if self.return_error:
            raise RuntimeError("Live API rate limit or network timeout")

        cand = PredictionCandidate(
            candidate_id="mock_c1",
            title="Intercepted Candidate",
            topology=ChapterTopology(pov_character="Hero", narrative_mode=NarrativeMode.ACTION),
            key_events=[PlotBeat(ordinal=1, summary="Action beat", source_citations=["scene_1"])],
            source_citations=["scene_1"],
            rationale="Test",
            confidence_label="HIGH"
        )
        res = ForecastResult(
            target_work="Test",
            cutoff_chapter=1,
            candidates=[cand],
            generated_at_utc="2026-09-20T00:00:00Z",
            scope_manifest_hash=scope.manifest_hash(),
            provider="mock-interceptor-v1"
        )
        res.raw_usage = {"prompt_token_count": 520, "candidates_token_count": 180, "total_token_count": 700}
        return res

def test_forecast_engine_run_persistence_and_failure_auditing(m2_db, monkeypatch):
    session, ver_id, proj_id = m2_db
    monkeypatch.setattr("story_forecaster.forecast.engine.SessionLocal", lambda: session)

    scope = ForecastScope(
        project_id=proj_id,
        target_work_version_id=ver_id,
        target_max_discourse_seq=3
    )

    # 1. Test successful run audit
    mock_provider = MockInterceptingProvider(return_error=False)
    engine = ForecastEngine(provider=mock_provider)

    result = engine.run_forecast(scope=scope, persist_run=True)
    assert len(result.included_sources) > 0
    assert result.context_truncation_info["total_available_scenes"] == 3

    # Verify Run in DB
    db_run = session.query(Run).filter_by(project_id=proj_id).first()
    assert db_run is not None
    assert db_run.status == "COMPLETED"
    assert db_run.prompt_version == "v2.0-m2"
    assert db_run.model_name == "mock-interceptor-v1"
    assert db_run.usage_json.get("total_token_count") == 700

    # Verify Candidate in DB
    db_cand = session.query(Candidate).filter_by(run_id=db_run.id).first()
    assert db_cand is not None
    assert db_cand.raw_candidate_json["candidate_id"] == "mock_c1"
    assert "scene_1" in db_cand.citations_json

    # 2. Test failed run audit (failure must NOT be masked)
    failing_provider = MockInterceptingProvider(return_error=True)
    failing_engine = ForecastEngine(provider=failing_provider)

    with pytest.raises(RuntimeError, match="Live API rate limit or network timeout"):
        failing_engine.run_forecast(scope=scope, persist_run=True)

    failed_runs = session.query(Run).filter_by(status="FAILED").all()
    assert len(failed_runs) == 1
    assert "Live API rate limit or network timeout" in failed_runs[0].error_message
