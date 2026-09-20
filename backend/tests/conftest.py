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

@pytest.fixture(scope="session", autouse=True)
def cleanup_isolated_test_db():
    yield
    try:
        if os.path.exists(_temp_db_path):
            os.remove(_temp_db_path)
    except Exception:
        pass

