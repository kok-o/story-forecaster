import os
import re
import hashlib
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from story_forecaster.db import SessionLocal
from story_forecaster.db.models import Work, WorkVersion, Chapter, Scene
from story_forecaster.ingestion.normalizer import normalize_text

class IncrementalChapterUpdater:
    """
    Incremental chapter updater for production pipeline:
    - Appends newly published chapters with contiguous discourse_seq integrity.
    - When modifying an existing chapter, creates a new WorkVersion or re-sequences scenes
      so historical discourse_seq ordering is preserved across all chapters.
    - Recomputes normalized_sha256 for the target version.
    """

    def __init__(self, db_session: Optional[Session] = None):
        self._external_session = db_session

    def _get_db(self) -> Session:
        return self._external_session if self._external_session else SessionLocal()

    def _split_into_scenes(self, normalized_text: str) -> list[str]:
        raw_scenes = re.split(r'\n(?:\s*[\*\#\-\_]{3,}\s*)\n', normalized_text)
        if len(raw_scenes) <= 1:
            paragraphs = normalized_text.split("\n\n")
            chunk_size = max(10, len(paragraphs) // 4)
            raw_scenes = [
                "\n\n".join(paragraphs[i:i + chunk_size])
                for i in range(0, len(paragraphs), chunk_size)
                if paragraphs[i:i + chunk_size]
            ]
        return [s.strip() for s in raw_scenes if s.strip()]

    def _resequence_version_scenes(self, db: Session, version_id: str) -> tuple[str, int]:
        chapters = db.query(Chapter).filter_by(work_version_id=version_id).order_by(Chapter.ordinal.asc()).all()
        current_seq = 1
        hasher = hashlib.sha256()
        for ch in chapters:
            hasher.update(ch.title.encode("utf-8"))
            scenes = db.query(Scene).filter_by(chapter_id=ch.id).order_by(Scene.ordinal.asc()).all()
            for sc in scenes:
                sc.discourse_seq = current_seq
                current_seq += 1
                if sc.content:
                    hasher.update(sc.content.encode("utf-8"))
        return hasher.hexdigest(), current_seq - 1

    def update_chapter(
        self,
        raw_text: str,
        title: Optional[str] = None,
        ordinal: Optional[int] = None,
        create_new_version_on_edit: bool = True
    ) -> Dict[str, Any]:
        db = self._get_db()
        should_close = self._external_session is None

        try:
            work = db.query(Work).filter_by(role="target").first()
            if not work:
                raise ValueError("Target work not initialized in database")

            latest_ver = db.query(WorkVersion).filter_by(work_id=work.id).order_by(WorkVersion.created_at.desc()).first()
            if not latest_ver:
                raise ValueError("No active work version found")

            last_ch = db.query(Chapter).filter_by(work_version_id=latest_ver.id).order_by(Chapter.ordinal.desc()).first()
            target_ordinal = ordinal if ordinal is not None else ((last_ch.ordinal + 1) if last_ch else 1)
            target_title = title if title else f"Глава {target_ordinal:02d}."

            normalized_text, text_hash = normalize_text(raw_text)
            scene_texts = self._split_into_scenes(normalized_text)

            existing_ch = db.query(Chapter).filter_by(work_version_id=latest_ver.id, ordinal=target_ordinal).first()
            created_new_version = False

            if existing_ch and create_new_version_on_edit:
                # Modifying an existing chapter: spawn a new WorkVersion to preserve historical immutability
                new_ver = WorkVersion(
                    work_id=work.id,
                    original_sha256=text_hash,
                    normalized_sha256="",
                    source_path=latest_ver.source_path
                )
                db.add(new_ver)
                db.flush()
                target_ver = new_ver
                created_new_version = True

                # Clone all chapters from latest_ver
                old_chapters = db.query(Chapter).filter_by(work_version_id=latest_ver.id).order_by(Chapter.ordinal.asc()).all()
                for old_c in old_chapters:
                    if old_c.ordinal == target_ordinal:
                        # Insert updated chapter
                        ch_to_add = Chapter(
                            work_version_id=target_ver.id,
                            ordinal=target_ordinal,
                            title=target_title,
                            char_count=len(normalized_text),
                            source_file=f"chapter_{target_ordinal:02d}.txt"
                        )
                        db.add(ch_to_add)
                        db.flush()
                        offset = 0
                        for idx, sc_text in enumerate(scene_texts, start=1):
                            sc = Scene(
                                chapter_id=ch_to_add.id,
                                ordinal=idx,
                                discourse_seq=0,  # will be resequenced
                                start_char=offset,
                                end_char=offset + len(sc_text),
                                summary=sc_text[:150].replace("\n", " ") + "...",
                                content=sc_text
                            )
                            offset += len(sc_text) + 2
                            db.add(sc)
                    else:
                        cloned_c = Chapter(
                            work_version_id=target_ver.id,
                            ordinal=old_c.ordinal,
                            title=old_c.title,
                            char_count=old_c.char_count,
                            source_file=old_c.source_file
                        )
                        db.add(cloned_c)
                        db.flush()
                        old_scenes = db.query(Scene).filter_by(chapter_id=old_c.id).order_by(Scene.ordinal.asc()).all()
                        for old_s in old_scenes:
                            cloned_s = Scene(
                                chapter_id=cloned_c.id,
                                ordinal=old_s.ordinal,
                                discourse_seq=0,  # will be resequenced
                                start_char=old_s.start_char,
                                end_char=old_s.end_char,
                                summary=old_s.summary,
                                content=old_s.content
                            )
                            db.add(cloned_s)
            else:
                target_ver = latest_ver
                if existing_ch:
                    existing_ch.title = target_title
                    existing_ch.char_count = len(normalized_text)
                    db.query(Scene).filter_by(chapter_id=existing_ch.id).delete()
                    ch_target = existing_ch
                else:
                    ch_target = Chapter(
                        work_version_id=target_ver.id,
                        ordinal=target_ordinal,
                        title=target_title,
                        char_count=len(normalized_text),
                        source_file=f"chapter_{target_ordinal:02d}.txt"
                    )
                    db.add(ch_target)
                    db.flush()

                offset = 0
                for idx, sc_text in enumerate(scene_texts, start=1):
                    sc = Scene(
                        chapter_id=ch_target.id,
                        ordinal=idx,
                        discourse_seq=0,
                        start_char=offset,
                        end_char=offset + len(sc_text),
                        summary=sc_text[:150].replace("\n", " ") + "...",
                        content=sc_text
                    )
                    offset += len(sc_text) + 2
                    db.add(sc)

            # Resequence all scenes in the target version contiguously by chapter.ordinal, scene.ordinal
            db.flush()
            version_sha256, max_seq = self._resequence_version_scenes(db, target_ver.id)
            target_ver.normalized_sha256 = version_sha256

            # Determine discourse_seq bounds for the updated chapter
            target_ch = db.query(Chapter).filter_by(work_version_id=target_ver.id, ordinal=target_ordinal).first()
            ch_scenes = db.query(Scene).filter_by(chapter_id=target_ch.id).order_by(Scene.discourse_seq.asc()).all()
            start_seq = ch_scenes[0].discourse_seq if ch_scenes else 0
            end_seq = ch_scenes[-1].discourse_seq if ch_scenes else 0

            db.commit()

            return {
                "work_version_id": target_ver.id,
                "created_new_version": created_new_version,
                "chapter_ordinal": target_ordinal,
                "chapter_title": target_title,
                "scenes_count": len(ch_scenes),
                "char_count": len(normalized_text),
                "discourse_seq_start": start_seq,
                "discourse_seq_end": end_seq,
                "version_sha256": version_sha256
            }

        except Exception:
            db.rollback()
            raise
        finally:
            if should_close:
                db.close()

