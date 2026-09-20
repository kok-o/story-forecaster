from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class ArcMilestone(BaseModel):
    """Specific narrative phase or plot beat within an overarching arc."""
    milestone_id: str
    title: str
    order: int
    status: str = Field("PENDING", description="'PENDING', 'IN_PROGRESS', 'ACHIEVED', 'ABANDONED'")
    target_chapter_or_scene: Optional[int] = None
    description: str = ""


class ReaderPromise(BaseModel):
    """Explicit narrative hook or expectation established for the reader (Chekhov's Gun)."""
    promise_id: str
    introduced_in_scene_ordinal: int
    promise_text: str
    target_payoff_ordinal: Optional[int] = None
    payoff_status: str = Field("OPEN", description="'OPEN', 'PAID_OFF', 'SUBVERTED', 'BROKEN'")
    associated_thread_id: Optional[str] = None


class ArcPlan(BaseModel):
    """
    Overarching narrative architecture for a multi-chapter storyline.
    Distinguishes future intentions from fulfilled events, enforcing versioned revisions.
    """
    arc_id: str
    title: str
    theme: str
    core_conflict: str
    milestones: List[ArcMilestone] = Field(default_factory=list)
    reader_promises: List[ReaderPromise] = Field(default_factory=list)
    open_mysteries: List[str] = Field(default_factory=list)
    setups_and_payoffs: Dict[str, str] = Field(
        default_factory=dict,
        description="Map of setup description -> expected payoff description"
    )
    revision_num: int = Field(1, ge=1)
    status: str = Field("ACTIVE", description="'ACTIVE', 'COMPLETED', 'ARCHIVED'")


class ChapterPlan(BaseModel):
    """
    Structural plan for an entire chapter, coordinating individual ScenePlans.
    """
    chapter_ordinal: int
    title: str
    chapter_goal: str
    arc_id: Optional[str] = None
    expected_scenes_count: int = Field(3, ge=1, le=10)
    open_commitments: List[str] = Field(
        default_factory=list,
        description="Specific plot threads or promises that must be addressed or advanced"
    )
    risk_factors: List[str] = Field(default_factory=list)
    revision_num: int = Field(1, ge=1)


class EditorialQualityScorecard(BaseModel):
    """Quantitative evaluation across fixed editorial quality rubrics."""
    pacing_score: float = Field(..., ge=0.0, le=1.0, description="1.0 = optimal narrative momentum")
    voice_consistency_score: float = Field(..., ge=0.0, le=1.0, description="1.0 = flawless character fidelity")
    causal_coherence_score: float = Field(..., ge=0.0, le=1.0, description="1.0 = strict cause-and-effect logic")
    repetition_penalty: float = Field(0.0, ge=0.0, le=1.0, description="0.0 = zero annoying repetition")
    overall_quality_score: float = Field(..., ge=0.0, le=1.0)


class EditorialReview(BaseModel):
    """
    Post-chapter or multi-scene editorial audit:
    Evaluates rhythm, repetitive dialogue/tropes, voice drift, and causal coherence.
    """
    chapter_ordinal: int
    scorecard: EditorialQualityScorecard
    pacing_assessment: str
    repetitive_phrases: List[str] = Field(default_factory=list)
    repetitive_tropes: List[str] = Field(default_factory=list)
    voice_anomalies: List[str] = Field(default_factory=list)
    unresolved_commitments_count: int = 0
    recommendations: List[str] = Field(default_factory=list)
