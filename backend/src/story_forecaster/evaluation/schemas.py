from typing import List, Optional
from pydantic import BaseModel, Field

class EventUnit(BaseModel):
    """Atomic narrative event structured as actor -> action -> target -> outcome with modality/polarity."""
    actor: str = Field(..., description="Active character or faction executing the beat")
    action: str = Field(..., description="Action or verb sequence")
    target: str = Field(..., description="Recipient or object of the action")
    outcome: str = Field(..., description="Result or consequence of the event")
    polarity: bool = Field(True, description="True if event occurred positively; False if negation/destruction")
    modality: str = Field("occurred", description="'occurred', 'hypothesized', 'prevented', 'canceled'")
    causal_links: List[str] = Field(default_factory=list, description="Causal prerequisites or follow-ups")
    negative_examples: List[str] = Field(default_factory=list, description="Antithetical expressions that must receive 0 score")

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
    """Pairwise match between a gold event and a predicted beat honoring strict 1-to-1 constraint."""
    gold_event_idx: int
    candidate_beat_idx: int
    gold_summary: str
    predicted_summary: str
    weight: float = Field(..., description="Match weight: 0.0 (no match / contradiction), 0.5 (partial match), 1.0 (full match)")
    rationale: str

class CandidateMetrics(BaseModel):
    """Evaluation metrics for a single prediction candidate."""
    candidate_id: str
    title: str
    pov_character: str
    narrative_mode: str
    topology_score: Optional[float] = Field(None, description="Score if topology was evaluated, None if not_checked")
    topology_status: str = Field("checked", description="'checked' or 'not_checked'")
    event_precision: float
    event_recall: float
    event_f1: float
    character_consistency: Optional[float] = Field(None, description="None unless explicitly validated by continuity checker")
    character_consistency_status: str = Field("not_checked", description="'passed', 'failed', or 'not_checked'")
    matches: List[MatchRecord] = Field(default_factory=list)
    missed_gold_events: List[int] = Field(default_factory=list, description="Indices of gold events with no prediction match")
    spurious_predicted_beats: List[int] = Field(default_factory=list, description="Indices of predicted beats with no gold match")

class EvaluationReport(BaseModel):
    """Comprehensive backtest evaluation report separating Best@1 and Oracle@K."""
    cutoff_chapter: int
    hidden_chapter: int
    total_candidates: int
    ranking_prior_to_gold: List[str] = Field(default_factory=list, description="Candidate IDs ranked before opening gold")
    best_at_1: CandidateMetrics
    oracle_at_k: CandidateMetrics
    mean_f1: float
    f1_variance: float = 0.0
    f1_std: float = 0.0
    all_candidates: List[CandidateMetrics]
    summary_verdict: str
