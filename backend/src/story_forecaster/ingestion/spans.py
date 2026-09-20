import re
import hashlib
from typing import List
from pydantic import BaseModel, Field

DIVIDER_PATTERN = re.compile(r'\n(?:\s*[*—_\-]{3,}\s*)\n')

class SceneSpan(BaseModel):
    """
    Exact character-level evidence coordinate of a narrative scene.
    Guarantees: chapter_text[start_char:end_char] == content.
    """
    ordinal: int = Field(..., description="Scene index within the chapter (1-based)")
    start_char: int = Field(..., ge=0, description="Start character index (inclusive)")
    end_char: int = Field(..., ge=0, description="End character index (exclusive)")
    content: str = Field(..., description="Verbatim textual content of the scene")
    fragment_sha256: str = Field(..., description="SHA-256 fingerprint of the verbatim scene content")

def extract_exact_scene_spans(text: str) -> List[SceneSpan]:
    """
    Parses chapter text into discrete scenes based on markdown/text dividers.
    Preserves exact character offsets without guessing or adding arbitrary padding.
    """
    if not text:
        return []

    spans: List[SceneSpan] = []
    last_pos = 0
    sc_ord = 1

    for match in DIVIDER_PATTERN.finditer(text):
        chunk = text[last_pos:match.start()]
        if chunk.strip():
            frag_hash = hashlib.sha256(chunk.encode('utf-8')).hexdigest()
            spans.append(SceneSpan(
                ordinal=sc_ord,
                start_char=last_pos,
                end_char=match.start(),
                content=chunk,
                fragment_sha256=frag_hash
            ))
            sc_ord += 1
        last_pos = match.end()

    # Trailing scene chunk after divider
    if last_pos > 0 and last_pos < len(text):
        chunk = text[last_pos:]
        if chunk.strip():
            frag_hash = hashlib.sha256(chunk.encode('utf-8')).hexdigest()
            spans.append(SceneSpan(
                ordinal=sc_ord,
                start_char=last_pos,
                end_char=len(text),
                content=chunk,
                fragment_sha256=frag_hash
            ))

    # Fallback if no explicit asterisks or dashes dividers exist
    if not spans:
        paragraphs = text.split("\n\n")
        if len(paragraphs) > 4:
            chunk_size = max(4, len(paragraphs) // 4)
            current_cursor = 0
            for i in range(0, len(paragraphs), chunk_size):
                sub_paras = paragraphs[i:i + chunk_size]
                first_p = sub_paras[0]
                last_p = sub_paras[-1]
                p_start = text.find(first_p, current_cursor)
                if p_start == -1:
                    p_start = current_cursor
                p_end = text.find(last_p, p_start) + len(last_p)
                chunk = text[p_start:p_end]
                frag_hash = hashlib.sha256(chunk.encode('utf-8')).hexdigest()
                spans.append(SceneSpan(
                    ordinal=sc_ord,
                    start_char=p_start,
                    end_char=p_end,
                    content=chunk,
                    fragment_sha256=frag_hash
                ))
                sc_ord += 1
                current_cursor = p_end
        else:
            frag_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
            spans.append(SceneSpan(
                ordinal=1,
                start_char=0,
                end_char=len(text),
                content=text,
                fragment_sha256=frag_hash
            ))

    return spans
