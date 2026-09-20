import json
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from ..domain.scope import ForecastScope
from ..domain.forecast import ForecastResult, PredictionCandidate
from ..memory.engine import NarrativeMemoryEngine
from ..canon.registry import CanonDivergenceRegistry
from ..author.precedents import AuthorPrecedentLibrary
from ..retrieval.engine import HybridRetrievalEngine
from ..providers.base import BaseLLMProvider, ProviderUnavailableError
from ..db.session import SessionLocal
from ..db.models import Run, Candidate, Scene, Chapter
from .context_builder import NarrativeContextBuilder
from .citation_verifier import CitationVerifier

logger = logging.getLogger(__name__)

class ForecastEngine:
    """
    Narrative forecasting engine for Author N.B.
    M2 Implementation:
    1. Volume-bounded context builder with exact scene sources and truncation metadata.
    2. Citation verifier preventing hallucinated or future-leakage scene citations.
    3. Strict Run lifecycle (RUNNING -> COMPLETED / FAILED) with usage metrics and complete candidate storage.
    4. Explicit error propagation (no silent conversion of missing API to demo).
    """

    def __init__(
        self,
        memory_engine: Optional[NarrativeMemoryEngine] = None,
        canon_registry: Optional[CanonDivergenceRegistry] = None,
        author_lib: Optional[AuthorPrecedentLibrary] = None,
        retrieval_engine: Optional[HybridRetrievalEngine] = None,
        provider: Optional[BaseLLMProvider] = None,
        context_builder: Optional[NarrativeContextBuilder] = None,
        citation_verifier: Optional[CitationVerifier] = None
    ):
        self.memory_engine = memory_engine or NarrativeMemoryEngine()
        self.canon_registry = canon_registry or CanonDivergenceRegistry()
        self.author_lib = author_lib or AuthorPrecedentLibrary()
        self.retrieval_engine = retrieval_engine or HybridRetrievalEngine()
        self.context_builder = context_builder or NarrativeContextBuilder()
        self.citation_verifier = citation_verifier or CitationVerifier()

        if provider is None:
            from ..providers import get_provider
            self.provider = get_provider(prefer_gemini=False)
        else:
            self.provider = provider

    def _retrieve_thematic_excerpts(self, scope: ForecastScope, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Retrieves past scenes relevant to active plot threads within scope boundary."""
        if not self.retrieval_engine:
            return []
        try:
            results = self.retrieval_engine.search(query=query, scope=scope, top_k=top_k)
            return [
                {
                    "chapter_ordinal": r.chapter_ordinal,
                    "discourse_seq": r.discourse_seq,
                    "snippet": r.snippet,
                    "score": round(r.score, 4)
                }
                for r in results
            ]
        except Exception as e:
            logger.warning(f"Retrieval query failed: {e}")
            return []

    def _verify_candidate_continuity(
        self,
        cand: PredictionCandidate,
        scope: ForecastScope,
        active_characters: List[str],
        epistemic_states: List[Any]
    ) -> None:
        """Evaluates narrative hard constraints: unintroduced actors and epistemic violations."""
        allowed_names = set(active_characters)
        generic_tokens = ["страж", "горожан", "торгов", "клиент", "бандит", "толпа", "монстр", "житель", "прохож"]
        violations = []

        for beat in cand.key_events:
            for participant in beat.participants:
                name_clean = participant.strip()
                if not name_clean:
                    continue
                if name_clean not in allowed_names:
                    if not any(token in name_clean.lower() for token in generic_tokens):
                        violations.append(f"Character '{name_clean}' is unintroduced at cutoff seq {scope.target_max_discourse_seq}")

        for state in epistemic_states:
            char_name = getattr(state, "character_id", None) or getattr(state, "character", "")
            fact_key = getattr(state, "fact_key", "")
            attitude = getattr(state, "attitude", None)
            attitude_val = attitude.value if hasattr(attitude, "value") else str(attitude or "")

            if not char_name or not fact_key:
                continue

            fact_lower = fact_key.lower()

            if attitude_val == "IGNORANT":
                for beat in cand.key_events:
                    if char_name in beat.participants and fact_lower in beat.summary.lower():
                        violations.append(f"{char_name} reveals/acts on ignorant fact: '{fact_key}'")

            elif attitude_val == "FALSE_BELIEF":
                for beat in cand.key_events:
                    if char_name in beat.participants and fact_lower in beat.summary.lower():
                        violations.append(f"{char_name} acts on unrevealed false belief: '{fact_key}'")

        if violations:
            cand.continuity_verified = False
            cand.continuity_status = "failed"
            cand.verification_notes = "Continuity violations: " + "; ".join(violations)
        elif cand.continuity_status != "citation_violation":
            cand.continuity_verified = True
            cand.continuity_status = "passed"
            cand.verification_notes = f"Verified: All characters and epistemic states valid at seq <= {scope.target_max_discourse_seq}."

    def run_forecast(
        self,
        scope: ForecastScope,
        num_candidates: int = 3,
        persist_run: bool = True,
        disable_retrieval: bool = False,
        disable_canon: bool = False,
        disable_author: bool = False,
        disable_memory: bool = False
    ) -> ForecastResult:
        """
        Executes a leak-free prospective forecast run constrained by scope.
        Guarantees:
        1. Context is volume-bounded with verifiable source IDs.
        2. Citations from candidates are rigorously validated against provided sources.
        3. Runs are audited in DB with status (RUNNING -> COMPLETED / FAILED).
        4. Complete candidate representations are stored without loss.
        """
        db: Session = SessionLocal()
        db_run = None
        try:
            # 1. Point-in-time narrative state snapshot
            snapshot = self.memory_engine.get_snapshot(scope)

            # 2. Active canon alignments
            canon_overlays = [] if disable_canon else self.canon_registry.get_overlays(scope)

            # 3. Authorial decision precedents
            if disable_author:
                precedents = []
            else:
                active_tags = ["fairy_blackmail", "trade", "subordinates", "dungeon_surge", "interlude"]
                precedents = self.author_lib.query_precedents(scope, active_tags)

            # 4. Assemble volume-bounded narrative context with dynamic thread-based retrieval, canon, and precedents
            context_result = self.context_builder.build_context(
                db=db,
                scope=scope,
                snapshot=snapshot if not disable_memory else None,
                retrieval_engine=self.retrieval_engine if not disable_retrieval else None,
                canon_overlays=canon_overlays,
                author_precedents=precedents
            )


            # 5. Retrieved historical excerpts
            if disable_retrieval:
                retrieved_excerpts = []
            else:
                thread_keywords = " ".join([t.thread_id.replace("_", " ") for t in snapshot.active_threads])
                retrieved_excerpts = self._retrieve_thematic_excerpts(scope, query=thread_keywords or "сюжет", top_k=3)

            # Target context payload with segregated sources and truncation metadata
            target_context = {
                "chapter_num": snapshot.chapter_num,
                "discourse_seq": snapshot.through_discourse_seq,
                "active_threads": [] if disable_memory else [t.model_dump() for t in snapshot.active_threads],
                "epistemic_states": [] if disable_memory else [e.model_dump() for e in snapshot.epistemic_states],
                "characters": snapshot.active_characters,
                "world_conditions": {} if disable_memory else snapshot.world_conditions,
                "recent_scenes": [s.model_dump() for s in context_result.sources],
                "formatted_source_text": context_result.formatted_source_text,
                "included_sources": [s.model_dump() for s in context_result.sources],
                "truncation_info": context_result.truncation_info,
                "retrieved_excerpts": retrieved_excerpts
            }

            # 6. Initialize Run in DB with status RUNNING
            if persist_run:
                db_run = Run(
                    project_id=scope.project_id,
                    run_type="forecast",
                    config_json={
                        "scope": scope.model_dump(),
                        "num_candidates": num_candidates,
                        "truncation_info": context_result.truncation_info
                    },
                    status="RUNNING",
                    model_name=getattr(self.provider, "model_name", getattr(self.provider, "provider_name", "unknown")),
                    prompt_version="v2.0-m2",
                    request_payload_json={
                        "scope_manifest_hash": scope.manifest_hash(),
                        "included_sources_count": len(context_result.sources),
                        "used_chars": context_result.truncation_info.get("used_chars", 0),
                        "num_candidates": num_candidates,
                        "disable_flags": {
                            "retrieval": disable_retrieval,
                            "canon": disable_canon,
                            "author": disable_author,
                            "memory": disable_memory
                        }
                    },
                    context_hash=scope.manifest_hash()
                )
                db.add(db_run)
                db.commit()

            # 7. Execute Generation via Provider
            result = self.provider.generate_hypotheses(
                scope=scope,
                target_context=target_context,
                author_precedents=[p.model_dump() for p in precedents],
                canon_context=[c.model_dump() for c in canon_overlays],
                num_candidates=num_candidates
            )

            if persist_run and db_run:
                result.run_id = db_run.id

            # Attach provenance and truncation info to result
            result.included_sources = [s.model_dump() for s in context_result.sources]
            result.context_truncation_info = context_result.truncation_info

            # 8. Verify Citations against provided source IDs
            valid_source_ids = set(context_result.source_ids)
            self.citation_verifier.verify_citations(
                candidates=result.candidates,
                valid_source_ids=valid_source_ids,
                scope=scope
            )

            # 9. Verify Narrative Continuity
            for cand in result.candidates:
                if getattr(result, "is_synthetic_demonstration", False) or (cand.verification_notes and "Синтетический шаблон" in cand.verification_notes):
                    cand.continuity_verified = False
                    cand.continuity_status = "not_checked"
                else:
                    self._verify_candidate_continuity(
                        cand=cand,
                        scope=scope,
                        active_characters=snapshot.active_characters,
                        epistemic_states=snapshot.epistemic_states
                    )

            # 10. Persist Completed Run and Full Candidate Objects to DB
            if persist_run and db_run:
                db_run.status = "COMPLETED"
                db_run.usage_json = getattr(result, "raw_usage", {})
                db_run.response_raw_text = getattr(result, "raw_response_text", None) or f"Generated {len(result.candidates)} candidates via {getattr(result, 'provider', 'unknown')}"
                db_run.config_json = {
                    **db_run.config_json,
                    "provider": getattr(result, "provider", "unknown"),
                    "is_synthetic_demonstration": getattr(result, "is_synthetic_demonstration", False)
                }

                for c in result.candidates:
                    db_cand = Candidate(
                        run_id=db_run.id,
                        topology_json=c.topology.model_dump(),
                        events_json=[e.model_dump() for e in c.key_events],
                        scores_json={
                            "confidence": c.confidence_label,
                            "rationale": c.rationale,
                            "continuity_status": c.continuity_status,
                            "continuity_verified": c.continuity_verified,
                            "verification_notes": c.verification_notes
                        },
                        citations_json=c.source_citations,
                        raw_candidate_json=c.model_dump(),
                        status="ACTIVE"
                    )
                    db.add(db_cand)

                db.commit()

            return result

        except Exception as e:
            if persist_run and db_run:
                try:
                    db_run.status = "FAILED"
                    db_run.error_message = str(e)
                    db.commit()
                except Exception as db_err:
                    logger.error(f"Failed to record failed Run status: {db_err}")
            raise e
        finally:
            db.close()
