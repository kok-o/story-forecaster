import os
import json
import re
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from .normalizer import normalize_text
from ..db import SessionLocal, init_db
from ..db.models import Project, Work, WorkVersion, Chapter, Scene

def import_target_work(
    project_title: str = "Story Forecaster - N.B.",
    manifest_path: str = "data/target/chapters/manifest.json"
) -> Dict[str, Any]:
    """
    Imports the target work into the database with full discourse sequence indexing.
    """
    init_db()
    db: Session = SessionLocal()

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        # 1. Create or get Project
        project = db.query(Project).filter_by(title=project_title).first()
        if not project:
            project = Project(
                title=project_title,
                settings_json={"primary_fandom": "Highschool of the Dead", "author": "N.B."}
            )
            db.add(project)
            db.flush()

        # 2. Create or get Work
        work = db.query(Work).filter_by(project_id=project.id, title=manifest["title"]).first()
        if not work:
            work = Work(
                project_id=project.id,
                author_name=manifest["author"],
                title=manifest["title"],
                role="target",
                fandom_metadata_json={"universe": "Highschool of the Dead", "genre": ["RealRPG", "Fanfiction", "Isekai"]}
            )
            db.add(work)
            db.flush()

        project.target_work_id = work.id

        # 3. Create WorkVersion
        full_text_parts = []
        chapters_dir = os.path.dirname(os.path.abspath(manifest_path))
        
        # Read and compute whole-work hashes
        for ch in manifest["chapters"]:
            ch_file = os.path.join(chapters_dir, ch["file"])
            with open(ch_file, "r", encoding="utf-8") as f:
                full_text_parts.append(f.read())

        full_raw_text = "\n\n".join(full_text_parts)
        norm_full_text, norm_full_sha = normalize_text(full_raw_text)

        version = WorkVersion(
            work_id=work.id,
            original_sha256=norm_full_sha,
            normalized_sha256=norm_full_sha,
            source_path=chapters_dir
        )
        db.add(version)
        db.flush()

        # 4. Import Chapters and Scenes
        global_discourse_seq = 0
        imported_chapters = []

        for ch_meta in manifest["chapters"]:
            ch_file = os.path.join(chapters_dir, ch_meta["file"])
            with open(ch_file, "r", encoding="utf-8") as f:
                ch_raw = f.read()

            norm_text, ch_sha = normalize_text(ch_raw)
            chapter = Chapter(
                work_version_id=version.id,
                ordinal=ch_meta["num"],
                title=ch_meta["title"],
                char_count=len(norm_text),
                source_file=ch_meta["file"]
            )
            db.add(chapter)
            db.flush()

            # Split scenes by explicit dividers (***, ---, *****) or large breaks
            scene_chunks = re.split(r'\n(?:\s*[*—_\-]{3,}\s*)\n', norm_text)
            char_cursor = 0
            for sc_ord, sc_text in enumerate(scene_chunks, start=1):
                global_discourse_seq += 1
                sc_len = len(sc_text)
                scene = Scene(
                    chapter_id=chapter.id,
                    ordinal=sc_ord,
                    discourse_seq=global_discourse_seq,
                    start_char=char_cursor,
                    end_char=char_cursor + sc_len,
                    content=sc_text,
                    summary=f"Сцена {sc_ord} главы {chapter.ordinal} ({len(sc_text)} зн.)"
                )
                db.add(scene)
                char_cursor += sc_len + 5

            imported_chapters.append({
                "ordinal": chapter.ordinal,
                "title": chapter.title,
                "char_count": chapter.char_count,
                "scene_count": len(scene_chunks)
            })

        db.commit()
        return {
            "project_id": project.id,
            "work_id": work.id,
            "version_id": version.id,
            "total_chapters": len(imported_chapters),
            "total_scenes": global_discourse_seq,
            "chapters": imported_chapters
        }
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()
