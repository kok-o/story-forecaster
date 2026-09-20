import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, DateTime, Text, ForeignKey, JSON, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from .session import Base

def gen_uuid() -> str:
    return str(uuid.uuid4())

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class Project(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    title = Column(String(255), nullable=False)
    target_work_id = Column(String(36), nullable=True)
    settings_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=utc_now)

    works = relationship("Work", back_populates="project")

class Work(Base):
    __tablename__ = "works"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    author_name = Column(String(255), nullable=False)
    title = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False)  # 'target' or 'reference_author'
    fandom_metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=utc_now)

    project = relationship("Project", back_populates="works")
    versions = relationship("WorkVersion", back_populates="work")

class WorkVersion(Base):
    __tablename__ = "work_versions"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    work_id = Column(String(36), ForeignKey("works.id"), nullable=False)
    original_sha256 = Column(String(64), nullable=False)
    normalized_sha256 = Column(String(64), nullable=False)
    source_path = Column(String(512), nullable=True)
    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    work = relationship("Work", back_populates="versions")
    chapters = relationship("Chapter", back_populates="version", order_by="Chapter.ordinal")

class Chapter(Base):
    __tablename__ = "chapters"
    __table_args__ = (
        UniqueConstraint("work_version_id", "ordinal", name="uq_chapter_version_ordinal"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    work_version_id = Column(String(36), ForeignKey("work_versions.id"), nullable=False)
    ordinal = Column(Integer, nullable=False)
    title = Column(String(255), nullable=False)
    char_count = Column(Integer, nullable=False)
    source_file = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=utc_now)

    version = relationship("WorkVersion", back_populates="chapters")
    scenes = relationship("Scene", back_populates="chapter", order_by="Scene.ordinal")

class Scene(Base):
    __tablename__ = "scenes"
    __table_args__ = (
        UniqueConstraint("chapter_id", "ordinal", name="uq_scene_chapter_ordinal"),
        Index("ix_scenes_chapter_ordinal", "chapter_id", "ordinal"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    chapter_id = Column(String(36), ForeignKey("chapters.id"), nullable=False)
    ordinal = Column(Integer, nullable=False)
    discourse_seq = Column(Integer, nullable=False, index=True)
    start_char = Column(Integer, nullable=False)
    end_char = Column(Integer, nullable=False)
    content = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    chapter = relationship("Chapter", back_populates="scenes")

class Artifact(Base):
    __tablename__ = "artifacts"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    type = Column(String(100), nullable=False)  # summary, claim, snapshot, trope
    content_json = Column(JSON, nullable=False)
    input_hash = Column(String(64), nullable=True)
    prompt_version = Column(String(50), nullable=True)
    model_revision = Column(String(100), nullable=True)
    status = Column(String(50), default="VALID")  # VALID, STALE, QUARANTINED
    created_at = Column(DateTime, default=utc_now)

class Run(Base):
    __tablename__ = "runs"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    run_type = Column(String(50), nullable=False)  # forecast, backtest, demo
    config_json = Column(JSON, default=dict)
    status = Column(String(50), default="COMPLETED")  # QUEUED, RUNNING, COMPLETED, FAILED
    model_name = Column(String(100), nullable=True)
    prompt_version = Column(String(50), nullable=True, default="v2.0")
    request_payload_json = Column(JSON, default=dict)
    response_raw_text = Column(Text, nullable=True)
    usage_json = Column(JSON, default=dict)
    error_message = Column(Text, nullable=True)
    context_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=utc_now)

    candidates = relationship("Candidate", back_populates="run")

class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    run_id = Column(String(36), ForeignKey("runs.id"), nullable=False)
    topology_json = Column(JSON, nullable=False)
    events_json = Column(JSON, nullable=False)
    scores_json = Column(JSON, default=dict)
    citations_json = Column(JSON, default=list)
    raw_candidate_json = Column(JSON, default=dict)
    status = Column(String(50), default="ACTIVE")
    created_at = Column(DateTime, default=utc_now)

    run = relationship("Run", back_populates="candidates")

class Branch(Base):
    """
    Isolated fanfic divergence branch branching off from an exact version and discourse sequence cutoff.
    Guarantees the original book is never modified.
    """
    __tablename__ = "branches"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    parent_work_version_id = Column(String(36), ForeignKey("work_versions.id"), nullable=False)
    cutoff_discourse_seq = Column(Integer, nullable=False)
    branch_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(50), default="ACTIVE")  # ACTIVE, ARCHIVED, MERGED
    created_at = Column(DateTime, default=utc_now)

    scenes = relationship("BranchScene", back_populates="branch", order_by="BranchScene.scene_ordinal")

class BranchScene(Base):
    """
    Individual scene within a fanfic branch.
    Stores ScenePlan, generated prose, status (DRAFT, ACCEPTED, REJECTED, SUPERSEDED), and state delta.
    """
    __tablename__ = "branch_scenes"
    __table_args__ = (
        UniqueConstraint("branch_id", "scene_ordinal", "revision_num", name="uq_branch_scene_revision"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    branch_id = Column(String(36), ForeignKey("branches.id"), nullable=False)
    scene_ordinal = Column(Integer, nullable=False)
    revision_num = Column(Integer, default=1, nullable=False)
    title = Column(String(255), nullable=False)
    scene_plan_json = Column(JSON, nullable=False)
    content = Column(Text, nullable=False)
    status = Column(String(50), default="ACCEPTED")  # DRAFT, ACCEPTED, REJECTED, SUPERSEDED
    state_delta_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=utc_now)

    branch = relationship("Branch", back_populates="scenes")

