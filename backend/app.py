"""FastAPI entry point; supports both backend.app:app and legacy app:app."""
import sys
from contextlib import asynccontextmanager
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "backend"

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

from .config import Settings
from .db import make_engine, session_factory
from .dependencies import actor
from .routers import router
from .operations import router as operations_router
from .services.inference import Inference
from .scheduling import router as scheduling_router, start_scheduler
from .replacements import router as replacements_router


def create_app(settings=None):
    settings = settings or Settings.from_env()
    engine = make_engine(settings.database_url)
    inference = Inference(settings)

    @asynccontextmanager
    async def lifespan(app):
        inference.load()
        if settings.require_model and inference.model is None:
            raise RuntimeError(inference.message)
        scheduler = start_scheduler(app.state.sessions) if settings.mode == 'production' else None
        try:
            yield
        finally:
            if scheduler:
                scheduler[0].set()
                scheduler[1].join(timeout=5)
            engine.dispose()

    app = FastAPI(title="SafeSense Bus Safety API", version="2.0.0", lifespan=lifespan,
                  description="Prototype: GPS never confirms drop-off; camera zero never certifies an empty bus.")
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessions = session_factory(engine)
    app.state.inference = inference
    app.state.navigation_cache = {}
    app.add_middleware(CORSMiddleware, allow_origins=[
        "http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:4173", "http://localhost:4173"
    ], allow_methods=["GET", "POST", "PATCH"], allow_headers=["Content-Type", "Authorization", "Idempotency-Key"])

    @app.exception_handler(IntegrityError)
    async def conflict(request, exc):
        return JSONResponse(status_code=409, content={"detail": "Conflicting or duplicate record; refresh and review"})

    @app.exception_handler(OperationalError)
    async def unavailable(request, exc):
        return JSONResponse(status_code=503, content={"detail": "Database unavailable; check migrations and connectivity"})

    @app.middleware("http")
    async def privacy_headers(request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > settings.max_upload_bytes + 64 * 1024:
                    return JSONResponse(status_code=413, content={"detail": "Request body is too large"})
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length"})
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/health")
    def health():
        database_online = False
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT version_num FROM alembic_version"))
                database_online = True
        except Exception:
            pass
        return {"backend_online": True, "database_online": database_online,
                "model_loaded": inference.model is not None, "message": inference.message,
                "classes": getattr(inference.model, "names", {}), "mode": settings.mode,
                "routing_configured": bool(settings.osrm_url), "confidence_threshold": settings.confidence}

    @app.get('/ready')
    def ready():
        status = health()
        available = status['database_online'] and (status['model_loaded'] or not settings.require_model)
        return JSONResponse({'ready': available}, status_code=200 if available else 503)

    @app.post("/predict")
    def predict(file: UploadFile = File(...), frame_id: str = Form(default="", max_length=100),
                captured_at: float | None = Form(default=None), who=Depends(actor)):
        if who.role not in {"admin", "driver"}:
            raise HTTPException(403, "Camera access is restricted")
        data = file.file.read(settings.max_upload_bytes + 1)
        return inference.predict(data, frame_id, captured_at)

    app.include_router(router)
    app.include_router(operations_router)
    app.include_router(scheduling_router)
    app.include_router(replacements_router)
    dist = Path(__file__).resolve().parents[1] / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="dashboard")
    return app


app = create_app()
