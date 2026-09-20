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
from story_forecaster.domain.resolver import resolve_scope

app = FastAPI(
    title="Story Forecaster API",
    version="1.0.0",
    description="Deterministic context compiler, hybrid retrieval, and narrative forecasting engine for Author N.B."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
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
    query: str = Field(..., min_length=1, max_length=500, description="Поисковый запрос")
    cutoff_chapter: int = Field(23, ge=1, le=1000, description="Номер граничной главы")
    top_k: int = Field(10, ge=1, le=50, description="Количество результатов")

class ForecastRequest(BaseModel):
    cutoff_chapter: int = Field(23, ge=1, le=1000, description="Номер граничной главы")
    num_candidates: int = Field(3, ge=1, le=10, description="Количество кандидатов")
    provider_name: Literal["demo", "gemini"] = Field("demo", description="Провайдер генерации гипотез")

class BacktestRequest(BaseModel):
    cutoff_chapter: int = Field(22, ge=1, le=1000, description="Номер граничной главы для бэктеста")
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
    try:
        resolved = resolve_scope(db)
        version_id = resolved.version.id
    except ValueError:
        return []

    chapters = db.query(Chapter).filter_by(work_version_id=version_id).order_by(Chapter.ordinal.asc()).all()
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
def get_canon_summary(cutoff_chapter: int = Query(23, ge=1, le=1000), db: Session = Depends(get_db)):
    try:
        resolved = resolve_scope(db, cutoff_chapter=cutoff_chapter)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    registry = CanonDivergenceRegistry()
    return registry.get_divergence_summary(resolved.scope)

@app.post("/api/retrieval/search", response_model=List[SearchResult])
def search_scenes(req: SearchRequest, db: Session = Depends(get_db)):
    try:
        resolved = resolve_scope(db, cutoff_chapter=req.cutoff_chapter)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    engine = HybridRetrievalEngine(db_session=db)
    return engine.search(query=req.query, scope=resolved.scope, top_k=req.top_k)

@app.post("/api/forecast", response_model=ForecastResult)
def run_forecast(req: ForecastRequest, db: Session = Depends(get_db)):
    try:
        resolved = resolve_scope(db, cutoff_chapter=req.cutoff_chapter)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        from story_forecaster.providers import get_provider, ProviderUnavailableError
        provider = get_provider(provider_name=req.provider_name)
    except ProviderUnavailableError as e:
        raise HTTPException(status_code=400, detail=str(e))

    engine = ForecastEngine(provider=provider)
    result = engine.run_forecast(scope=resolved.scope, num_candidates=req.num_candidates, persist_run=True)
    return result

@app.post("/api/backtest", response_model=EvaluationReport)
def run_backtest(req: BacktestRequest, db: Session = Depends(get_db)):
    try:
        resolved = resolve_scope(db, cutoff_chapter=req.cutoff_chapter)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    hidden_chapter_num = req.cutoff_chapter + 1
    try:
        gold = get_gold_chapter(hidden_chapter_num)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        from story_forecaster.providers import get_provider, ProviderUnavailableError
        provider = get_provider(provider_name=req.provider_name)
    except ProviderUnavailableError as e:
        raise HTTPException(status_code=400, detail=str(e))

    engine = ForecastEngine(provider=provider)
    result = engine.run_forecast(scope=resolved.scope, num_candidates=3, persist_run=True)

    evaluator = BacktestEvaluator()
    report = evaluator.evaluate_forecast(result, gold, cutoff_chapter=req.cutoff_chapter)
    return report

@app.get("/api/memory/snapshot")
def get_memory_snapshot(cutoff_chapter: int = Query(23, ge=1, le=1000), db: Session = Depends(get_db)):
    try:
        resolved = resolve_scope(db, cutoff_chapter=cutoff_chapter)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    mem_engine = NarrativeMemoryEngine()
    snapshot = mem_engine.get_snapshot(resolved.scope)
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

