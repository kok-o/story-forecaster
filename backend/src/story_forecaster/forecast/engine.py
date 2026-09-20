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
from ..providers.base import BaseLLMProvider
from ..db.session import SessionLocal
from ..db.models import Run, Candidate, Scene, Chapter

logger = logging.getLogger(__name__)

class ForecastEngine:
    """
    Two-stage narrative forecasting engine:
    1. Macro-Topology & POV Selection
    2. Micro-Beat Synthesis constrained by Theory of Mind & Canon divergence
    3. Consistency Evaluation & Ranking
    """

    def __init__(
        self,
        memory_engine: Optional[NarrativeMemoryEngine] = None,
        canon_registry: Optional[CanonDivergenceRegistry] = None,
        author_lib: Optional[AuthorPrecedentLibrary] = None,
        retrieval_engine: Optional[HybridRetrievalEngine] = None,
        provider: Optional[BaseLLMProvider] = None
    ):
        self.memory_engine = memory_engine or NarrativeMemoryEngine()
        self.canon_registry = canon_registry or CanonDivergenceRegistry()
        self.author_lib = author_lib or AuthorPrecedentLibrary()
        self.retrieval_engine = retrieval_engine or HybridRetrievalEngine()
        if provider is None:
            from ..providers import get_provider
            self.provider = get_provider(prefer_gemini=False)
        else:
            self.provider = provider

    def _fetch_recent_scenes(self, scope: ForecastScope, limit: int = 4) -> List[Dict[str, Any]]:
        """Fetches immediate narrative scenes preceding the cutoff sequence."""
        db = SessionLocal()
        try:
            scenes = (
                db.query(Scene, Chapter)
                .join(Chapter, Scene.chapter_id == Chapter.id)
                .filter(Chapter.work_version_id == scope.target_work_version_id)
                .filter(Scene.discourse_seq <= scope.target_max_discourse_seq)
                .order_by(Scene.discourse_seq.desc())
                .limit(limit)
                .all()
            )
            out = []
            for sc, ch in reversed(scenes):
                out.append({
                    "chapter_ordinal": ch.ordinal,
                    "discourse_seq": sc.discourse_seq,
                    "summary": sc.summary or "",
                    "snippet": (sc.content[:300] + "...") if sc.content else ""
                })
            return out
        finally:
            db.close()

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
            char_name = getattr(state, "character", "")
            false_beliefs = getattr(state, "false_beliefs", [])
            for fb in false_beliefs:
                for beat in cand.key_events:
                    if char_name in beat.participants and fb.lower() in beat.summary.lower():
                        violations.append(f"{char_name} acts on unrevealed false belief: '{fb}'")

        if violations:
            cand.continuity_verified = False
            cand.continuity_status = "failed"
            cand.verification_notes = "Continuity violations: " + "; ".join(violations)
        else:
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
        Supports ablation toggles for empirical component evaluation.
        """
        # 1. Reconstruct point-in-time narrative state snapshot
        snapshot = self.memory_engine.get_snapshot(scope)

        # 2. Extract active canon alignments (5-state defeasible model)
        canon_overlays = [] if disable_canon else self.canon_registry.get_overlays(scope)

        # 3. Retrieve relevant authorial precedents
        if disable_author:
            precedents = []
        else:
            active_tags = ["fairy_blackmail", "trade", "subordinates", "dungeon_surge", "interlude"]
            precedents = self.author_lib.query_precedents(scope, active_tags)

        # 4. Assemble recent scenes and retrieved historical excerpts
        recent_scenes = self._fetch_recent_scenes(scope, limit=4)
        if disable_retrieval:
            retrieved_excerpts = []
        else:
            thread_keywords = " ".join([t.thread_id.replace("_", " ") for t in snapshot.active_threads])
            retrieved_excerpts = self._retrieve_thematic_excerpts(scope, query=thread_keywords or "сюжет", top_k=3)

        target_context = {
            "chapter_num": snapshot.chapter_num,
            "discourse_seq": snapshot.through_discourse_seq,
            "active_threads": [] if disable_memory else [t.model_dump() for t in snapshot.active_threads],
            "epistemic_states": [] if disable_memory else [e.model_dump() for e in snapshot.epistemic_states],
            "characters": snapshot.active_characters,
            "world_conditions": {} if disable_memory else snapshot.world_conditions,
            "recent_scenes": recent_scenes,
            "retrieved_excerpts": retrieved_excerpts
        }

        # 5. Execute Generation via Provider
        result = self.provider.generate_hypotheses(
            scope=scope,
            target_context=target_context,
            author_precedents=[p.model_dump() for p in precedents],
            canon_context=[c.model_dump() for c in canon_overlays],
            num_candidates=num_candidates
        )

        # 6. Consistency Verification & Filter
        for cand in result.candidates:
            if getattr(result, "is_synthetic_demonstration", False) or cand.verification_notes and "Синтетический шаблон" in cand.verification_notes:
                cand.continuity_verified = False
                cand.continuity_status = "not_checked"
            else:
                self._verify_candidate_continuity(
                    cand=cand,
                    scope=scope,
                    active_characters=snapshot.active_characters,
                    epistemic_states=snapshot.epistemic_states
                )

        # 7. Persist to DB if requested
        if persist_run:
            db: Session = SessionLocal()
            try:
                db_run = Run(
                    project_id=scope.project_id,
                    run_type="forecast",
                    config_json={
                        "scope": scope.model_dump(),
                        "provider": getattr(result, "provider", "unknown"),
                        "is_synthetic_demonstration": getattr(result, "is_synthetic_demonstration", False),
                        "num_candidates": num_candidates
                    },
                    status="COMPLETED",
                    context_hash=result.scope_manifest_hash
                )
                db.add(db_run)
                db.flush()

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
                        status="ACTIVE"
                    )
                    db.add(db_cand)

                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to persist forecast run to DB: {e}")
            finally:
                db.close()

        return result
