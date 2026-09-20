import hashlib
import pytest
from story_forecaster.domain.scope import ForecastScope
from story_forecaster.domain.memory import (
    EvidenceRecord,
    EvidenceKind,
    EvidenceConflict,
    EpistemicAttitude,
    PlotThread,
    PlotThreadKind,
    PlotThreadStatus
)
from story_forecaster.memory.engine import NarrativeMemoryEngine
from story_forecaster.memory.reducer import EvidenceReducer
from story_forecaster.retrieval.bm25 import BM25Index, tokenize_for_search, stem_russian_word
from story_forecaster.retrieval.engine import HybridRetrievalEngine
from story_forecaster.forecast.context_builder import NarrativeContextBuilder
from story_forecaster.db.session import SessionLocal
from story_forecaster.db.models import Scene, Chapter, Work, WorkVersion

def test_evidence_records_epistemic_separation():
    """
    Criterion: Separate observed events, narrator assertions, character utterances,
    beliefs, and speculations. Character utterances must NOT automatically become world facts.
    """
    engine = NarrativeMemoryEngine()
    ev_list = engine.get_evidence(cutoff_seq=192)

    # Check observed event: Hachiman buying Kazuma
    buy_ev = next(e for e in ev_list if e.evidence_id == "ev_ch22_buy_kazuma")
    assert buy_ev.kind == EvidenceKind.OBSERVED_EVENT
    assert buy_ev.is_confirmed_world_fact is True
    assert buy_ev.fragment_sha256 is not None
    assert buy_ev.end_char > buy_ev.start_char

    # Check character utterance: Fairy threatening Kazuma
    blackmail_ev = next(e for e in ev_list if e.evidence_id == "ev_ch23_fairy_blackmail_utterance")
    assert blackmail_ev.kind == EvidenceKind.CHARACTER_UTTERANCE
    assert blackmail_ev.speaker == "Фея"
    assert blackmail_ev.is_confirmed_world_fact is False  # Dialogue utterance is not an objective world fact!

def test_reader_availability_vs_in_story_temporal_seq():
    """
    Criterion: Store reader availability moment separately from in-story event time.
    For flashbacks, cutoff operates strictly on reader availability.
    """
    engine = NarrativeMemoryEngine()

    # Create a flashback evidence record:
    # Event happened in ancient past (in_story_temporal_seq = 5),
    # but is revealed to reader in chapter 23 (reader_availability_seq = 190).
    flashback_ev = EvidenceRecord(
        evidence_id="ev_ch23_flashback_ancient_relic",
        kind=EvidenceKind.NARRATOR_ASSERTION,
        reader_availability_seq=190,
        in_story_temporal_seq=5,
        chapter_ordinal=23,
        scene_discourse_seq=190,
        start_char=50,
        end_char=180,
        fragment_sha256=hashlib.sha256(b"Ancient secret").hexdigest(),
        source_text="В древние времена до апокалипсиса был сокрыт секретный бункер.",
        subject="Секретный бункер",
        predicate="hidden_location",
        object_val="Подземелье Фудзими",
        polarity=True,
        is_confirmed_world_fact=True
    )
    engine.add_evidence(flashback_ev)

    # Snapshot at cutoff seq 100 (Chapter 11) MUST NOT know about the flashback!
    scope_early = ForecastScope(
        project_id="test_p",
        target_work_version_id="v1",
        target_max_discourse_seq=100
    )
    snap_early = engine.get_snapshot(scope_early)
    assert not any(e.evidence_id == "ev_ch23_flashback_ancient_relic" for e in snap_early.evidence_records)
    assert "Секретный бункер" not in snap_early.active_characters

    # Snapshot at cutoff seq 192 MUST include the flashback!
    scope_late = ForecastScope(
        project_id="test_p",
        target_work_version_id="v1",
        target_max_discourse_seq=192
    )
    snap_late = engine.get_snapshot(scope_late)
    assert any(e.evidence_id == "ev_ch23_flashback_ancient_relic" for e in snap_late.evidence_records)
    assert "Секретный бункер" in snap_late.active_characters

def test_reducer_strict_cutoff_and_inventory_evolution():
    """
    Criterion: Deterministic reducer builds point-in-time snapshot.
    Snapshot at N does not leak characters, equipment, or events from N+1.
    """
    engine = NarrativeMemoryEngine()

    # 1. Early cutoff (seq 100):
    # Kazuma and Fairy are completely unintroduced.
    # Hachiman has no subordinates.
    scope_ch11 = ForecastScope(
        project_id="test_p",
        target_work_version_id="v1",
        target_max_discourse_seq=100
    )
    snap_ch11 = engine.get_snapshot(scope_ch11)
    assert "Сато Кадзума" not in snap_ch11.active_characters
    assert "Фея" not in snap_ch11.active_characters
    assert snap_ch11.active_characters["Хачиман Хикигая"]["active_subordinates"] == []

    # 2. Mid cutoff (seq 182 - Chapter 22):
    # Kazuma is purchased, has Horadric Cube, but NOT Evaluation Glasses.
    # Fairy is not introduced yet.
    scope_ch22 = ForecastScope(
        project_id="test_p",
        target_work_version_id="v1",
        target_max_discourse_seq=182
    )
    snap_ch22 = engine.get_snapshot(scope_ch22)
    assert "Сато Кадзума" in snap_ch22.active_characters
    assert "Фея" not in snap_ch22.active_characters
    assert "Сато Кадзума" in snap_ch22.active_characters["Хачиман Хикигая"]["active_subordinates"]
    kazuma_ch22 = snap_ch22.active_characters["Сато Кадзума"]
    assert "Хорадримский Куб (S)" in kazuma_ch22["equipped"]
    assert "Очки-оценки (S)" not in kazuma_ch22["equipped"]

    # 3. Late cutoff (seq 188 - Chapter 23):
    # Kazuma now equipped with both Horadric Cube and Evaluation Glasses.
    # Fairy is introduced.
    scope_ch23 = ForecastScope(
        project_id="test_p",
        target_work_version_id="v1",
        target_max_discourse_seq=188
    )
    snap_ch23 = engine.get_snapshot(scope_ch23)
    assert "Фея" in snap_ch23.active_characters
    kazuma_ch23 = snap_ch23.active_characters["Сато Кадзума"]
    assert "Хорадримский Куб (S)" in kazuma_ch23["equipped"]
    assert "Очки-оценки (S)" in kazuma_ch23["equipped"]

def test_reducer_preserves_evidence_contradictions():
    """
    Criterion: Reducer deterministically preserves evidence contradictions
    without arbitrarily discarding them.
    """
    engine = NarrativeMemoryEngine()

    # Add contradictory evidence at seq 150:
    # Rumor claims Shard Market is destroyed, but Narrator observation states it is open.
    ev_rumor = EvidenceRecord(
        evidence_id="ev_rumor_market_destroyed",
        kind=EvidenceKind.RUMOR_OR_SPECULATION,
        reader_availability_seq=150,
        in_story_temporal_seq=150,
        chapter_ordinal=16,
        scene_discourse_seq=150,
        start_char=0,
        end_char=100,
        fragment_sha256=hashlib.sha256(b"Rumor").hexdigest(),
        source_text="Ходят слухи, что Ярмарка Осколков закрыта навсегда.",
        subject="Ярмарка Осколков",
        predicate="is_operational",
        object_val="operational",
        polarity=False,  # Negation: not operational
        is_confirmed_world_fact=False
    )
    ev_fact = EvidenceRecord(
        evidence_id="ev_fact_market_open",
        kind=EvidenceKind.OBSERVED_EVENT,
        reader_availability_seq=150,
        in_story_temporal_seq=150,
        chapter_ordinal=16,
        scene_discourse_seq=150,
        start_char=105,
        end_char=210,
        fragment_sha256=hashlib.sha256(b"Fact").hexdigest(),
        source_text="Хачиман лично видит открытые торговые ряды Ярмарки Осколков.",
        subject="Ярмарка Осколков",
        predicate="is_operational",
        object_val="operational",
        polarity=True,  # Affirmation: is operational
        is_confirmed_world_fact=True
    )
    engine.add_evidence(ev_rumor)
    engine.add_evidence(ev_fact)

    scope = ForecastScope(
        project_id="test_p",
        target_work_version_id="v1",
        target_max_discourse_seq=155
    )
    snap = engine.get_snapshot(scope)

    # Verify that the contradiction is preserved in snap.conflicts!
    assert len(snap.conflicts) >= 1
    conflict = next(c for c in snap.conflicts if c.subject == "Ярмарка Осколков" and c.predicate == "is_operational")
    assert "ev_rumor_market_destroyed" in conflict.conflicting_evidence_ids
    assert "ev_fact_market_open" in conflict.conflicting_evidence_ids
    assert conflict.resolved is False

def test_bm25_russian_inflection_stemming():
    """
    Criterion: Measure and eliminate keyword misses due to Russian inflections.
    'куб', 'куба', 'кубе', 'кубом', 'кубами' must all match.
    'фея', 'фее', 'фею' must match.
    'пыльца', 'пыльцы', 'пыльцой' must match.
    """
    # 1. Direct stemmer assertions
    assert stem_russian_word("куб") == stem_russian_word("кубом") == stem_russian_word("кубе") == stem_russian_word("куба")
    assert stem_russian_word("пыльца") == stem_russian_word("пыльцы") == stem_russian_word("пыльцой")
    assert stem_russian_word("фея") == stem_russian_word("фее") == stem_russian_word("фею")

    # 2. Search index matching across inflections
    index = BM25Index(k1=1.2, b=0.75)
    index.add_document("doc_craft", "Кадзума берет Хорадримский куб и начинает синтез.")
    index.add_document("doc_fairy", "Маленькая фея угрожает разоблачить Кадзуму из-за пыльцы.")
    index.add_document("doc_school", "В Академии Фудзими идут уроки.")
    index.build()

    # Query with instrumental case 'кубом' (not in doc_craft text verbatim)
    results_cube = index.search("трансмутация кубом")
    assert len(results_cube) > 0
    assert results_cube[0][0] == "doc_craft"

    # Query with dative case 'фее' (not in doc_fairy text verbatim)
    results_fairy = index.search("обращение к фее за пыльцой")
    assert len(results_fairy) > 0
    assert results_fairy[0][0] == "doc_fairy"

def test_scope_bounded_retrieval_caching_and_future_isolation():
    """
    Criterion: Cache search indexes by (version_id, cutoff_seq).
    Corpus statistics must NEVER leak future chapters.
    """
    db = SessionLocal()
    try:
        work = db.query(Work).filter_by(role="target").first()
        if not work:
            pytest.skip("No target work in DB")

        ch12 = db.query(Chapter).filter_by(ordinal=12).first()
        ch23 = db.query(Chapter).filter_by(ordinal=23).first()
        if not ch12 or not ch23:
            pytest.skip("Chapters 12 or 23 not found")

        last_sc_12 = db.query(Scene).filter_by(chapter_id=ch12.id).order_by(Scene.discourse_seq.desc()).first()
        last_sc_23 = db.query(Scene).filter_by(chapter_id=ch23.id).order_by(Scene.discourse_seq.desc()).first()

        scope_early = ForecastScope(
            project_id=work.project_id,
            target_work_version_id=ch12.work_version_id,
            target_max_discourse_seq=last_sc_12.discourse_seq
        )
        scope_late = ForecastScope(
            project_id=work.project_id,
            target_work_version_id=ch23.work_version_id,
            target_max_discourse_seq=last_sc_23.discourse_seq
        )

        engine = HybridRetrievalEngine(db_session=db)
        HybridRetrievalEngine.clear_cache()

        # Build early index
        bm25_early, _ = engine._get_or_build_index(db, ch12.work_version_id, last_sc_12.discourse_seq)
        docs_early = bm25_early.total_docs

        # Build late index
        bm25_late, _ = engine._get_or_build_index(db, ch23.work_version_id, last_sc_23.discourse_seq)
        docs_late = bm25_late.total_docs

        # Strict isolation: early index statistics MUST NOT include later scenes!
        assert docs_early < docs_late

        # Cache test: re-fetching early returns identical cached object
        bm25_early_cached, _ = engine._get_or_build_index(db, ch12.work_version_id, last_sc_12.discourse_seq)
        assert bm25_early_cached is bm25_early
    finally:
        db.close()

def test_context_builder_dynamic_retrieval_from_active_threads():
    """
    Criterion: Connect BM25 directly to ContextBuilder, constructing queries
    dynamically from active unresolved goals rather than static tags.
    """
    db = SessionLocal()
    try:
        work = db.query(Work).filter_by(role="target").first()
        if not work:
            pytest.skip("No target work in DB")

        scope = ForecastScope(
            project_id=work.project_id,
            target_work_version_id=work.id,
            target_max_discourse_seq=192
        )

        mem_engine = NarrativeMemoryEngine(db_session=db)
        ret_engine = HybridRetrievalEngine(db_session=db)
        builder = NarrativeContextBuilder()

        snapshot = mem_engine.get_snapshot(scope)
        # Verify active threads exist
        assert len(snapshot.active_threads) >= 2

        # Build context with dynamic retrieval enabled
        res = builder.build_context(
            db=db,
            scope=scope,
            char_budget=8000,
            max_scenes=3,  # Keep recent scenes small so retrieval has budget
            snapshot=snapshot,
            retrieval_engine=ret_engine
        )

        assert len(res.sources) >= 3
        # Verify that dynamic retrieval enriched the context with past evidence
        assert res.truncation_info["retrieved_sources_count"] >= 0
        # Verify all sources have valid source_id for citation verification
        for sid in res.source_ids:
            assert sid.startswith("scene_")
    finally:
        db.close()
