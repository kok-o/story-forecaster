import glob
import os
import re
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from story_forecaster.ingestion.fb2_parser import parse_fb2_file, FB2Book
from story_forecaster.db.session import SessionLocal
from story_forecaster.db.models import Work, WorkVersion, Chapter, Scene, Artifact, Project

TROPE_PATTERNS = {
    "system_exploitation": re.compile(r"(баг|фича|наебать систему|обойти систему|лазейк|эксплойт|магазин.*систем)", re.IGNORECASE),
    "blackmail_counterattack": re.compile(r"(шантаж|вымогат|угроз.*позор|кабальн.*контракт|переиграть|встречн.*претензи)", re.IGNORECASE),
    "subordinate_utility": re.compile(r"(раб|слуг|контракт.*кров|клятв.*систем|пожизненн.*служб|утилитарн)", re.IGNORECASE),
    "canon_subversion": re.compile(r"(канон.*до свидания|сломать канон|наплевать на канон|не по сюжету)", re.IGNORECASE),
    "craft_and_luck": re.compile(r"(крафт|трансмутац|куб|удач.*крафт|сохранен.*прочност)", re.IGNORECASE)
}

def index_meta_corpus(db: Optional[Session] = None) -> Dict[str, Any]:
    """Scans all FB2 books in workspace, ingests as reference works, and tags precedent excerpts."""
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        project = db.query(Project).first()
        if not project:
            project = Project(name="Default Story Forecaster Project")
            db.add(project)
            db.flush()

        fb2_files = glob.glob("NB*/*.fb2")
        total_books = 0
        total_sections = 0
        total_precedents = 0

        for fb2_path in fb2_files:
            try:
                book = parse_fb2_file(fb2_path)
            except Exception as e:
                print(f"Skipping {fb2_path} due to parse error: {e}")
                continue

            work_key = f"ref_{os.path.splitext(os.path.basename(fb2_path))[0]}"
            work = db.query(Work).filter_by(project_id=project.id, title=book.title, role="reference").first()
            if not work:
                work = Work(
                    project_id=project.id,
                    author_name=book.author,
                    title=book.title,
                    role="reference",
                    fandom_metadata_json={"source_path": fb2_path, "total_chars": book.total_chars}
                )
                db.add(work)
                db.flush()

            total_books += 1

            # Extract trope excerpts across sections
            for sec in book.sections:
                total_sections += 1
                matched_tags = []
                for tag, pattern in TROPE_PATTERNS.items():
                    if pattern.search(sec.text):
                        matched_tags.append(tag)

                if matched_tags:
                    total_precedents += 1
                    # Extract representative snippet
                    first_match = None
                    for tag in matched_tags:
                        m = TROPE_PATTERNS[tag].search(sec.text)
                        if m:
                            start = max(0, m.start() - 100)
                            end = min(len(sec.text), m.end() + 200)
                            first_match = sec.text[start:end].replace("\n", " ").strip()
                            break

                    artifact = Artifact(
                        project_id=project.id,
                        type="trope_precedent",
                        content_json={
                            "book_title": book.title,
                            "section_title": sec.title,
                            "tags": matched_tags,
                            "excerpt": first_match or sec.text[:300],
                            "char_count": sec.char_count
                        }
                    )
                    db.add(artifact)

        db.commit()
        return {
            "total_books_indexed": total_books,
            "total_sections_scanned": total_sections,
            "total_precedents_tagged": total_precedents
        }
    finally:
        if close_db:
            db.close()
