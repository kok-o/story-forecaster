import pytest
from story_forecaster.retrieval.bm25 import BM25Index, tokenize_for_search
from story_forecaster.retrieval.engine import HybridRetrievalEngine
from story_forecaster.domain.scope import ForecastScope
from story_forecaster.db.session import SessionLocal
from story_forecaster.db.models import Scene, Chapter, Work

def test_bm25_index_scoring():
    index = BM25Index(k1=1.2, b=0.75)
    index.add_document("doc1", "Хачиман активировал Систему Абсолютного Зла и призвал помощника.")
    index.add_document("doc2", "Сато Кадзума тестирует Хорадримский Куб для крафта и трансмутации.")
    index.add_document("doc3", "Саэко Бусуджима тренируется с деревянным мечом боккэн в зале.")
    index.build()

    results = index.search("Куб трансмутации")
    assert len(results) > 0
    top_doc, score = results[0]
    assert top_doc == "doc2"
    assert score > 0.0

def test_retrieval_scope_boundary_zero_leakage():
    """
    Critical invariant test:
    Queries must NEVER return scenes beyond the discourse_seq cutoff,
    even if the search term strongly matches a future chapter.
    """
    db = SessionLocal()
    try:
        work = db.query(Work).filter_by(role="target").first()
        if not work:
            pytest.skip("No ingested work in DB")

        # Find cutoff for Chapter 22
        ch22 = db.query(Chapter).filter_by(ordinal=22).first()
        ch23 = db.query(Chapter).filter_by(ordinal=23).first()
        if not ch22 or not ch23:
            pytest.skip("Chapters 22 or 23 not found")

        last_scene_ch22 = db.query(Scene).filter_by(chapter_id=ch22.id).order_by(Scene.discourse_seq.desc()).first()
        max_seq_22 = last_scene_ch22.discourse_seq

        # Search for "Кадзума" (which features heavily in chapter 23)
        scope = ForecastScope(
            project_id=work.project_id,
            target_work_version_id=work.id,
            target_max_discourse_seq=max_seq_22,
            mode="retrospective"
        )

        engine = HybridRetrievalEngine(db_session=db)
        results = engine.search(query="Кадзума", scope=scope, top_k=20)

        # Strictly verify that NO result belongs to Chapter 23 or has discourse_seq > max_seq_22
        for r in results:
            assert r.discourse_seq <= max_seq_22, f"Future leak detected: {r.title} with seq {r.discourse_seq} > {max_seq_22}"
            assert r.chapter_num <= 22, f"Future chapter returned: Chapter {r.chapter_num}"
    finally:
        db.close()

def test_retrieval_version_isolation():
    """Verify that retrieval strictly limits indexed scenes to the specified work version."""
    db = SessionLocal()
    try:
        from story_forecaster.db.models import WorkVersion
        work = db.query(Work).filter_by(role="target").first()
        if not work:
            pytest.skip("No target work in DB")
        versions = db.query(WorkVersion).filter_by(work_id=work.id).all()
        if len(versions) < 2:
            pytest.skip("Multiple versions not present in test DB")
        
        target_ver = versions[-1]
        scope = ForecastScope(
            project_id=work.project_id,
            target_work_version_id=target_ver.id,
            target_max_discourse_seq=192
        )
        engine = HybridRetrievalEngine(db_session=db)
        results = engine.search("Куб", scope=scope, top_k=50)
        for r in results:
            ch = db.query(Chapter).filter_by(ordinal=r.chapter_num, work_version_id=target_ver.id).first()
            assert ch is not None
    finally:
        db.close()

