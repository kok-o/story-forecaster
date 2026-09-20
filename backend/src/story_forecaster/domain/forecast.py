from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class NarrativeMode(str, Enum):
    ACTION = "ACTION"                         # High-stakes combat, physical pursuit, immediate crisis
    AFTERMATH = "AFTERMATH"                   # Tending wounds, consolidating loot/power, reflection
    INTERLUDE = "INTERLUDE"                   # Third-party reaction (enemies, authorities, parallel faction)
    POLITICS = "POLITICS"                     # Negotiations, faction conflict, trade bargaining
    SLICE_OF_LIFE = "SLICE_OF_LIFE"           # Comedic relief, domestic banter, training routine

class ChapterTopology(BaseModel):
    """Macro-structure of the predicted chapter before micro-events are determined."""
    pov_character: str = Field(..., description="Character from whose perspective the chapter is narrated")
    narrative_mode: NarrativeMode = Field(..., description="Primary mode of the chapter")
    is_direct_continuation: bool = Field(True, description="True if continues previous scene without time/location jump")
    focal_thread_id: Optional[str] = Field(None, description="Primary plot thread addressed")
    estimated_pacing: str = Field("medium", description="fast, medium, deliberate")

class PlotBeat(BaseModel):
    """A concrete narrative milestone within the chapter."""
    ordinal: int = Field(..., description="Order of the beat (1-indexed)")
    summary: str = Field(..., description="Concise description of the event")
    participants: List[str] = Field(default_factory=list, description="Characters involved")
    conflict_type: Optional[str] = None
    epistemic_change: Optional[str] = Field(None, description="What information or belief changes as a result")
    source_citations: List[str] = Field(default_factory=list, description="IDs of sources cited in this beat (e.g. ['scene_191'])")

class PredictionCandidate(BaseModel):
    """One distinct prospective chapter development trajectory."""
    candidate_id: str = Field(..., description="Unique identifier for the hypothesis (e.g. 'hyp_1')")
    title: str = Field(..., description="Descriptive label for this story path")
    topology: ChapterTopology = Field(..., description="Macro structure and POV")
    key_events: List[PlotBeat] = Field(..., description="Sequential list of 3-6 core beats")
    character_motivations: Dict[str, str] = Field(default_factory=dict, description="Motivations driving key actors")
    potential_twist: Optional[str] = Field(None, description="Possible subversion or cliffhanger")
    confidence_label: str = Field("UNVERIFIED", description="High / Moderate / Low / Experimental")
    rationale: str = Field(..., description="Justification grounded in story context and author habits")
    assumptions: List[str] = Field(default_factory=list, description="Explicit assumptions required for this path")
    source_citations: List[str] = Field(default_factory=list, description="All source IDs cited by this candidate")
    continuity_verified: bool = Field(False, description="Passed hard constraint checker")
    continuity_status: str = Field("not_checked", description="passed / failed / not_checked / citation_violation")
    verification_notes: Optional[str] = Field(None, description="Detailed continuity verification status and notes")

class ForecastResult(BaseModel):
    """Full prediction report containing multiple diverse candidates."""
    target_work: str
    cutoff_chapter: int
    candidates: List[PredictionCandidate] = Field(..., min_length=1, max_length=5)
    author_precedent_citations: List[str] = Field(default_factory=list)
    included_sources: List[Dict[str, Any]] = Field(default_factory=list, description="List of source items included in the prompt with their IDs and metadata")
    context_truncation_info: Dict[str, Any] = Field(default_factory=dict, description="Metadata about context budget, character counts, and truncation")
    raw_usage: Dict[str, Any] = Field(default_factory=dict, description="Token usage and metadata from provider")
    generated_at_utc: str
    scope_manifest_hash: str
    provider: str = Field("demo", description="Provider used for generation (e.g. 'demo', 'gemini-3.8-flash')")
    is_synthetic_demonstration: bool = Field(False, description="True if generated from pre-scripted demonstration templates")
