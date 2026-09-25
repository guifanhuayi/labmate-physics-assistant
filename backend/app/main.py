import asyncio
from contextlib import asynccontextmanager, suppress
import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.api.auth import router as auth_router
from app.api.roster import router as roster_router
from app.api.templates import router as templates_router
from app.api.stage4 import router as stage4_router
from app.auth.errors import AuthError
from app.config import get_settings
from app.db.session import SessionLocal
from app.retention import purge_expired_assignments


settings = get_settings()
logger = logging.getLogger(__name__)


def _cleanup_expired_assignments() -> None:
    with SessionLocal() as db:
        purge_expired_assignments(db)


async def _retention_loop() -> None:
    while True:
        await asyncio.sleep(3600)
        try:
            _cleanup_expired_assignments()
        except Exception:
            logger.exception("Assignment retention cleanup failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        _cleanup_expired_assignments()
    except Exception:
        logger.exception("Assignment retention startup cleanup failed")
    cleanup_task = asyncio.create_task(_retention_loop())
    try:
        yield
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task


app = FastAPI(title="LabMate API", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)


@app.exception_handler(AuthError)
async def auth_error_handler(_: Request, exc: AuthError) -> JSONResponse:
    error = {"code": exc.code, "message": exc.message}
    if exc.details is not None:
        error["details"] = exc.details
    return JSONResponse(status_code=exc.status_code, content=jsonable_encoder({"error": error}))


@app.middleware("http")
async def same_origin_writes(request: Request, call_next):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if origin and origin not in settings.allowed_origins:
            return JSONResponse(
                status_code=403,
                content={"error": {"code": "forbidden_origin", "message": "请求来源不受信任。"}},
            )
    return await call_next(request)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(roster_router)
app.include_router(templates_router)
app.include_router(stage4_router)
