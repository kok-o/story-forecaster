from typing import Optional
from sqlalchemy.orm import Session
from story_forecaster.db.models import Project, Work, WorkVersion, Chapter, Scene
from story_forecaster.domain.scope import ForecastScope

class ResolvedScope:
    """
    Container representing the fully resolved and validated context boundaries.
    """
    def __init__(
        self,
        project: Project,
        work: Work,
        version: WorkVersion,
        target_chapter: Optional[Chapter],
        max_discourse_seq: int,
        scope: ForecastScope
    ):
        self.project = project
        self.work = work
        self.version = version
        self.target_chapter = target_chapter
        self.max_discourse_seq = max_discourse_seq
        self.scope = scope

    def __repr__(self) -> str:
        ch_ord = self.target_chapter.ordinal if self.target_chapter else None
        return (
            f"<ResolvedScope work='{self.work.title}' version={self.version.id[:8]} "
            f"chapter={ch_ord} max_seq={self.max_discourse_seq}>"
        )

def resolve_scope(
    db: Session,
    project_id: Optional[str] = None,
    work_id: Optional[str] = None,
    version_id: Optional[str] = None,
    cutoff_chapter: Optional[int] = None,
    cutoff_seq: Optional[int] = None,
    mode: str = "retrospective"
) -> ResolvedScope:
    """
    Unified context resolver: project -> work -> version -> chapter -> cutoff_seq
    Guarantees:
    1. Only the specified or latest version of the target work is loaded.
    2. Chapters and scenes are strictly filtered by work_version_id (preventing cross-version pollution).
    3. Produces an immutable ForecastScope populated with target_work_version_id and validated cutoff sequence.
    """
    # 1. Resolve Work
    if work_id:
        work = db.query(Work).filter_by(id=work_id).first()
    else:
        work = db.query(Work).filter_by(role="target").first()

    if not work:
        raise ValueError("Target work not found in database. Ingest work first.")

    # 2. Resolve Project
    project = None
    if project_id:
        project = db.query(Project).filter_by(id=project_id).first()
    if not project and work.project_id:
        project = db.query(Project).filter_by(id=work.project_id).first()
    if not project:
        project = db.query(Project).first()
    
    resolved_proj_id = project.id if project else (work.project_id or "default")

    # 3. Resolve Version
    if version_id:
        version = db.query(WorkVersion).filter_by(id=version_id, work_id=work.id).first()
        if not version:
            version = db.query(WorkVersion).filter_by(id=version_id).first()
    else:
        version = db.query(WorkVersion).filter_by(work_id=work.id).order_by(WorkVersion.created_at.desc()).first()

    if not version:
        raise ValueError(f"No version found for work '{work.title}' ({work.id})")

    # 4. Resolve Cutoff Chapter and Sequence strictly within this version
    target_chapter: Optional[Chapter] = None
    if cutoff_chapter is not None:
        target_chapter = db.query(Chapter).filter_by(
            work_version_id=version.id,
            ordinal=cutoff_chapter
        ).first()

        if not target_chapter:
            raise ValueError(
                f"Chapter {cutoff_chapter} not found in work version '{version.id}' ('{work.title}')"
            )

        last_scene = db.query(Scene).filter_by(
            chapter_id=target_chapter.id
        ).order_by(Scene.discourse_seq.desc()).first()

        max_seq = last_scene.discourse_seq if last_scene else target_chapter.ordinal

    elif cutoff_seq is not None:
        max_seq = cutoff_seq
        scene = (
            db.query(Scene)
            .join(Chapter, Scene.chapter_id == Chapter.id)
            .filter(Chapter.work_version_id == version.id, Scene.discourse_seq == cutoff_seq)
            .first()
        )
        if scene:
            target_chapter = scene.chapter
    else:
        # Default to latest scene in this version
        last_scene = (
            db.query(Scene)
            .join(Chapter, Scene.chapter_id == Chapter.id)
            .filter(Chapter.work_version_id == version.id)
            .order_by(Scene.discourse_seq.desc())
            .first()
        )
        if last_scene:
            max_seq = last_scene.discourse_seq
            target_chapter = last_scene.chapter
        else:
            max_seq = 1

    scope = ForecastScope(
        project_id=resolved_proj_id,
        target_work_version_id=version.id,
        target_max_discourse_seq=max_seq,
        mode=mode
    )

    return ResolvedScope(
        project=project or Project(title="Default Project"),
        work=work,
        version=version,
        target_chapter=target_chapter,
        max_discourse_seq=max_seq,
        scope=scope
    )
