from typing import List, Dict, Tuple, Optional, Any
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from story_forecaster.domain.scope import ForecastScope
from story_forecaster.db.session import SessionLocal
from story_forecaster.db.models import Scene, Chapter, Work
from story_forecaster.retrieval.bm25 import BM25Index, tokenize_for_search
from story_forecaster.config import get_settings

class SearchChunk(BaseModel):
    """Bounded search chunk with exact span coordinates within the scene."""
    chunk_id: str
    scene_id: str
    discourse_seq: int
    chapter_num: int
    chapter_title: str
    scene_ordinal: int
    start_char: int
    end_char: int
    content: str

class SearchResult(BaseModel):
    """Retrieved evidence unit bounded by scope."""
    document_id: str
    channel: str = Field(..., description="'local_scene', 'canon_reference', 'author_precedent'")
    title: str
    content_snippet: str
    score: float
    discourse_seq: Optional[int] = None
    chapter_num: Optional[int] = None
    chapter_ordinal: Optional[int] = None
    snippet: Optional[str] = None
    start_char: Optional[int] = None
    end_char: Optional[int] = None

    def model_post_init(self, __context: Any) -> None:
        if self.chapter_ordinal is None and self.chapter_num is not None:
            self.chapter_ordinal = self.chapter_num
        elif self.chapter_num is None and self.chapter_ordinal is not None:
            self.chapter_num = self.chapter_ordinal

        if self.snippet is None and self.content_snippet is not None:
            self.snippet = self.content_snippet
        elif self.content_snippet is None and self.snippet is not None:
            self.content_snippet = self.snippet

class HybridRetrievalEngine:
    """
    Scope-bounded lexical retrieval engine:
    - Restricts search space strictly to discourse_seq <= scope.target_max_discourse_seq.
    - Divides scenes into bounded search chunks with exact span coordinates.
    - Caches BM25 indexes by (work_version_id, cutoff_seq) so corpus statistics never leak future chapters.
    - Combines BM25 lexical ranking with lexical token overlap via Reciprocal Rank Fusion (RRF).
    """

    # Class-level cache: (work_version_id, cutoff_seq) -> (BM25Index, Dict[str, SearchChunk])
    _cache: Dict[Tuple[str, int], Tuple[BM25Index, Dict[str, SearchChunk]]] = {}

    @classmethod
    def clear_cache(cls, version_id: Optional[str] = None):
        """Invalidates BM25 retrieval cache either entirely or for a specific work version."""
        if version_id is None:
            cls._cache.clear()
        else:
            keys_to_del = [k for k in cls._cache if k[0] == version_id]
            for k in keys_to_del:
                cls._cache.pop(k, None)

    def __init__(self, db_session: Optional[Session] = None, chunk_size: int = 1500, chunk_overlap: int = 200):
        self._external_session = db_session
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        cfg = get_settings().get("retrieval", {})
        self.k1 = cfg.get("bm25_k1", 1.2)
        self.b = cfg.get("bm25_b", 0.75)
        self.rrf_k = cfg.get("rrf_k", 60)
        self.lexical_top_k = cfg.get("lexical_top_k", 50)

    def _get_db(self) -> Session:
        return self._external_session if self._external_session else SessionLocal()


    def _chunk_scene(self, sc: Scene, ch: Chapter) -> List[SearchChunk]:
        """Partitions a scene into search chunks with precise coordinates."""
        full_text = sc.content if (hasattr(sc, "content") and sc.content) else (sc.summary or "")
        text_len = len(full_text)

        if text_len <= self.chunk_size:
            return [
                SearchChunk(
                    chunk_id=f"scene_{sc.id}",
                    scene_id=str(sc.id),
                    discourse_seq=sc.discourse_seq,
                    chapter_num=ch.ordinal,
                    chapter_title=ch.title,
                    scene_ordinal=sc.ordinal,
                    start_char=0,
                    end_char=text_len,
                    content=full_text
                )
            ]

        chunks = []
        step = self.chunk_size - self.chunk_overlap
        idx = 0
        chunk_num = 1
        while idx < text_len:
            end_idx = min(idx + self.chunk_size, text_len)
            sub_text = full_text[idx:end_idx]
            chunks.append(
                SearchChunk(
                    chunk_id=f"scene_{sc.id}_chunk_{chunk_num}",
                    scene_id=str(sc.id),
                    discourse_seq=sc.discourse_seq,
                    chapter_num=ch.ordinal,
                    chapter_title=ch.title,
                    scene_ordinal=sc.ordinal,
                    start_char=idx,
                    end_char=end_idx,
                    content=sub_text
                )
            )
            chunk_num += 1
            if end_idx >= text_len:
                break
            idx += step

        return chunks

    def _get_or_build_index(self, db: Session, ver_id: str, cutoff_seq: int) -> Tuple[BM25Index, Dict[str, SearchChunk]]:
        """
        Retrieves or deterministically builds and caches a BM25Index for (ver_id, cutoff_seq).
        Corpus statistics (total docs, avg doc len, IDF) strictly reflect only scenes up to cutoff_seq.
        """
        cache_key = (ver_id, cutoff_seq)
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Fetch only eligible scenes bounded by scope and version
        eligible_scenes = (
            db.query(Scene, Chapter)
            .join(Chapter, Scene.chapter_id == Chapter.id)
            .filter(Chapter.work_version_id == ver_id)
            .filter(Scene.discourse_seq <= cutoff_seq)
            .order_by(Scene.discourse_seq.asc())
            .all()
        )

        bm25 = BM25Index(k1=self.k1, b=self.b)
        chunk_lookup: Dict[str, SearchChunk] = {}

        for sc, ch in eligible_scenes:
            scene_chunks = self._chunk_scene(sc, ch)
            for chunk in scene_chunks:
                chunk_lookup[chunk.chunk_id] = chunk
                bm25.add_document(chunk.chunk_id, chunk.content)

        bm25.build()
        self._cache[cache_key] = (bm25, chunk_lookup)
        return bm25, chunk_lookup

    def search(
        self,
        query: str,
        scope: ForecastScope,
        top_k: int = 15
    ) -> List[SearchResult]:
        """
        Executes leak-free hybrid search:
        1. Resolve target work version ID.
        2. Retrieve or build scope-bounded BM25 index (cached by ver_id + cutoff_seq).
        3. Execute BM25 lexical ranking with Russian stemming.
        4. Execute lexical token overlap ranking.
        5. Combine with Reciprocal Rank Fusion (RRF) and return top_k SearchResults.
        """
        db = self._get_db()
        should_close = self._external_session is None

        try:
            # 1. Resolve work version ID
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

            cutoff_seq = scope.target_max_discourse_seq
            bm25, chunk_lookup = self._get_or_build_index(db, ver_id, cutoff_seq)

            if bm25.total_docs == 0:
                return []

            # 2. BM25 Lexical search (with Russian stemming)
            bm25_matches = bm25.search(query, top_k=self.lexical_top_k)

            # 3. Lexical Token Overlap match (named honestly as lexical token overlap, not dense)
            query_tokens = set(tokenize_for_search(query, stem=True))
            lexical_overlap_scores: List[Tuple[str, int]] = []
            for doc_id in bm25.doc_ids:
                chunk = chunk_lookup[doc_id]
                chunk_tokens = set(tokenize_for_search(chunk.content, stem=True))
                overlap = len(query_tokens.intersection(chunk_tokens))
                if overlap > 0:
                    lexical_overlap_scores.append((doc_id, overlap))

            lexical_overlap_scores.sort(key=lambda x: x[1], reverse=True)

            # 4. Reciprocal Rank Fusion (RRF)
            rrf_k = self.rrf_k
            rrf_scores: Dict[str, float] = {}

            for rank, (doc_id, _) in enumerate(bm25_matches, start=1):
                rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + (1.0 / (rrf_k + rank))

            for rank, (doc_id, _) in enumerate(lexical_overlap_scores[:50], start=1):
                rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + (1.0 / (rrf_k + rank))

            # 5. Sort by RRF score descending
            ranked_doc_ids = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

            # 6. Format results
            results: List[SearchResult] = []
            for doc_id, rrf_score in ranked_doc_ids[:top_k]:
                chunk = chunk_lookup[doc_id]
                snippet = self._make_snippet(chunk.content, query)
                results.append(SearchResult(
                    document_id=doc_id,
                    channel="local_scene",
                    title=f"{chunk.chapter_title} (Сцена #{chunk.scene_ordinal})",
                    content_snippet=snippet,
                    score=round(rrf_score, 4),
                    discourse_seq=chunk.discourse_seq,
                    chapter_num=chunk.chapter_num,
                    chapter_ordinal=chunk.chapter_num,
                    snippet=snippet,
                    start_char=chunk.start_char,
                    end_char=chunk.end_char
                ))

            return results
        finally:
            if should_close:
                db.close()

    def _make_snippet(self, text: str, query: str, max_chars: int = 240) -> str:
        """Extracts a relevant text snippet surrounding query terms."""
        tokens = tokenize_for_search(query, stem=False)
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
