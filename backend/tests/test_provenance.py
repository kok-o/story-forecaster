import os
import tempfile
import sqlite3
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from story_forecaster.db.models import Base, Project, Work, WorkVersion, Chapter, Scene, Artifact
from story_forecaster.db.backup import backup_sqlite_database
from story_forecaster.ingestion.spans import extract_exact_scene_spans
from story_forecaster.ingestion.importer import import_target_work
from story_forecaster.domain.resolver import resolve_scope

@pytest.fixture
def mem_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_exact_scene_spans_coordinates():
    text = (
        "Первая сцена произведения.\n"
        "Она продолжается здесь.\n\n"
        "***\n\n"
        "Вторая сцена после разделителя.\n"
        "Герой принимает решение.\n\n"
        "---\n\n"
        "Третья сцена в самом конце."
    )
    spans = extract_exact_scene_spans(text)
    assert len(spans) == 3
    for s in spans:
        # Guarantee: exact substring equality
        assert text[s.start_char:s.end_char] == s.content
        assert len(s.fragment_sha256) == 64
    assert spans[0].ordinal == 1
    assert spans[1].ordinal == 2
    assert spans[2].ordinal == 3

def test_exact_scene_spans_fallback_paragraphs():
    text = "Абзац 1.\n\nАбзац 2.\n\nАбзац 3.\n\nАбзац 4.\n\nАбзац 5.\n\nАбзац 6."
    spans = extract_exact_scene_spans(text)
    assert len(spans) > 1
    for s in spans:
        assert text[s.start_char:s.end_char] == s.content

def test_backup_sqlite_database(tmp_path):
    # Create a real sqlite file
    test_db = tmp_path / "test.db"
    conn = sqlite3.connect(str(test_db))
    conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO test (name) VALUES ('story_test')")
    conn.commit()
    conn.close()

    backup_dir = tmp_path / "backups"
    backup_file = backup_sqlite_database(db_path=test_db, backup_dir=backup_dir)

    assert backup_file.exists()
    assert backup_file.stat().st_size > 0

    # Verify backup content
    b_conn = sqlite3.connect(str(backup_file))
    cur = b_conn.cursor()
    cur.execute("SELECT name FROM test WHERE id=1")
    row = cur.fetchone()
    assert row[0] == "story_test"
    b_conn.close()

def test_idempotent_import(mem_db, tmp_path):
    project = Project(title="Test Project")
    mem_db.add(project)
    mem_db.commit()

    # Create dummy chapter files
    ch1 = tmp_path / "ch1.txt"
    ch1.write_text("Текст первой главы.\n\n***\n\nВторая сцена первой главы.", encoding="utf-8")

    manifest = {
        "title": "Тестовая книга",
        "author": "Тестовый автор",
        "chapters": [
            {"ordinal": 1, "title": "Глава 1", "file": "ch1.txt"}
        ]
    }

    manifest_file = tmp_path / "manifest.json"
    import json
    manifest_file.write_text(json.dumps(manifest), encoding="utf-8")

    # First import
    res1 = import_target_work(manifest_path=str(manifest_file), project_title=project.title)
    assert res1["is_idempotent_hit"] is False
    v1_id = res1["version_id"]

    # Check database counts
    from story_forecaster.db.session import SessionLocal
    db = SessionLocal()
    try:
        ver_count = db.query(WorkVersion).filter_by(id=v1_id).count()
        scenes_count = db.query(Scene).join(Chapter).filter(Chapter.work_version_id == v1_id).count()
        assert ver_count == 1
        assert scenes_count == 2
    finally:
        db.close()

    # Second import with identical manifest
    res2 = import_target_work(manifest_path=str(manifest_file), project_title=project.title)
    assert res2["is_idempotent_hit"] is True
    assert res2["version_id"] == v1_id

    # Verify no duplication occurred
    db = SessionLocal()
    try:
        ver_count_after = db.query(WorkVersion).filter_by(id=v1_id).count()
        scenes_count_after = db.query(Scene).join(Chapter).filter(Chapter.work_version_id == v1_id).count()
        assert ver_count_after == 1
        assert scenes_count_after == 2
    finally:
        db.close()

def test_resolve_scope_multi_version(mem_db):
    proj = Project(title="P1")
    work = Work(title="Book", author_name="Author", role="target", project=proj)
    mem_db.add_all([proj, work])
    from datetime import datetime, timezone
    v1 = WorkVersion(work=work, original_sha256="h1", normalized_sha256="h1", created_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
    v2 = WorkVersion(work=work, original_sha256="h2", normalized_sha256="h2", created_at=datetime(2024, 1, 2, tzinfo=timezone.utc))
    mem_db.add_all([v1, v2])
    mem_db.flush()


    c1_v1 = Chapter(work_version_id=v1.id, ordinal=1, title="Ch1 V1", char_count=100)
    c1_v2 = Chapter(work_version_id=v2.id, ordinal=1, title="Ch1 V2", char_count=200)
    c2_v2 = Chapter(work_version_id=v2.id, ordinal=2, title="Ch2 V2", char_count=300)
    mem_db.add_all([c1_v1, c1_v2, c2_v2])
    mem_db.flush()

    sc1 = Scene(chapter_id=c1_v2.id, ordinal=1, discourse_seq=1, start_char=0, end_char=100, content="s1")
    sc2 = Scene(chapter_id=c2_v2.id, ordinal=1, discourse_seq=2, start_char=0, end_char=100, content="s2")
    mem_db.add_all([sc1, sc2])
    mem_db.commit()

    # Resolve latest version (v2) by default
    resolved = resolve_scope(mem_db, work_id=work.id, cutoff_chapter=2)
    assert resolved.version.id == v2.id
    assert resolved.target_chapter.id == c2_v2.id
    assert resolved.max_discourse_seq == 2

    # Resolving v1 requesting chapter 2 must fail because v1 only has chapter 1
    with pytest.raises(ValueError, match="Chapter 2 not found"):
        resolve_scope(mem_db, work_id=work.id, version_id=v1.id, cutoff_chapter=2)

from story_forecaster.author.indexer import index_meta_corpus
from story_forecaster.ingestion.fb2_parser import FB2Book, FB2Section

def test_trope_indexer_deduplication(mem_db, monkeypatch):
    proj = Project(title="P1")
    mem_db.add(proj)
    mem_db.commit()

    mock_book = FB2Book(
        filepath="NB1/book.fb2",
        title="Тестовая книга автора",
        author="N.B.",
        sections=[
            FB2Section(
                ordinal=1,
                title="Секция 1",
                text="Здесь мы видим явный крафт и лазейка в системе для обхода правил.",
                char_count=65
            )
        ],
        total_chars=65
    )

    monkeypatch.setattr("glob.glob", lambda pat: ["NB1/book.fb2"])
    monkeypatch.setattr("story_forecaster.author.indexer.parse_fb2_file", lambda path: mock_book)

    # First index run
    res1 = index_meta_corpus(db=mem_db)
    assert res1["total_books_indexed"] == 1
    initial_artifacts = mem_db.query(Artifact).filter_by(type="trope_precedent").count()
    assert initial_artifacts >= 1

    # Second index run (idempotent deduplication via input_hash)
    res2 = index_meta_corpus(db=mem_db)
    second_artifacts = mem_db.query(Artifact).filter_by(type="trope_precedent").count()

    assert initial_artifacts == second_artifacts
