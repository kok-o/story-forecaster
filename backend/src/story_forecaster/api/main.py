from pathlib import Path
from typing import List, Optional, Dict, Any, Literal
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from story_forecaster.db.session import SessionLocal
from story_forecaster.db.models import Work, Chapter, Scene, Run, Candidate
from story_forecaster.domain.scope import ForecastScope
from story_forecaster.domain.forecast import ForecastResult
from story_forecaster.forecast.engine import ForecastEngine
from story_forecaster.canon.registry import CanonDivergenceRegistry
from story_forecaster.retrieval import HybridRetrievalEngine, SearchResult
from story_forecaster.evaluation import get_gold_chapter, BacktestEvaluator, EvaluationReport
from story_forecaster.memory.engine import NarrativeMemoryEngine

app = FastAPI(
    title="Story Forecaster API",
    version="1.0.0",
    description="Deterministic context compiler, hybrid retrieval, and narrative forecasting engine for Author N.B."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Request Models
class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Поисковый запрос")
    cutoff_chapter: int = Field(23, ge=1, description="Номер граничной главы")
    top_k: int = Field(10, ge=1, le=50, description="Количество результатов")

class ForecastRequest(BaseModel):
    cutoff_chapter: int = Field(23, ge=1, description="Номер граничной главы")
    num_candidates: int = Field(3, ge=1, le=10, description="Количество кандидатов")
    provider_name: Literal["demo", "gemini"] = Field("demo", description="Провайдер генерации гипотез")

class BacktestRequest(BaseModel):
    cutoff_chapter: int = Field(22, ge=1, description="Номер граничной главы для бэктеста")
    provider_name: Literal["demo", "gemini"] = Field("demo", description="Провайдер генерации гипотез")

@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "Story Forecaster API", "version": "1.0.0"}

@app.get("/api/work")
def get_target_work(db: Session = Depends(get_db)):
    work = db.query(Work).filter_by(role="target").first()
    if not work:
        raise HTTPException(status_code=404, detail="Target work not ingested yet")
    
    from story_forecaster.db.models import WorkVersion
    latest_ver = db.query(WorkVersion).filter_by(work_id=work.id).order_by(WorkVersion.created_at.desc()).first()
    if not latest_ver:
        return {"id": work.id, "title": work.title, "chapters_count": 0, "scenes_count": 0}

    chapters_count = db.query(Chapter).filter_by(work_version_id=latest_ver.id).count()
    scenes_count = db.query(Scene).join(Chapter).filter(Chapter.work_version_id == latest_ver.id).count()

    return {
        "id": work.id,
        "title": work.title,
        "author_name": work.author_name,
        "role": work.role,
        "version_id": latest_ver.id,
        "chapters_count": chapters_count,
        "scenes_count": scenes_count
    }

@app.get("/api/chapters")
def get_chapters(db: Session = Depends(get_db)):
    from story_forecaster.db.models import WorkVersion
    work = db.query(Work).filter_by(role="target").first()
    if not work:
        return []
    latest_ver = db.query(WorkVersion).filter_by(work_id=work.id).order_by(WorkVersion.created_at.desc()).first()
    if not latest_ver:
        return []

    chapters = db.query(Chapter).filter_by(work_version_id=latest_ver.id).order_by(Chapter.ordinal.asc()).all()
    results = []
    for ch in chapters:
        scenes = db.query(Scene).filter_by(chapter_id=ch.id).order_by(Scene.discourse_seq.asc()).all()
        results.append({
            "id": ch.id,
            "ordinal": ch.ordinal,
            "title": ch.title,
            "char_count": ch.char_count,
            "scene_count": len(scenes),
            "discourse_seq_start": scenes[0].discourse_seq if scenes else None,
            "discourse_seq_end": scenes[-1].discourse_seq if scenes else None
        })
    return results

@app.get("/api/canon/summary")
def get_canon_summary(cutoff_chapter: int = 23, db: Session = Depends(get_db)):
    registry = CanonDivergenceRegistry()
    target_ch = db.query(Chapter).filter_by(ordinal=cutoff_chapter).first()
    max_seq = 192
    if target_ch:
        last_scene = db.query(Scene).filter_by(chapter_id=target_ch.id).order_by(Scene.discourse_seq.desc()).first()
        if last_scene:
            max_seq = last_scene.discourse_seq

    scope = ForecastScope(
        project_id="default",
        target_work_version_id="target_v1",
        target_max_discourse_seq=max_seq
    )
    return registry.get_divergence_summary(scope)

@app.post("/api/retrieval/search", response_model=List[SearchResult])
def search_scenes(req: SearchRequest, db: Session = Depends(get_db)):
    work = db.query(Work).filter_by(role="target").first()
    if not work:
        raise HTTPException(status_code=404, detail="Target work not found")

    from story_forecaster.db.models import WorkVersion
    latest_ver = db.query(WorkVersion).filter_by(work_id=work.id).order_by(WorkVersion.created_at.desc()).first()
    version_id = latest_ver.id if latest_ver else work.id

    target_ch = db.query(Chapter).filter(
        (Chapter.work_version_id == version_id) if latest_ver else True,
        Chapter.ordinal == req.cutoff_chapter
    ).first()
    if not target_ch:
        raise HTTPException(status_code=404, detail=f"Chapter {req.cutoff_chapter} not found")

    last_scene = db.query(Scene).filter_by(chapter_id=target_ch.id).order_by(Scene.discourse_seq.desc()).first()
    max_seq = last_scene.discourse_seq if last_scene else req.cutoff_chapter

    scope = ForecastScope(
        project_id=work.project_id,
        target_work_version_id=version_id,
        target_max_discourse_seq=max_seq,
        mode="retrospective"
    )

    engine = HybridRetrievalEngine(db_session=db)
    return engine.search(query=req.query, scope=scope, top_k=req.top_k)

@app.post("/api/forecast", response_model=ForecastResult)
def run_forecast(req: ForecastRequest, db: Session = Depends(get_db)):
    work = db.query(Work).filter_by(role="target").first()
    if not work:
        raise HTTPException(status_code=404, detail="Target work not found")

    from story_forecaster.db.models import WorkVersion
    latest_ver = db.query(WorkVersion).filter_by(work_id=work.id).order_by(WorkVersion.created_at.desc()).first()
    version_id = latest_ver.id if latest_ver else work.id

    target_ch = db.query(Chapter).filter(
        (Chapter.work_version_id == version_id) if latest_ver else True,
        Chapter.ordinal == req.cutoff_chapter
    ).first()
    if not target_ch:
        raise HTTPException(status_code=404, detail=f"Chapter {req.cutoff_chapter} not found")

    last_scene = db.query(Scene).filter_by(chapter_id=target_ch.id).order_by(Scene.discourse_seq.desc()).first()
    max_seq = last_scene.discourse_seq if last_scene else req.cutoff_chapter

    scope = ForecastScope(
        project_id=work.project_id,
        target_work_version_id=version_id,
        target_max_discourse_seq=max_seq,
        mode="retrospective"
    )

    if req.provider_name == "gemini":
        from story_forecaster.providers.gemini import GeminiProvider
        provider = GeminiProvider()
        if not provider.is_available():
            raise HTTPException(
                status_code=400,
                detail="Gemini provider selected, but GEMINI_API_KEY is not set or google-genai is not installed in the environment."
            )
    else:
        from story_forecaster.providers.demo import DemoProvider
        provider = DemoProvider()

    engine = ForecastEngine(provider=provider)
    result = engine.run_forecast(scope=scope, num_candidates=req.num_candidates, persist_run=True)
    return result

@app.post("/api/backtest", response_model=EvaluationReport)
def run_backtest(req: BacktestRequest, db: Session = Depends(get_db)):
    work = db.query(Work).filter_by(role="target").first()
    if not work:
        raise HTTPException(status_code=404, detail="Target work not found")

    from story_forecaster.db.models import WorkVersion
    latest_ver = db.query(WorkVersion).filter_by(work_id=work.id).order_by(WorkVersion.created_at.desc()).first()
    version_id = latest_ver.id if latest_ver else work.id

    target_ch = db.query(Chapter).filter(
        (Chapter.work_version_id == version_id) if latest_ver else True,
        Chapter.ordinal == req.cutoff_chapter
    ).first()
    if not target_ch:
        raise HTTPException(status_code=404, detail=f"Chapter {req.cutoff_chapter} not found")

    last_scene = db.query(Scene).filter_by(chapter_id=target_ch.id).order_by(Scene.discourse_seq.desc()).first()
    max_seq = last_scene.discourse_seq if last_scene else req.cutoff_chapter

    hidden_chapter_num = req.cutoff_chapter + 1
    try:
        gold = get_gold_chapter(hidden_chapter_num)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    scope = ForecastScope(
        project_id=work.project_id,
        target_work_version_id=version_id,
        target_max_discourse_seq=max_seq,
        mode="retrospective"
    )

    from story_forecaster.providers import get_provider
    provider = get_provider(prefer_gemini=(req.provider_name == "gemini"))
    engine = ForecastEngine(provider=provider)
    result = engine.run_forecast(scope=scope, num_candidates=3, persist_run=True)

    evaluator = BacktestEvaluator()
    report = evaluator.evaluate_forecast(result, gold, cutoff_chapter=req.cutoff_chapter)
    return report

@app.get("/api/memory/snapshot")
def get_memory_snapshot(cutoff_chapter: int = Query(23, ge=1), db: Session = Depends(get_db)):
    work = db.query(Work).filter_by(role="target").first()
    if not work:
        raise HTTPException(status_code=404, detail="Target work not found")

    from story_forecaster.db.models import WorkVersion
    latest_ver = db.query(WorkVersion).filter_by(work_id=work.id).order_by(WorkVersion.created_at.desc()).first()
    version_id = latest_ver.id if latest_ver else work.id

    target_ch = db.query(Chapter).filter(
        (Chapter.work_version_id == version_id) if latest_ver else True,
        Chapter.ordinal == cutoff_chapter
    ).first()
    if not target_ch:
        raise HTTPException(status_code=404, detail=f"Chapter {cutoff_chapter} not found")

    last_scene = db.query(Scene).filter_by(chapter_id=target_ch.id).order_by(Scene.discourse_seq.desc()).first()
    max_seq = last_scene.discourse_seq if last_scene else cutoff_chapter

    scope = ForecastScope(
        project_id=work.project_id,
        target_work_version_id=version_id,
        target_max_discourse_seq=max_seq,
        mode="retrospective"
    )

    mem_engine = NarrativeMemoryEngine()
    snapshot = mem_engine.get_snapshot(scope)
    return snapshot.model_dump()

@app.get("/api/author/precedents")
def get_author_precedents(tags: str = "fairy_blackmail,extortion,subordinates"):
    from story_forecaster.author.precedents import AuthorPrecedentLibrary
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    lib = AuthorPrecedentLibrary()
    transitions = lib.query_precedents(None, tag_list)
    excerpts = lib.query_corpus_excerpts(tag_list, limit=5)
    profile = lib.get_profile()
    return {
        "author": profile.author_name,
        "signature_traits": profile.signature_traits,
        "abstracted_transitions": [t.model_dump() for t in transitions],
        "corpus_excerpts": excerpts
    }

# Mount Static Frontend
frontend_path = Path(__file__).resolve().parents[4] / "frontend"
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")

