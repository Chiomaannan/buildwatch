"""
main.py — FastAPI application entry point.

Startup sequence:
  1. Create all DB tables (idempotent)
  2. Mount API routers
  3. Expose health check endpoint
  4. WebSocket endpoint for real-time inference events (Redis pub/sub)
"""

import asyncio
import logging

import redis.asyncio as aioredis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import create_tables
from app.routers import images, plan, projects, reports, schedule, upload, worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("aic.main")
settings = get_settings()

app = FastAPI(
    title="BuildWatch API",
    description="IoT Construction Progress Monitoring — YOLO11n + MWPI",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(schedule.router)
app.include_router(upload.router)
app.include_router(images.router)
app.include_router(worker.router)
app.include_router(plan.router)
app.include_router(reports.router)


@app.on_event("startup")
def on_startup() -> None:
    logger.info("Running DB migrations (create_all) …")
    create_tables()
    logger.info("BuildWatch backend ready.")


@app.get("/health", tags=["Health"])
def health() -> dict:
    return {"status": "ok", "service": "buildwatch-backend"}


@app.get("/", tags=["Health"])
def root() -> dict:
    return {"message": "BuildWatch API", "docs": "/docs"}


# ── WebSocket — real-time inference events ─────────────────────────────────────

@app.websocket("/api/v1/ws/projects/{project_id}")
async def ws_inference_events(project_id: str, websocket: WebSocket) -> None:
    """
    WebSocket endpoint that streams inference events for a project.

    Celery workers publish to Redis channel  project:{project_id}:events
    after each inference completes. This endpoint subscribes and forwards
    those messages to the connected browser.

    Message format:
        {
            "event": "new_inference",
            "project_id": "...",
            "image_id": "...",
            "mwpi_score": 0.65,
            "detected_classes": ["foundation", "column"],
            "avg_confidence": 0.82,
            "annotated_image_url": "https://...",
            "timestamp": "2026-06-19T10:30:00Z"
        }
    """
    await websocket.accept()
    channel = f"project:{project_id}:events"
    r = aioredis.from_url(settings.redis_url)
    pubsub = r.pubsub()
    await pubsub.subscribe(channel)
    logger.info(f"WebSocket connected — project={project_id}")

    async def _redis_to_ws():
        async for message in pubsub.listen():
            if message["type"] == "message":
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode()
                try:
                    await websocket.send_text(data)
                except Exception:
                    return

    async def _ws_keepalive():
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass

    listener = asyncio.create_task(_redis_to_ws())
    keepalive = asyncio.create_task(_ws_keepalive())

    try:
        done, pending = await asyncio.wait(
            [listener, keepalive],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
    finally:
        await pubsub.unsubscribe(channel)
        await r.aclose()
        logger.info(f"WebSocket disconnected — project={project_id}")
