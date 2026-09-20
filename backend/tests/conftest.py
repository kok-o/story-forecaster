import sys
import os

# Ensure backend/src is in sys.path for pytest
src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

import shutil
import tempfile
from pathlib import Path
import pytest

# Isolated Test Database: copy data/story_forecaster.db to a temp file so tests never mutate prod DB
_prod_db = (Path(__file__).resolve().parents[2] / "data" / "story_forecaster.db").resolve()
_temp_db_file = tempfile.NamedTemporaryFile(suffix="_test.db", delete=False)
_temp_db_path = _temp_db_file.name
_temp_db_file.close()

if _prod_db.exists():
    shutil.copyfile(str(_prod_db), _temp_db_path)

os.environ["DATABASE_URL"] = f"sqlite:///{Path(_temp_db_path).as_posix()}"

def _seed_synthetic_work_if_needed():
    """Guarantees hermetic test execution on clean machines without user database."""
    from story_forecaster.db import SessionLocal, init_db
    from story_forecaster.db.models import Project, Work, WorkVersion, Chapter, Scene

    init_db()
    session = SessionLocal()
    try:
        work = session.query(Work).filter_by(role="target").first()
        if not work:
            proj = Project(id="synth_proj", name="Synthetic Project", description="Hermetic Test Project")
            session.add(proj)
            session.flush()

            target_work = Work(
                id="synth_target_work",
                project_id=proj.id,
                title="Королева Защиты",
                author_name="N.B.",
                role="target",
                fandom_metadata_json={"universe": "HOTD", "genre": ["RealRPG"]}
            )
            session.add(target_work)
            session.flush()

            ver = WorkVersion(
                id="synth_ver_1",
                work_id=target_work.id,
                original_sha256="synth_sha",
                normalized_sha256="synth_norm_sha",
                source_path="synthetic"
            )
            session.add(ver)
            session.flush()

            seq = 1
            for ch_num in range(1, 25):
                ch = Chapter(
                    id=f"synth_ch_{ch_num}",
                    work_version_id=ver.id,
                    ordinal=ch_num,
                    title=f"Глава {ch_num:02d}",
                    char_count=1000,
                    source_file=f"chapter_{ch_num:02d}.txt"
                )
                session.add(ch)
                session.flush()

                for sc_num in range(1, 3):
                    sc = Scene(
                        id=f"synth_sc_{ch_num}_{sc_num}",
                        chapter_id=ch.id,
                        ordinal=sc_num,
                        discourse_seq=seq,
                        start_char=(sc_num - 1) * 500,
                        end_char=sc_num * 500,
                        summary=f"Глава {ch_num}, Сцена {sc_num}. Хачиман и Кадзума обсуждают Систему и ярмарку осколков.",
                        content=f"Сцена {sc_num} главы {ch_num}. Хачиман спокойно оценил обстановку. Кадзума поправил Очки-оценки. Фея угрожающе посмотрела на шест."
                    )
                    session.add(sc)
                    seq += 1

            session.commit()
    finally:
        session.close()

_seed_synthetic_work_if_needed()

@pytest.fixture(scope="session", autouse=True)
def cleanup_isolated_test_db():
    yield
    try:
        if os.path.exists(_temp_db_path):
            os.remove(_temp_db_path)
    except Exception:
        pass

