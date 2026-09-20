from .session import Base, engine, SessionLocal, get_db
from .models import (
    Project,
    Work,
    WorkVersion,
    Chapter,
    Scene,
    Artifact,
    Run,
    Candidate,
    Branch,
    BranchScene
)

def migrate_columns():
    """Safely adds newly required columns to existing SQLite tables without data loss."""
    try:
        with engine.connect() as conn:
            # Check runs table
            res = conn.exec_driver_sql("PRAGMA table_info(runs)").fetchall()
            existing_run_cols = {row[1] for row in res}
            if existing_run_cols:
                new_run_cols = [
                    ("model_name", "VARCHAR(100)"),
                    ("prompt_version", "VARCHAR(50) DEFAULT 'v2.0'"),
                    ("request_payload_json", "JSON"),
                    ("response_raw_text", "TEXT"),
                    ("usage_json", "JSON"),
                    ("error_message", "TEXT")
                ]
                for col_name, col_type in new_run_cols:
                    if col_name not in existing_run_cols:
                        conn.exec_driver_sql(f"ALTER TABLE runs ADD COLUMN {col_name} {col_type}")

            # Check candidates table
            res_c = conn.exec_driver_sql("PRAGMA table_info(candidates)").fetchall()
            existing_cand_cols = {row[1] for row in res_c}
            if existing_cand_cols:
                new_cand_cols = [
                    ("citations_json", "JSON"),
                    ("raw_candidate_json", "JSON")
                ]
                for col_name, col_type in new_cand_cols:
                    if col_name not in existing_cand_cols:
                        conn.exec_driver_sql(f"ALTER TABLE candidates ADD COLUMN {col_name} {col_type}")

            conn.commit()
    except Exception:
        pass

def init_db():
    """Initializes all database tables and applies non-destructive column migrations."""
    Base.metadata.create_all(bind=engine)
    migrate_columns()

# Ensure migration is run whenever db is loaded
init_db()

__all__ = [
    "Base",
    "engine",
    "SessionLocal",
    "get_db",
    "init_db",
    "Project",
    "Work",
    "WorkVersion",
    "Chapter",
    "Scene",
    "Artifact",
    "Run",
    "Candidate",
    "Branch",
    "BranchScene"
]
