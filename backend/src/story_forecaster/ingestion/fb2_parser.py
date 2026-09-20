import re
import os
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field

class FB2Section(BaseModel):
    ordinal: int
    title: str
    text: str
    char_count: int

class FB2Book(BaseModel):
    filepath: str
    title: str
    author: str
    annotation: Optional[str] = None
    sections: List[FB2Section]
    total_chars: int

def parse_fb2_file(filepath: str) -> FB2Book:
    """Parses an FB2 XML file and returns structured book and section representations."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"FB2 file not found: {filepath}")

    tree = ET.parse(filepath)
    root = tree.getroot()

    # Detect namespace
    ns_uri = root.tag.split("}")[0].strip("{") if "}" in root.tag else "http://www.gribuser.ru/xml/fictionbook/2.0"
    ns = {"fb": ns_uri}

    # Title info
    title_info = root.find(".//fb:description/fb:title-info", ns)
    title = "Без названия"
    author = "N.B."
    annotation = ""

    if title_info is not None:
        bt_el = title_info.find("fb:book-title", ns)
        if bt_el is not None and bt_el.text:
            title = bt_el.text.strip()

        author_el = title_info.find("fb:author", ns)
        if author_el is not None:
            fn = author_el.find("fb:first-name", ns)
            ln = author_el.find("fb:last-name", ns)
            fn_t = fn.text.strip() if fn is not None and fn.text else ""
            ln_t = ln.text.strip() if ln is not None and ln.text else ""
            author = f"{fn_t} {ln_t}".strip() or author

        ann_el = title_info.find("fb:annotation", ns)
        if ann_el is not None:
            annotation = "".join(ann_el.itertext()).strip()

    # Fallback to filename if title is generic
    if not title or title == "Без названия":
        title = os.path.splitext(os.path.basename(filepath))[0]

    # Extract body sections
    body = root.find("fb:body", ns)
    sections: List[FB2Section] = []

    if body is not None:
        raw_sections = body.findall("fb:section", ns)
        if not raw_sections:
            # Whole body is one section
            full_text = "".join(body.itertext()).strip()
            sections.append(FB2Section(
                ordinal=1,
                title=title,
                text=full_text,
                char_count=len(full_text)
            ))
        else:
            for idx, sec in enumerate(raw_sections, start=1):
                sec_title = f"Часть {idx}"
                t_el = sec.find("fb:title", ns)
                if t_el is not None:
                    sec_title = "".join(t_el.itertext()).strip() or sec_title

                p_texts = []
                for p in sec.findall(".//fb:p", ns):
                    p_str = "".join(p.itertext()).strip()
                    if p_str:
                        p_texts.append(p_str)

                sec_full_text = "\n\n".join(p_texts)
                sections.append(FB2Section(
                    ordinal=idx,
                    title=sec_title,
                    text=sec_full_text,
                    char_count=len(sec_full_text)
                ))

    total_chars = sum(s.char_count for s in sections)
    return FB2Book(
        filepath=filepath,
        title=title,
        author=author,
        annotation=annotation,
        sections=sections,
        total_chars=total_chars
    )
