from typing import List, Optional
from pydantic import BaseModel, Field

class EventUnit(BaseModel):
    """Atomic narrative event structured as actor -> action -> target -> outcome."""
    actor: str = Field(..., description="Active character or faction executing the beat")
    action: str = Field(..., description="Action or verb sequence")
    target: str = Field(..., description="Recipient or object of the action")
    outcome: str = Field(..., description="Result or consequence of the event")
    causal_links: List[str] = Field(default_factory=list, description="Causal prerequisites or follow-ups")

class GoldChapterData(BaseModel):
    """Gold standard reference extracted from the held-out/hidden actual chapter."""
    chapter_ordinal: int
    title: str
    pov_character: str
    narrative_mode: str
    key_events: List[EventUnit]
    active_threads: List[str] = Field(default_factory=list)
    cliffhanger: Optional[str] = None

class MatchRecord(BaseModel):
    """Pairwise match between a gold event and a predicted beat honoring 1-to-1 constraint."""
    gold_event_idx: int
    candidate_beat_idx: int
    gold_summary: str
    predicted_summary: str
    weight: float = Field(..., description="Match weight: 0.0 (no match), 0.5 (partial match), 1.0 (full match)")
    rationale: str

class CandidateMetrics(BaseModel):
    """Evaluation metrics for a single prediction candidate."""
    candidate_id: str
    title: str
    pov_character: str
    narrative_mode: str
    topology_score: float = Field(..., description="1.0 if POV and mode match gold, 0.5 if partial, 0.0 if mismatch")
    event_precision: float
    event_recall: float
    event_f1: float
    character_consistency: float = 1.0
    matches: List[MatchRecord] = Field(default_factory=list)

class EvaluationReport(BaseModel):
    """Comprehensive backtest evaluation report separating Best@1 and Oracle@K."""
    cutoff_chapter: int
    hidden_chapter: int
    total_candidates: int
    best_at_1: CandidateMetrics
    oracle_at_k: CandidateMetrics
    mean_f1: float
    all_candidates: List[CandidateMetrics]
    summary_verdict: str
