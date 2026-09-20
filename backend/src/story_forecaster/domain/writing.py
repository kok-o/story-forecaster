from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class ScenePlan(BaseModel):
    """
    Detailed blueprint for a fanfic scene before prose generation.
    Enforces goal, POV, participant state, conflict, mandatory beats, and target pacing.
    """
    scene_goal: str = Field(..., description="Primary dramatic objective of the scene")
    pov_character: str = Field(..., description="POV character whose perspective and sensory filter govern narration")
    participants: List[str] = Field(..., description="Characters present and acting in the scene")
    initial_state_summary: str = Field(..., description="Physical and emotional state at scene opening")
    known_information: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Explicit map of what each participant knows going in (Theory of Mind)"
    )
    conflict_kind: str = Field("negotiation", description="'negotiation', 'action', 'crafting', 'blackmail', 'social'")
    mandatory_beats: List[str] = Field(..., description="Key plot events that must occur in sequence")
    permitted_changes: List[str] = Field(default_factory=list, description="Allowed state modifications (items, status)")
    desired_outcome: str = Field(..., description="Ending status of the scene")
    target_pacing: str = Field("medium", description="'slow', 'medium', 'fast', 'frenetic'")
    target_length_chars: int = Field(2500, ge=500, le=10000, description="Target character length")

class CharacterVoiceProfile(BaseModel):
    """
    Stylistic and lexical fingerprint for a character's dialogue and thoughts.
    """
    character_id: str
    vocabulary_tone: str = Field(..., description="Vocabulary style (e.g. 'cynical-pragmatic', 'refined-polite')")
    typical_sentence_length: str = Field("medium", description="'short', 'medium', 'compound', 'fragmented'")
    dialogue_mannerisms: List[str] = Field(default_factory=list, description="Characteristic turns of phrase or rhetorical habits")
    interpersonal_nuance: Dict[str, str] = Field(
        default_factory=dict,
        description="Manner shifts depending on interlocutor (e.g. deferential to Boss, arrogant to peers)"
    )
    author_tuning_rationale: str = Field("Based on author N.B.'s canon characterisation", description="Rationale for voice settings")

class ProposedStateDelta(BaseModel):
    """
    Proposed delta extracted from a generated scene draft.
    Does NOT mutate canon or branch state until validated and accepted.
    """
    delta_id: str
    branch_id: str
    scene_ordinal: int
    introduced_characters: List[str] = Field(default_factory=list)
    inventory_changes: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of dicts: {'character': str, 'item': str, 'action': 'acquired'|'lost'|'equipped', 'span_quote': str}"
    )
    injuries_or_statuses: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of dicts: {'character': str, 'status': str, 'action': 'applied'|'healed'|'canceled', 'span_quote': str}"
    )
    epistemic_updates: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of dicts: {'character': str, 'fact_key': str, 'attitude': str, 'span_quote': str}"
    )
    dialogue_claims: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of dicts: {'speaker': str, 'statement': str, 'is_world_fact': False, 'span_quote': str}"
    )
    validation_status: str = Field("PENDING", description="'PENDING', 'VALIDATED', 'REJECTED'")
    validation_notes: Optional[str] = None
    provider_name: Optional[str] = None
    is_synthetic_demonstration: bool = False

class SceneValidationResult(BaseModel):
    """
    Fact-checking and constraint verification report for a generated scene.
    Separates factual consistency from aesthetic editing.
    """
    passed: bool
    plan_compliance_score: float = Field(..., ge=0.0, le=1.0, description="Degree to which mandatory beats were executed")
    pov_violations: List[str] = Field(default_factory=list, description="Narrative omniscience leaks violating the chosen POV")
    epistemic_violations: List[str] = Field(default_factory=list, description="Characters acting on knowledge they cannot possess")
    timeline_violations: List[str] = Field(default_factory=list, description="Inconsistencies with preceding sequence")
    factual_errors: List[str] = Field(default_factory=list, description="Factual contradictions with established branch state")
    notes: str = ""

class SceneSynthesisOutput(BaseModel):
    """
    Structured response schema for LLM scene synthesis:
    Returns both literary narrative prose and extracted state deltas with verbatim quotes.
    """
    prose: str = Field(..., description="Full Russian literary narrative scene prose fulfilling plan beats and adhering to character voices")
    inventory_changes: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of dicts: {'character': str, 'item': str, 'action': 'acquired'|'lost'|'equipped', 'span_quote': str}"
    )
    injuries_or_statuses: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of dicts: {'character': str, 'status': str, 'action': 'applied'|'healed'|'canceled', 'span_quote': str}"
    )
    epistemic_updates: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of dicts: {'character': str, 'fact_key': str, 'attitude': str, 'span_quote': str}"
    )
    dialogue_claims: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of dicts: {'speaker': str, 'statement': str, 'is_world_fact': False, 'span_quote': str}"
    )
    introduced_characters: List[str] = Field(
        default_factory=list,
        description="Characters introduced for the first time in this scene"
    )
