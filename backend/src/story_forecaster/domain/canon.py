from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

class ReferenceClassification(str, Enum):
    """Classification of cross-fandom and canon references."""
    QUOTE_OR_JOKE = "QUOTE_OR_JOKE"           # Character makes a pop-culture reference/joke; does not alter world physics
    COMPARISON = "COMPARISON"                 # Metaphor/comparison in narration
    BORROWED_MECHANIC = "BORROWED_MECHANIC"   # Isolated power/magic system element borrowed into the story
    CROSSOVER_ENTITY = "CROSSOVER_ENTITY"     # Full character/entity/faction imported from another world
    PRIMARY_CANON = "PRIMARY_CANON"           # Element belonging to the primary setting (e.g. HOTD)
    AMBIGUOUS = "AMBIGUOUS"                   # Needs further context or user classification

class CanonRelation(str, Enum):
    """Relation of a canon element to the fanfic's established events."""
    CONFIRMED = "CONFIRMED"                   # Explicitly observed and preserved in the fanfic
    MODIFIED = "MODIFIED"                     # Explicitly changed or averted by character actions
    PRESUMED_INTACT = "PRESUMED_INTACT"       # Not yet mentioned or affected; presumed following original canon
    DEPENDS_ON_CHANGED_CONDITIONS = "DEPENDS_ON_CHANGED_CONDITIONS" # Preconditions altered; needs causal re-evaluation
    UNKNOWN = "UNKNOWN"                       # Insufficient data to determine status

class FanficModificationType(str, Enum):
    """Origin and epistemic certainty of canon alteration in the fanfic."""
    ORIGINAL_UNTOUCHED = "ORIGINAL_UNTOUCHED" # Intact canonical lore without fanfic alteration
    EXPLICIT_CHANGE = "EXPLICIT_CHANGE"       # In-text explicit deviation caused by SI/protagonist actions
    INFERRED_DIVERGENCE = "INFERRED_DIVERGENCE"# Causal ripple effect from prior changes
    READER_SPECULATION = "READER_SPECULATION" # External hypothesis not yet established in narrative

class EvidenceStatus(str, Enum):
    """Status of evidence supporting a canon relation."""
    EXPLICIT = "EXPLICIT"                     # Direct in-text observation/statement
    INFERRED = "INFERRED"                     # Deduced from logical consequences of actions
    DISPUTED = "DISPUTED"                     # Contradictory evidence exists
    ABSENT = "ABSENT"                         # No evidence found in current prefix

class DependencyStatus(str, Enum):
    """Validity of causal prerequisites for a canon event."""
    VALID = "VALID"                           # All preconditions are intact
    NEEDS_REVIEW = "NEEDS_REVIEW"             # Preconditions changed; requires re-evaluation of likelihood
    UNSUPPORTED = "UNSUPPORTED"               # Key preconditions definitively destroyed
    UNKNOWN = "UNKNOWN"

class OccurrenceStatus(str, Enum):
    """Observation status of a canon event."""
    OBSERVED = "OBSERVED"                     # Has occurred in narrative time
    NOT_OBSERVED = "NOT_OBSERVED"             # Has not yet occurred or was off-screen
    EXPLICITLY_PREVENTED = "EXPLICITLY_PREVENTED" # Completely prevented/rendered impossible
    UNKNOWN = "UNKNOWN"

class CanonOverlay(BaseModel):
    """
    Structured alignment entry for a canon event/entity evaluated on 4 orthogonal axes.
    Separates reader knowledge from protagonist awareness.
    """
    element_id: str = Field(..., description="Unique ID of the canon element")
    canon_universe: str = Field(..., description="Originating universe (e.g., 'Highschool of the Dead')")
    source_canon_ref: Optional[str] = Field(None, description="Original canon chapter/volume source citation")
    description: str = Field(..., description="Canonical description of event or entity")
    canon_relation: CanonRelation = Field(..., description="CONFIRMED | MODIFIED | PRESUMED_INTACT | UNKNOWN")
    fanfic_modification_type: FanficModificationType = Field(FanficModificationType.ORIGINAL_UNTOUCHED)
    is_known_to_protagonist: bool = Field(False, description="True only if the in-story protagonist has observed/deduced this")
    version: str = Field("v1.0", description="Overlay schema revision")
    evidence_status: EvidenceStatus = Field(EvidenceStatus.ABSENT)
    dependency_status: DependencyStatus = Field(DependencyStatus.VALID)
    occurrence_status: OccurrenceStatus = Field(OccurrenceStatus.NOT_OBSERVED)
    supporting_refs: List[str] = Field(default_factory=list, description="Span IDs or Chapter citations supporting this status")
    contradicting_refs: List[str] = Field(default_factory=list, description="Contradicting span IDs")
    source_spans: List[str] = Field(default_factory=list, description="Verifiable fanfic text spans")
    known_from_seq: int = Field(..., description="Discourse sequence index where this status was determined")
    notes: Optional[str] = None
