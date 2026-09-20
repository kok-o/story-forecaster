import hashlib
from typing import Dict, Any, List, Optional, Set
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from story_forecaster.domain.scope import ForecastScope
from story_forecaster.domain.memory import NarrativeSnapshot
from story_forecaster.domain.canon import CanonOverlay
from story_forecaster.author.precedents import AuthorTransition
from story_forecaster.db.models import Scene, Chapter
from story_forecaster.retrieval.engine import HybridRetrievalEngine

class SourceDocument(BaseModel):
    """Metadata and verbatim content of a permitted narrative source."""
    source_id: str = Field(..., description="Unique source identifier (e.g. 'scene_191')")
    chapter_ordinal: int
    scene_ordinal: int
    discourse_seq: int
    char_count: int
    fragment_sha256: str
    summary: str
    content: str
    channel: str = Field("recent_scene", description="'recent_scene' or 'retrieved_evidence'")

class ContextBuildResult(BaseModel):
    """Result of volume-bounded narrative context assembly."""
    sources: List[SourceDocument]
    source_ids: List[str]
    formatted_source_text: str
    truncation_info: Dict[str, Any]
    retrieved_sources: List[SourceDocument] = Field(default_factory=list)

class NarrativeContextBuilder:
    """
    Constructs leak-free, volume-bounded context for the LLM forecast prompt.
    Guarantees:
    1. Sources never exceed scope.target_max_discourse_seq or target_work_version_id.
    2. Sources are tagged with verifiable source_ids for citation verification.
    3. Source texts are strictly segregated from control instructions.
    4. Connects BM25 retrieval dynamically using active unresolved threads rather than static tags.
    5. Includes verified canon alignments and authorial precedents with clear provenance.
    6. Truncation and source count metadata are tracked explicitly.
    """

    def __init__(self, default_char_budget: int = 32000, default_max_scenes: int = 10):
        self.default_char_budget = default_char_budget
        self.default_max_scenes = default_max_scenes

    def build_context(
        self,
        db: Session,
        scope: ForecastScope,
        char_budget: Optional[int] = None,
        max_scenes: Optional[int] = None,
        snapshot: Optional[NarrativeSnapshot] = None,
        retrieval_engine: Optional[HybridRetrievalEngine] = None,
        retrieval_top_k: int = 3,
        retrieval_budget_chars: int = 6000,
        canon_overlays: Optional[List[CanonOverlay]] = None,
        author_precedents: Optional[List[AuthorTransition]] = None
    ) -> ContextBuildResult:
        budget = char_budget if char_budget is not None else self.default_char_budget
        limit_scenes = max_scenes if max_scenes is not None else self.default_max_scenes

        # 1. Query all permitted scenes in descending discourse sequence (sliding window backwards from cutoff)
        query = (
            db.query(Scene, Chapter)
            .join(Chapter, Scene.chapter_id == Chapter.id)
            .filter(Chapter.work_version_id == scope.target_work_version_id)
            .filter(Scene.discourse_seq <= scope.target_max_discourse_seq)
            .order_by(Scene.discourse_seq.desc())
        )

        all_scenes = query.all()
        total_available = len(all_scenes)

        selected_pairs = []
        used_chars = 0
        included_scene_seqs: Set[int] = set()

        for sc, ch in all_scenes:
            if used_chars >= budget or len(selected_pairs) >= limit_scenes:
                break

            content = sc.content or ""
            content_len = len(content)

            if used_chars + content_len > budget:
                remaining = budget - used_chars
                if remaining <= 0:
                    break
                truncated_content = content[:remaining]
                sc_proxy = type("SceneProxy", (), {
                    "id": getattr(sc, "id", f"scene_{sc.discourse_seq}"),
                    "ordinal": sc.ordinal,
                    "discourse_seq": sc.discourse_seq,
                    "summary": getattr(sc, "summary", None),
                    "content": truncated_content
                })()
                selected_pairs.append((sc_proxy, ch))
                included_scene_seqs.add(sc.discourse_seq)
                used_chars += len(truncated_content)
                break

            selected_pairs.append((sc, ch))
            included_scene_seqs.add(sc.discourse_seq)
            used_chars += content_len

            if len(selected_pairs) >= limit_scenes:
                break

        # Re-order chronologically for prompt consumption
        selected_pairs.reverse()

        sources: List[SourceDocument] = []
        doc_blocks = []

        for sc, ch in selected_pairs:
            content = sc.content or ""
            s_id = f"scene_{sc.discourse_seq}"
            sha = hashlib.sha256(content.encode("utf-8")).hexdigest()

            doc = SourceDocument(
                source_id=s_id,
                chapter_ordinal=ch.ordinal,
                scene_ordinal=sc.ordinal,
                discourse_seq=sc.discourse_seq,
                char_count=len(content),
                fragment_sha256=sha,
                summary=sc.summary or f"Глава {ch.ordinal}, Сцена {sc.ordinal}",
                content=content,
                channel="recent_scene"
            )
            sources.append(doc)

            doc_blocks.append(
                f'<source id="{s_id}" chapter="{ch.ordinal}" seq="{sc.discourse_seq}">\n'
                f'<!-- {doc.summary} -->\n'
                f'{content}\n'
                f'</source>'
            )

        # 2. Dynamic Retrieval from Active Unresolved Plot Threads
        retrieved_sources: List[SourceDocument] = []
        retrieved_blocks = []
        retrieved_chars = 0

        if retrieval_engine is not None and snapshot is not None and snapshot.active_threads:
            dynamic_queries = [t.title for t in snapshot.active_threads if t.urgency >= 3]
            if not dynamic_queries:
                dynamic_queries = [t.title for t in snapshot.active_threads]

            seen_retrieved_seqs: Set[int] = set()

            for dyn_query in dynamic_queries:
                if retrieved_chars >= retrieval_budget_chars:
                    break
                try:
                    search_results = retrieval_engine.search(
                        query=dyn_query,
                        scope=scope,
                        top_k=retrieval_top_k
                    )
                    for r in search_results:
                        if r.discourse_seq in included_scene_seqs or r.discourse_seq in seen_retrieved_seqs:
                            continue

                        snip_content = r.content_snippet or r.snippet or ""
                        snip_len = len(snip_content)
                        if retrieved_chars + snip_len > retrieval_budget_chars:
                            continue

                        seen_retrieved_seqs.add(r.discourse_seq)
                        retrieved_chars += snip_len

                        ret_id = f"scene_{r.discourse_seq}"
                        sha = hashlib.sha256(snip_content.encode("utf-8")).hexdigest()

                        ret_doc = SourceDocument(
                            source_id=ret_id,
                            chapter_ordinal=r.chapter_num or 0,
                            scene_ordinal=0,
                            discourse_seq=r.discourse_seq or 0,
                            char_count=snip_len,
                            fragment_sha256=sha,
                            summary=f"Фрагмент по теме: {dyn_query}",
                            content=snip_content,
                            channel="retrieved_evidence"
                        )
                        retrieved_sources.append(ret_doc)
                        sources.append(ret_doc)

                        retrieved_blocks.append(
                            f'<retrieved_source id="{ret_id}" chapter="{r.chapter_num}" seq="{r.discourse_seq}">\n'
                            f'<!-- Запрос: {dyn_query} (score: {r.score}) -->\n'
                            f'{snip_content}\n'
                            f'</retrieved_source>'
                        )
                except Exception:
                    pass

        # 3. Canon Alignments Section
        canon_blocks = []
        if canon_overlays:
            for o in canon_overlays:
                protagonist_note = "Известно герою" if o.is_known_to_protagonist else "Неизвестно герою (внешний канон)"
                canon_blocks.append(
                    f'<canon_element id="{o.element_id}" universe="{o.canon_universe}" relation="{o.canon_relation.value}">\n'
                    f'<!-- {o.description} | {protagonist_note} | Источник: {o.source_canon_ref or "Canon"} -->\n'
                    f'{o.notes or o.description}\n'
                    f'</canon_element>'
                )

        # 4. Author Precedents Section
        precedent_blocks = []
        if author_precedents:
            for p in author_precedents:
                precedent_blocks.append(
                    f'<precedent id="{p.transition_id}" source="{p.source_work}" chapter="{p.source_chapter}">\n'
                    f'<!-- Ситуация: {p.abstract_situation} -->\n'
                    f'<!-- Решение автора: {p.author_resolution} -->\n'
                    f'<!-- Последствие: {p.consequence} -->\n'
                    f'Цитата: «{p.source_text_snippet}»\n'
                    f'</precedent>'
                )

        # Build combined formatted text
        formatted_sections = ["<source_documents>\n" + "\n\n".join(doc_blocks) + "\n</source_documents>"]
        if retrieved_blocks:
            formatted_sections.append(
                "<retrieved_evidence>\n" + "\n\n".join(retrieved_blocks) + "\n</retrieved_evidence>"
            )
        if canon_blocks:
            formatted_sections.append(
                "<canon_alignments>\n" + "\n\n".join(canon_blocks) + "\n</canon_alignments>"
            )
        if precedent_blocks:
            formatted_sections.append(
                "<author_precedents>\n" + "\n\n".join(precedent_blocks) + "\n</author_precedents>"
            )

        formatted_text = "\n\n".join(formatted_sections)
        source_ids = [s.source_id for s in sources]

        is_truncated = (len(selected_pairs) < total_available)
        truncation_info = {
            "is_truncated": is_truncated,
            "budget_chars": budget,
            "used_chars": used_chars,
            "total_available_scenes": total_available,
            "included_scenes_count": len(selected_pairs),
            "excluded_scenes_count": total_available - len(selected_pairs),
            "retrieved_sources_count": len(retrieved_sources),
            "retrieved_chars": retrieved_chars,
            "included_canon_count": len(canon_overlays) if canon_overlays else 0,
            "included_canon_ids": [o.element_id for o in canon_overlays] if canon_overlays else [],
            "included_precedents_count": len(author_precedents) if author_precedents else 0,
            "included_precedent_ids": [p.transition_id for p in author_precedents] if author_precedents else []
        }

        return ContextBuildResult(
            sources=sources,
            source_ids=source_ids,
            formatted_source_text=formatted_text,
            truncation_info=truncation_info,
            retrieved_sources=retrieved_sources
        )
