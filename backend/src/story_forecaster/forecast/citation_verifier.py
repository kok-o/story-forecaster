import re
from typing import Set, List, Dict, Any
from story_forecaster.domain.scope import ForecastScope
from story_forecaster.domain.forecast import PredictionCandidate

class CitationVerificationReport:
    def __init__(self, all_valid: bool, total_citations: int, invalid_citations: List[str]):
        self.all_valid = all_valid
        self.total_citations = total_citations
        self.invalid_citations = invalid_citations

class CitationVerifier:
    """
    Validates that prospective hypotheses reference only genuinely provided,
    permitted source documents within the scope boundary. Rejects hallucinated
    or out-of-scope citation IDs.
    """

    def verify_citations(
        self,
        candidates: List[PredictionCandidate],
        valid_source_ids: Set[str],
        scope: ForecastScope
    ) -> CitationVerificationReport:
        all_valid = True
        total_citations = 0
        all_invalid: List[str] = []

        for cand in candidates:
            cand_citations = set(cand.source_citations or [])
            for beat in cand.key_events:
                cand_citations.update(beat.source_citations or [])

            total_citations += len(cand_citations)
            invalid_for_cand = []

            for cite in cand_citations:
                cite_clean = cite.strip()
                if not cite_clean:
                    continue

                if cite_clean not in valid_source_ids:
                    invalid_for_cand.append(cite_clean)

                # Extra check: parse sequence number if format is scene_<seq>
                seq_match = re.match(r"^scene_(\d+)$", cite_clean)
                if seq_match:
                    seq_num = int(seq_match.group(1))
                    if seq_num > scope.target_max_discourse_seq:
                        invalid_for_cand.append(f"{cite_clean}(FUTURE_LEAKAGE_seq_{seq_num}>{scope.target_max_discourse_seq})")

            if invalid_for_cand:
                all_valid = False
                all_invalid.extend(invalid_for_cand)
                cand.continuity_verified = False
                cand.continuity_status = "citation_violation"
                note = f"Citation violation: Unrecognized or out-of-boundary sources: {', '.join(invalid_for_cand)}"
                cand.verification_notes = f"{cand.verification_notes}; {note}" if cand.verification_notes else note

        return CitationVerificationReport(
            all_valid=all_valid,
            total_citations=total_citations,
            invalid_citations=list(set(all_invalid))
        )
