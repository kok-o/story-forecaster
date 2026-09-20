from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class EpistemicKind(str, Enum):
    GROUND_TRUTH = "GROUND_TRUTH"             # Actual established state in the story
    CHARACTER_BELIEF = "CHARACTER_BELIEF"     # What a specific native character knows/believes
    TRANSMIGRATOR_RECOLLECTION = "TRANSMIGRATOR_RECOLLECTION" # What the SI/transmigrator recalls from canon
    FALSE_RUMOR = "FALSE_RUMOR"               # Misinformation active in the world

class EpistemicAttitude(str, Enum):
    KNOWN = "KNOWN"                           # Confirmed known by subject
    SUSPECTED = "SUSPECTED"                   # Hypothesized or suspected
    FALSE_BELIEF = "FALSE_BELIEF"             # Believed to be true, but actually false
    IGNORANT = "IGNORANT"                     # Unaware

class CharacterEpistemicState(BaseModel):
    """Subjective knowledge matrix entry for a character."""
    character_id: str
    fact_key: str
    attitude: EpistemicAttitude
    known_from_discourse_seq: int
    source_evidence_ref: Optional[str] = None

class PlotThreadKind(str, Enum):
    MYSTERY = "MYSTERY"                       # Unanswered question (origin, hidden threat)
    PROMISE_OR_DEBT = "PROMISE_OR_DEBT"       # Oath, contract, debt, favour owed
    TICKING_CLOCK = "TICKING_CLOCK"           # Imminent deadline (e.g. apocalypse start, tournament, arrival)
    RIVALRY_OR_VENDETTA = "RIVALRY_OR_VENDETTA"# Personal animosity or target
    ACQUISITION_GOAL = "ACQUISITION_GOAL"     # Item, skill, or resource sought (e.g. fairy dust!)

class PlotThreadStatus(str, Enum):
    OPEN = "OPEN"
    SUSPENDED = "SUSPENDED"
    RESOLVED = "RESOLVED"
    ABANDONED = "ABANDONED"

class PlotThread(BaseModel):
    """Narrative hook or 'Chekhov's Gun' requiring resolution."""
    thread_id: str
    title: str
    kind: PlotThreadKind
    status: PlotThreadStatus = PlotThreadStatus.OPEN
    introduced_chapter: int
    introduced_seq: int
    last_active_chapter: int
    urgency: int = Field(1, ge=1, le=5, description="Urgency/salience 1-5")
    key_actors: List[str] = Field(default_factory=list)
    description: str

class NarrativeSnapshot(BaseModel):
    """Point-in-time state ledger on a specific discourse boundary."""
    chapter_num: int
    through_discourse_seq: int
    active_threads: List[PlotThread]
    epistemic_states: List[CharacterEpistemicState]
    active_characters: Dict[str, Dict[str, Any]]
    world_conditions: Dict[str, Any]
    snapshot_hash: str
