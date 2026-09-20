from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from story_forecaster.domain.scope import ForecastScope
from story_forecaster.db.session import SessionLocal
from story_forecaster.db.models import Scene, Chapter, Work
from story_forecaster.retrieval.bm25 import BM25Index, tokenize_for_search
from story_forecaster.config import get_settings

class SearchResult(BaseModel):
    """Retrieved evidence unit bounded by scope."""
    document_id: str
    channel: str = Field(..., description="'local_scene', 'canon_reference', 'author_precedent'")
    title: str
    content_snippet: str
    score: float
    discourse_seq: Optional[int] = None
    chapter_num: Optional[int] = None

class HybridRetrievalEngine:
    """
    Scope-bounded hybrid retrieval engine:
    - Restricts search space strictly to discourse_seq <= scope.target_max_discourse_seq.
    - Executes BM25 lexical ranking configured via settings.yaml.
    - Applies Reciprocal Rank Fusion (RRF).
    """

    def __init__(self, db_session: Optional[Session] = None):
        self._external_session = db_session
        cfg = get_settings().get("retrieval", {})
        self.k1 = cfg.get("bm25_k1", 1.2)
        self.b = cfg.get("bm25_b", 0.75)
        self.rrf_k = cfg.get("rrf_k", 60)
        self.lexical_top_k = cfg.get("lexical_top_k", 50)

    def _get_db(self) -> Session:
        return self._external_session if self._external_session else SessionLocal()

    def search(
        self,
        query: str,
        scope: ForecastScope,
        top_k: int = 15
    ) -> List[SearchResult]:
        """
        Executes leak-free hybrid search:
        1. Query DB for scenes where discourse_seq <= scope.target_max_discourse_seq.
        2. Filter only to the specified work version.
        3. Index eligible scenes with BM25.
        4. Execute lexical search + keyword overlap.
        5. Combine with RRF and return top_k SearchResults.
        """
        db = self._get_db()
        should_close = self._external_session is None

        try:
            # 1. Scope Boundary Enforcement: identify target version ID
            from story_forecaster.db.models import WorkVersion
            ver_id = scope.target_work_version_id
            is_version = db.query(WorkVersion).filter_by(id=ver_id).first()
            if not is_version:
                latest_v = db.query(WorkVersion).filter_by(work_id=ver_id).order_by(WorkVersion.created_at.desc()).first()
                if latest_v:
                    ver_id = latest_v.id
                else:
                    target_work = db.query(Work).filter_by(role="target").first()
                    if target_work:
                        target_v = db.query(WorkVersion).filter_by(work_id=target_work.id).order_by(WorkVersion.created_at.desc()).first()
                        if target_v:
                            ver_id = target_v.id

            # Fetch only eligible scenes bounded by scope and version
            db_query = (
                db.query(Scene, Chapter)
                .join(Chapter, Scene.chapter_id == Chapter.id)
                .filter(Chapter.work_version_id == ver_id)
                .filter(Scene.discourse_seq <= scope.target_max_discourse_seq)
                .order_by(Scene.discourse_seq.asc())
            )
            eligible_scenes = db_query.all()

            if not eligible_scenes:
                return []

            # 2. Build BM25 index over eligible scenes
            bm25 = BM25Index(k1=self.k1, b=self.b)
            scene_lookup: Dict[str, Any] = {}

            for sc, ch in eligible_scenes:
                doc_id = f"scene_{sc.id}"
                doc_text = sc.content if (hasattr(sc, "content") and sc.content) else (sc.summary or "")
                scene_lookup[doc_id] = (sc, ch, doc_text)
                bm25.add_document(doc_id, doc_text)

            bm25.build()

            # 3. Lexical search
            bm25_matches = bm25.search(query, top_k=self.lexical_top_k)

            # 4. Dense / Semantic Keyword match (keyword overlap score)
            query_tokens = set(tokenize_for_search(query))
            dense_scores: List[tuple] = []
            for doc_id in bm25.doc_ids:
                sc, ch, doc_text = scene_lookup[doc_id]
                sc_tokens = set(tokenize_for_search(doc_text))
                overlap = len(query_tokens.intersection(sc_tokens))
                if overlap > 0:
                    dense_scores.append((doc_id, overlap))

            dense_scores.sort(key=lambda x: x[1], reverse=True)

            # 5. Reciprocal Rank Fusion (RRF)
            rrf_k = self.rrf_k
            rrf_scores: Dict[str, float] = {}

            for rank, (doc_id, _) in enumerate(bm25_matches, start=1):
                rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + (1.0 / (rrf_k + rank))

            for rank, (doc_id, _) in enumerate(dense_scores[:50], start=1):
                rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + (1.0 / (rrf_k + rank))

            # 6. Sort by RRF score descending
            ranked_doc_ids = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

            # 7. Format results
            results: List[SearchResult] = []
            for doc_id, rrf_score in ranked_doc_ids[:top_k]:
                sc, ch, doc_text = scene_lookup[doc_id]
                snippet = self._make_snippet(doc_text, query)
                results.append(SearchResult(
                    document_id=doc_id,
                    channel="local_scene",
                    title=f"{ch.title} (Сцена #{sc.ordinal})",
                    content_snippet=snippet,
                    score=round(rrf_score, 4),
                    discourse_seq=sc.discourse_seq,
                    chapter_num=ch.ordinal
                ))

            return results
        finally:
            if should_close:
                db.close()

    def _make_snippet(self, text: str, query: str, max_chars: int = 240) -> str:
        """Extracts a relevant text snippet surrounding query terms."""
        tokens = tokenize_for_search(query)
        pos = -1
        for t in tokens:
            p = text.lower().find(t)
            if p != -1:
                pos = p
                break

        if pos == -1:
            snippet = text[:max_chars].strip()
            return snippet + "..." if len(text) > max_chars else snippet

        start = max(0, pos - 60)
        end = min(len(text), pos + max_chars - 60)
        snippet = text[start:end].replace("\n", " ").strip()
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(text) else ""
        return f"{prefix}{snippet}{suffix}"
