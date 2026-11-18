import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1 import devices, events, push, readings, reports, ws
from app.core import config
from app.db.migrate import migrate_notifications
from app.db.pool import close_pool, db, open_pool
from app.mqtt import ingest
from app.workers import diagnostics, notifier, weather_sync

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await open_pool()
    tasks = []
    try:
        await migrate_notifications()
        await notifier.reconcile_history()
        # Keep the existing ingest startup behavior; restore() belongs to the other branch.
        await db().execute("UPDATE events SET ended_at = now() WHERE ended_at IS NULL")
        tasks = [asyncio.create_task(c) for c in (
            ingest.run(), ingest.watch_stale(), weather_sync.run(),
            diagnostics.run(), notifier.maintain_history(),
        )]
        yield
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await ingest.stop_notifications()
        await close_pool()


async def require_token(authorization: str = Header("")):
    """§7.3 학기 범위의 단순 토큰. 제대로 된 인증은 제외 항목(§1.2)."""
    if config.API_TOKEN and authorization != f"Bearer {config.API_TOKEN}":
        raise HTTPException(401)


app = FastAPI(title="결로·곰팡이 예측 API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])

api = APIRouter(prefix="/api/v1", dependencies=[Depends(require_token)])
for m in (devices, readings, events, reports, push):
    api.include_router(m.router)
app.include_router(api)
app.include_router(ws.router)

# 프런트 정적 빌드(frontend/out)를 같은 출처로 서빙. API 라우트 뒤에 마운트해야 /api, /ws가 먼저 잡힌다
if os.path.isdir(config.STATIC_DIR):
    app.mount("/", StaticFiles(directory=config.STATIC_DIR, html=True), name="web")
