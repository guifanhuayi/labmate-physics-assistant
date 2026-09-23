"""Run the LabMate API and built frontend as one local preview service."""

from __future__ import annotations

import os
from pathlib import Path
import shutil

import uvicorn
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import inspect


BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent
DIST_DIR = PROJECT_DIR / "frontend" / "dist"
DATABASE_PATH = BACKEND_DIR / "labmate-preview.sqlite"

os.environ.setdefault("DATABASE_URL", f"sqlite:///{DATABASE_PATH.as_posix()}")
os.environ.setdefault("DEMO_AUTH_ENABLED", "true")
os.environ.setdefault(
    "ALLOWED_ORIGINS",
    '["http://127.0.0.1:8010", "http://localhost:8010"]',
)

from app.main import app  # noqa: E402  Settings must be configured before app import.
from app.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.seed import main as seed_demo_users  # noqa: E402


def prepare_preview_database() -> None:
    """Create a new preview database or preserve and migrate an older one."""
    preview_db_path = Path(engine.url.database or DATABASE_PATH)
    migration_config = Config(str(BACKEND_DIR / "alembic.ini"))
    migration_config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    if not tables:
        Base.metadata.create_all(engine)
        command.stamp(migration_config, "head")
    elif "alembic_version" not in tables:
        stage_three_tables = {
            "users", "auth_sessions", "audit_logs", "classes", "class_members",
            "roster_imports", "experiment_templates", "template_versions", "assignments",
        }
        user_columns = {column["name"] for column in inspector.get_columns("users")} if "users" in tables else set()
        if not stage_three_tables.issubset(tables):
            raise SystemExit("预览数据库结构无法自动识别，请先备份并检查数据库。")
        if "phone_number" not in user_columns:
            backup_path = preview_db_path.with_name(f"{preview_db_path.stem}-pre-migration{preview_db_path.suffix}")
            if not backup_path.exists():
                shutil.copy2(preview_db_path, backup_path)
            command.stamp(migration_config, "20260921_0003")
        elif {"phone_number", "enrollment_completed"}.issubset(user_columns):
            command.stamp(migration_config, "head")
        else:
            raise SystemExit("预览数据库用户表结构无法自动识别，请先备份并检查数据库。")
        command.upgrade(migration_config, "head")
    else:
        command.upgrade(migration_config, "head")

    if get_settings().demo_auth_enabled:
        seed_demo_users()


@app.get("/", include_in_schema=False)
def frontend_root() -> FileResponse:
    return FileResponse(DIST_DIR / "index.html")


@app.get("/{requested_path:path}", include_in_schema=False)
def frontend_route(requested_path: str) -> FileResponse:
    """Serve frontend assets and fall back to index.html for Vue routes."""
    if requested_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")

    requested_file = (DIST_DIR / requested_path).resolve()
    if requested_file.is_file() and DIST_DIR.resolve() in requested_file.parents:
        return FileResponse(requested_file)
    return FileResponse(DIST_DIR / "index.html")


if __name__ == "__main__":
    if not (DIST_DIR / "index.html").is_file():
        raise SystemExit("Frontend build not found. Run `pnpm build` in frontend first.")
    prepare_preview_database()
    uvicorn.run(app, host="127.0.0.1", port=8010)
