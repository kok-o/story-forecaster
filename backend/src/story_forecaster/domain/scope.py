from typing import Optional, Literal
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime

class ForecastScope(BaseModel):
    """
    Immutable specification of the access boundaries for a forecast or backtest run.
    Enforces zero-leakage constraints by design.
    """
    model_config = ConfigDict(frozen=True)

    project_id: str = Field(..., description="Unique ID of the project")
    target_work_version_id: str = Field(..., description="Version of the target work being analyzed")
    target_max_discourse_seq: int = Field(..., description="Absolute upper boundary of discourse sequence allowed (strictly exclusive of future)")
    allowed_author_manifest_id: Optional[str] = Field(None, description="Allowed corpus manifest of author's other works")
    allowed_canon_manifest_id: Optional[str] = Field(None, description="Allowed external canon lore manifest")
    reference_time: Optional[datetime] = Field(None, description="Historical cutoff timestamp for historical mode")
    mode: Literal["retrospective", "historical", "prospective"] = Field(
        "retrospective",
        description="retrospective (explicit canon allowed), historical (strictly pre-dating cutoff), prospective (pre-publication run)"
    )
    branch_id: str = Field("main", description="Narrative branch identifier")
    policy_version: str = Field("v1", description="Policy schema version")

    def is_discourse_allowed(self, seq: int) -> bool:
        """Verifies whether a given discourse sequence position is within the allowed boundary."""
        return seq <= self.target_max_discourse_seq

    def validate_coverage(self, source_version_id: str, max_seq_used: int) -> bool:
        """Ensures that artifacts built from the target work do not exceed the cutoff."""
        if source_version_id == self.target_work_version_id:
            return max_seq_used <= self.target_max_discourse_seq
        if self.allowed_author_manifest_id is not None or self.allowed_canon_manifest_id is not None:
            allowed = [m for m in [self.allowed_author_manifest_id, self.allowed_canon_manifest_id] if m]
            return any(source_version_id == m or source_version_id.startswith(m) for m in allowed)
        return True

    def manifest_hash(self) -> str:
        """Computes deterministic SHA-256 fingerprint of the scope boundary configuration."""
        import hashlib
        ref_time_str = self.reference_time.isoformat() if self.reference_time else "none"
        payload = (
            f"{self.project_id}:{self.target_work_version_id}:{self.target_max_discourse_seq}:"
            f"{self.allowed_author_manifest_id or 'none'}:{self.allowed_canon_manifest_id or 'none'}:"
            f"{ref_time_str}:{self.mode}:{self.branch_id}:{self.policy_version}"
        )
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]

