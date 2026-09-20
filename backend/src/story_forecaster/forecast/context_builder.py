import hashlib
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from story_forecaster.domain.scope import ForecastScope
from story_forecaster.db.models import Scene, Chapter

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

class ContextBuildResult(BaseModel):
    """Result of volume-bounded narrative context assembly."""
    sources: List[SourceDocument]
    source_ids: List[str]
    formatted_source_text: str
    truncation_info: Dict[str, Any]

class NarrativeContextBuilder:
    """
    Constructs leak-free, volume-bounded context for the LLM forecast prompt.
    Guarantees:
    1. Sources never exceed scope.target_max_discourse_seq or target_work_version_id.
    2. Sources are tagged with verifiable source_ids for citation verification.
    3. Source texts are strictly segregated from control instructions.
    4. Truncation and source count metadata are tracked explicitly.
    """

    def __init__(self, default_char_budget: int = 32000, default_max_scenes: int = 10):
        self.default_char_budget = default_char_budget
        self.default_max_scenes = default_max_scenes

    def build_context(
        self,
        db: Session,
        scope: ForecastScope,
        char_budget: Optional[int] = None,
        max_scenes: Optional[int] = None
    ) -> ContextBuildResult:
        budget = char_budget if char_budget is not None else self.default_char_budget
        limit_scenes = max_scenes if max_scenes is not None else self.default_max_scenes

        # Query all permitted scenes in descending discourse sequence (working backwards from cutoff)
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

        for sc, ch in all_scenes:
            content = sc.content or ""
            content_len = len(content)
            # Stop if budget would be exceeded and we already have at least 1 scene
            if selected_pairs and (used_chars + content_len > budget or len(selected_pairs) >= limit_scenes):
                break

            selected_pairs.append((sc, ch))
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
                content=content
            )
            sources.append(doc)

            doc_blocks.append(
                f'<source id="{s_id}" chapter="{ch.ordinal}" seq="{sc.discourse_seq}">\n'
                f'<!-- {doc.summary} -->\n'
                f'{content}\n'
                f'</source>'
            )

        formatted_text = "<source_documents>\n" + "\n\n".join(doc_blocks) + "\n</source_documents>"
        source_ids = [s.source_id for s in sources]

        is_truncated = (len(sources) < total_available)
        truncation_info = {
            "is_truncated": is_truncated,
            "budget_chars": budget,
            "used_chars": used_chars,
            "total_available_scenes": total_available,
            "included_scenes_count": len(sources),
            "excluded_scenes_count": total_available - len(sources)
        }

        return ContextBuildResult(
            sources=sources,
            source_ids=source_ids,
            formatted_source_text=formatted_text,
            truncation_info=truncation_info
        )
