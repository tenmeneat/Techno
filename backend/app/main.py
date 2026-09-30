import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import devices, events, push, readings, reports, ws
from app.core import config
from app.db.pool import close_pool, db, open_pool
from app.mqtt import ingest
from app.workers import diagnostics, weather_sync

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await open_pool()
    # 재시작 전 열려 있던 이벤트 정리 (메모리 상태는 새로 시작하므로)
    await db().execute("UPDATE events SET ended_at = now() WHERE ended_at IS NULL")
    tasks = [asyncio.create_task(c) for c in
             (ingest.run(), ingest.watch_stale(), weather_sync.run(), diagnostics.run())]
    yield
    for t in tasks:
        t.cancel()
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
