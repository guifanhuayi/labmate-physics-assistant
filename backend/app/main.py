from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.auth import router as auth_router
from app.api.roster import router as roster_router
from app.api.templates import router as templates_router
from app.auth.errors import AuthError
from app.config import get_settings


settings = get_settings()
app = FastAPI(title="LabMate API", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")


@app.exception_handler(AuthError)
async def auth_error_handler(_: Request, exc: AuthError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message}})


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
