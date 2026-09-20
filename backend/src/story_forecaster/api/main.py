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

# --- M6 / M7: Fanfic Writing, Arcs & Background Task Endpoints ---

from story_forecaster.db.models import Branch, BranchScene, Arc, AsyncTask
from story_forecaster.domain.writing import ScenePlan
from story_forecaster.domain.arc import ArcPlan, ArcMilestone, ReaderPromise, EditorialReview
from story_forecaster.writing.branch_service import BranchService
from story_forecaster.planning.arc_manager import ArcManager
from story_forecaster.tasks.queue import TaskQueue

class CreateBranchRequest(BaseModel):
    parent_work_version_id: Optional[str] = None
    cutoff_discourse_seq: int = Field(182, ge=1)
    branch_name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None

class DraftSceneRequest(BaseModel):
    scene_ordinal: int = Field(..., ge=1)
    title: str = Field(..., min_length=1, max_length=255)
    plan: ScenePlan
    provider_name: Literal["demo", "gemini"] = "demo"

class RejectSceneRequest(BaseModel):
    reason: str = Field("Deviation from character or plot constraints", max_length=500)

class ReviseSceneRequest(BaseModel):
    new_content: str = Field(..., min_length=10)
    new_plan: Optional[ScenePlan] = None

class RollbackInjuryRequest(BaseModel):
    character_id: str
    injury_status: str

class CreateArcRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    theme: str = Field("Использование Системы Зла и лазеек крафта", max_length=500)
    core_conflict: str = Field(..., max_length=500)
    milestones: List[ArcMilestone] = Field(default_factory=list)
    promises: List[ReaderPromise] = Field(default_factory=list)
    branch_id: Optional[str] = None

class EditorialReviewRequest(BaseModel):
    chapter_ordinal: int = Field(1, ge=1)
    scenes_content: List[str] = Field(..., min_length=1)


class EnqueueTaskRequest(BaseModel):
    task_type: str = Field(..., min_length=1)
    params: Dict[str, Any] = Field(default_factory=dict)
    max_cost_limit_usd: float = Field(0.50, ge=0.01, le=10.0)

@app.get("/api/writing/branches")
def list_branches(db: Session = Depends(get_db)):
    branches = db.query(Branch).order_by(Branch.created_at.desc()).all()
    results = []
    for b in branches:
        scene_count = db.query(BranchScene).filter(BranchScene.branch_id == b.id, BranchScene.status == "ACCEPTED").count()
        results.append({
            "id": b.id,
            "branch_name": b.branch_name,
            "parent_work_version_id": b.parent_work_version_id,
            "cutoff_discourse_seq": b.cutoff_discourse_seq,
            "description": b.description,
            "status": b.status,
            "accepted_scenes_count": scene_count,
            "created_at": b.created_at.isoformat() if b.created_at else None
        })
    return results

@app.post("/api/writing/branches")
def create_branch(req: CreateBranchRequest, db: Session = Depends(get_db)):
    work = db.query(Work).filter_by(role="target").first()
    proj_id = work.project_id if work else "default"
    ver_id = req.parent_work_version_id
    if not ver_id:
        try:
            resolved = resolve_scope(db)
            ver_id = resolved.version.id
        except Exception:
            ver_id = "default_ver"

    service = BranchService()
    branch = service.create_branch(
        session=db,
        project_id=proj_id,
        parent_work_version_id=ver_id,
        cutoff_discourse_seq=req.cutoff_discourse_seq,
        branch_name=req.branch_name,
        description=req.description
    )
    return {
        "id": branch.id,
        "branch_name": branch.branch_name,
        "parent_work_version_id": branch.parent_work_version_id,
        "cutoff_discourse_seq": branch.cutoff_discourse_seq,
        "status": branch.status
    }

@app.get("/api/writing/branches/{branch_id}/scenes")
def list_branch_scenes(branch_id: str, db: Session = Depends(get_db)):
    scenes = (
        db.query(BranchScene)
        .filter(BranchScene.branch_id == branch_id)
        .order_by(BranchScene.scene_ordinal.asc(), BranchScene.revision_num.desc())
        .all()
    )
    results = []
    for s in scenes:
        results.append({
            "id": s.id,
            "scene_ordinal": s.scene_ordinal,
            "revision_num": s.revision_num,
            "title": s.title,
            "status": s.status,
            "content": s.content,
            "scene_plan": s.scene_plan_json,
            "state_delta": s.state_delta_json,
            "created_at": s.created_at.isoformat() if s.created_at else None
        })
    return results

@app.post("/api/writing/branches/{branch_id}/draft")
def draft_scene(branch_id: str, req: DraftSceneRequest, db: Session = Depends(get_db)):
    service = BranchService()
    try:
        from story_forecaster.providers import get_provider
        provider = get_provider(provider_name=req.provider_name)
    except Exception:
        provider = None

    try:
        scene, validation, delta = service.draft_scene(
            session=db,
            branch_id=branch_id,
            scene_ordinal=req.scene_ordinal,
            title=req.title,
            plan=req.plan,
            provider=provider
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "scene_id": scene.id,
        "scene_ordinal": scene.scene_ordinal,
        "revision_num": scene.revision_num,
        "title": scene.title,
        "status": scene.status,
        "content": scene.content,
        "validation": validation.model_dump(),
        "proposed_state_delta": delta.model_dump()
    }

@app.post("/api/writing/scenes/{scene_id}/accept")
def accept_scene(scene_id: str, db: Session = Depends(get_db)):
    service = BranchService()
    try:
        scene = service.accept_scene(db, scene_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"id": scene.id, "status": scene.status, "message": "Scene accepted successfully."}

@app.post("/api/writing/scenes/{scene_id}/reject")
def reject_scene(scene_id: str, req: RejectSceneRequest, db: Session = Depends(get_db)):
    service = BranchService()
    try:
        scene = service.reject_scene(db, scene_id, reason=req.reason)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"id": scene.id, "status": scene.status, "message": "Scene rejected; delta quarantined."}

@app.post("/api/writing/scenes/{scene_id}/revise")
def revise_scene(scene_id: str, req: ReviseSceneRequest, db: Session = Depends(get_db)):
    service = BranchService()
    try:
        new_scene, validation, delta = service.revise_scene(
            session=db,
            scene_id=scene_id,
            new_content=req.new_content,
            new_plan=req.new_plan
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "new_scene_id": new_scene.id,
        "revision_num": new_scene.revision_num,
        "status": new_scene.status,
        "validation": validation.model_dump(),
        "state_delta": delta.model_dump()
    }

@app.post("/api/writing/branches/{branch_id}/rollback-injury")
def rollback_injury(branch_id: str, req: RollbackInjuryRequest, db: Session = Depends(get_db)):
    service = BranchService()
    try:
        healing_scene = service.rollback_injury(
            session=db,
            branch_id=branch_id,
            character_id=req.character_id,
            injury_status=req.injury_status
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": f"Injury/status '{req.injury_status}' canceled.", "healing_scene_id": healing_scene.id}

@app.get("/api/writing/branches/{branch_id}/snapshot")
def get_branch_snapshot(branch_id: str, through_ordinal: Optional[int] = None, db: Session = Depends(get_db)):
    service = BranchService()
    try:
        snap = service.get_branch_snapshot(db, branch_id, through_scene_ordinal=through_ordinal)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    return snap.model_dump()

@app.get("/api/writing/branches/{branch_id}/export")
def export_branch(branch_id: str, format: str = "markdown", db: Session = Depends(get_db)):
    service = BranchService()
    try:
        output = service.export_branch(db, branch_id, format=format)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"format": format, "content": output}

@app.get("/api/arcs")
def list_arcs(db: Session = Depends(get_db)):
    arcs = db.query(Arc).order_by(Arc.created_at.desc()).all()
    return [{"id": a.id, "title": a.title, "revision_num": a.revision_num, "status": a.status, "plan": a.arc_plan_json} for a in arcs]

@app.post("/api/arcs")
def create_arc(req: CreateArcRequest, db: Session = Depends(get_db)):
    work = db.query(Work).filter_by(role="target").first()
    proj_id = work.project_id if work else "default"
    mgr = ArcManager()
    arc = mgr.create_arc(
        session=db,
        project_id=proj_id,
        title=req.title,
        theme=req.theme,
        core_conflict=req.core_conflict,
        milestones=req.milestones,
        promises=req.promises,
        branch_id=req.branch_id
    )
    return {"id": arc.id, "title": arc.title, "revision_num": arc.revision_num, "status": arc.status}

@app.get("/api/arcs/{arc_id}/commitments")
def get_arc_commitments(arc_id: str, current_scene: int = Query(1, ge=1), db: Session = Depends(get_db)):
    mgr = ArcManager()
    plan = mgr.get_arc_plan(db, arc_id)
    if not plan:
        raise HTTPException(status_code=404, detail=f"Arc '{arc_id}' not found.")
    return mgr.track_commitments(plan, current_scene)

@app.post("/api/editor/review", response_model=EditorialReview)
def review_chapter(req: EditorialReviewRequest):
    mgr = ArcManager()
    from story_forecaster.writing.voice import VoiceRegistry
    reg = VoiceRegistry()
    profiles = [reg.get_profile(c) for c in reg.list_characters()]
    return mgr.editorial_review_chapter(
        chapter_ordinal=req.chapter_ordinal,
        scenes_content=req.scenes_content,
        voice_profiles=profiles
    )

@app.get("/api/tasks")
def list_tasks(db: Session = Depends(get_db)):
    queue = TaskQueue()
    tasks = queue.list_tasks(db)
    return [{
        "id": t.id,
        "task_type": t.task_type,
        "status": t.status,
        "progress_pct": t.progress_pct,
        "cost_usd": t.cost_usd,
        "error_message": t.error_message,
        "params": t.params_json,
        "result": t.result_json,
        "created_at": t.created_at.isoformat() if t.created_at else None
    } for t in tasks]

@app.post("/api/tasks")
def enqueue_task(req: EnqueueTaskRequest, db: Session = Depends(get_db)):
    queue = TaskQueue()
    task = queue.enqueue(session=db, task_type=req.task_type, params=req.params)
    return {"task_id": task.id, "status": task.status, "progress_pct": task.progress_pct}

@app.post("/api/tasks/{task_id}/run")
def run_task_worker(task_id: str, max_cost_limit: float = Query(0.50, ge=0.01), db: Session = Depends(get_db)):
    queue = TaskQueue()
    try:
        task = queue.execute_worker_cycle(db, task_id, max_cost_limit_usd=max_cost_limit)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "task_id": task.id,
        "status": task.status,
        "progress_pct": task.progress_pct,
        "cost_usd": task.cost_usd,
        "error_message": task.error_message,
        "result": task.result_json
    }

@app.post("/api/tasks/{task_id}/cancel")
def cancel_task(task_id: str, db: Session = Depends(get_db)):
    queue = TaskQueue()
    try:
        task = queue.cancel_task(db, task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"task_id": task.id, "status": task.status, "message": "Task canceled."}

# Mount Static Frontend
frontend_path = Path(__file__).resolve().parents[4] / "frontend"
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")


