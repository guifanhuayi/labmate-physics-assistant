"""Run the LabMate API and built frontend as one local preview service."""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn
from fastapi import HTTPException
from fastapi.responses import FileResponse


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
    uvicorn.run(app, host="127.0.0.1", port=8010)
