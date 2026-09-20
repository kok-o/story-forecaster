from story_forecaster.ingestion.updater import IncrementalChapterUpdater
from story_forecaster.db import SessionLocal
from story_forecaster.db.models import Chapter, Scene, WorkVersion

def test_incremental_chapter_updater():
    updater = IncrementalChapterUpdater()
    synthetic_text = """
    # Глава 99: Тестовый инкремент
    
    Хачиман проверил работоспособность инкрементального пайплайна.
    
    ***
    
    Кадзума загрузил очередную партию ядер маны в Хорадримский Куб.
    """

    res = updater.update_chapter(
        raw_text=synthetic_text,
        title="Глава 99: Тестовый инкремент",
        ordinal=99
    )

    assert res["chapter_ordinal"] == 99
    assert res["scenes_count"] >= 2
    assert res["discourse_seq_end"] >= res["discourse_seq_start"]
    assert res["version_sha256"] != ""

    # Verify in DB
    db = SessionLocal()
    try:
        ch = db.query(Chapter).filter_by(ordinal=99).first()
        assert ch is not None
        assert "Тестовый инкремент" in ch.title
        scenes = db.query(Scene).filter_by(chapter_id=ch.id).all()
        assert len(scenes) >= 2

        # Clean up synthetic test data
        db.query(Scene).filter_by(chapter_id=ch.id).delete()
        db.delete(ch)
        db.commit()
    finally:
        db.close()

def test_incremental_chapter_updater_edit_past_chapter():
    """Verify that editing an existing chapter creates a new WorkVersion and keeps discourse_seq contiguous."""
    updater = IncrementalChapterUpdater()
    updated_text = """
    # Глава 01: Обновленный пролог
    
    Это совершенно новый пролог книги.
    
    ***
    
    Вторая сцена нового пролога без сдвига в конец книги.
    """

    res = updater.update_chapter(
        raw_text=updated_text,
        title="Глава 01: Обновленный пролог",
        ordinal=1,
        create_new_version_on_edit=True
    )

    assert res["created_new_version"] is True
    assert res["chapter_ordinal"] == 1
    assert res["discourse_seq_start"] == 1
    assert res["discourse_seq_end"] >= 2

    # Verify in DB that Chapter 2 scenes in this new version immediately follow Chapter 1
    db = SessionLocal()
    try:
        new_version_id = res["work_version_id"]
        ch1 = db.query(Chapter).filter_by(work_version_id=new_version_id, ordinal=1).first()
        ch2 = db.query(Chapter).filter_by(work_version_id=new_version_id, ordinal=2).first()
        assert ch1 is not None and ch2 is not None

        ch1_scenes = db.query(Scene).filter_by(chapter_id=ch1.id).order_by(Scene.discourse_seq.asc()).all()
        ch2_scenes = db.query(Scene).filter_by(chapter_id=ch2.id).order_by(Scene.discourse_seq.asc()).all()

        assert ch1_scenes[-1].discourse_seq + 1 == ch2_scenes[0].discourse_seq
    finally:
        db.close()

