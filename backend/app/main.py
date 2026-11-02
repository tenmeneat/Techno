import asyncio
import hmac
import logging
import os
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1 import devices, events, push, readings, reports, ws
from app.core import config
from app.db.pool import close_pool, db, open_pool
from app.mqtt import ingest
from app.workers import diagnostics, weather_sync

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


async def supervise(name: str, factory, delay: float = 5.0):
    """워커가 예외로 죽거나 끝나버려도 로그를 남기고 다시 띄운다. API만 살아 있고 수집이 멈춘 상태를 막는다."""
    while True:
        try:
            await factory()
            log.error("워커 %s가 종료됨 — %.0f초 후 재시작", name, delay)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("워커 %s 오류 — %.0f초 후 재시작", name, delay)
        await asyncio.sleep(delay)


def check_public_config():
    """외부 공개(Funnel) 중인데 토큰이 비어 있으면 모든 API가 인증 없이 열린다 — 기동을 거부한다."""
    if config.API_TOKEN:
        return
    if config.PUBLIC:
        raise RuntimeError("PUBLIC=true인데 API_TOKEN이 비어 있습니다. .env에 API_TOKEN을 설정하세요.")
    log.warning("API_TOKEN이 비어 있어 인증 없이 동작합니다 (로컬 개발 전용). 외부 공개 시 PUBLIC=true로 막으세요.")


@asynccontextmanager
async def lifespan(_: FastAPI):
    check_public_config()
    await open_pool()
    # 재시작 전 상태 복원: 최근까지 데이터가 오던 기기는 열린 이벤트를 이어받고,
    # 아니면 이벤트를 '마지막 측정 시각'에 닫는다(서버가 꺼진 시간을 위험 시간에 넣지 않음)
    try:
        await ingest.restore()
    except Exception:  # 복원 실패로 서버 전체가 안 뜨는 것보다는, 상태를 비운 채 시작하는 게 낫다
        log.exception("상태 복원 실패 — 빈 상태로 시작")
        ingest.runtimes.clear()
        await db().execute("UPDATE events SET ended_at = now() WHERE ended_at IS NULL")
    tasks = [asyncio.create_task(supervise(n, f)) for n, f in
             (("ingest", ingest.run), ("stale", ingest.watch_stale),
              ("weather", weather_sync.run), ("diagnostics", diagnostics.run))]
    yield
    for t in tasks:
        t.cancel()
    await close_pool()


async def require_token(authorization: str = Header("")):
    """§7.3 학기 범위의 단순 토큰. 제대로 된 인증은 제외 항목(§1.2)."""
    if config.API_TOKEN and not hmac.compare_digest(authorization.encode(), f"Bearer {config.API_TOKEN}".encode()):
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
