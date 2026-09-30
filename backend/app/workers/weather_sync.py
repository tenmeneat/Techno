"""외기온 수집 (§4.5). 기상청 API허브 ASOS 주 경로, 실패 시 Open-Meteo 폴백."""
import asyncio
import logging
from datetime import UTC, datetime, timedelta

import httpx

from app.core import config
from app.db.pool import db

log = logging.getLogger(__name__)


async def fetch_kma(client: httpx.AsyncClient, hour: datetime) -> tuple[float, float | None]:
    r = await client.get("https://apihub.kma.go.kr/api/typ01/url/kma_sfctm2.php", params={
        "tm": hour.astimezone(config.TZ).strftime("%Y%m%d%H00"), "stn": config.KMA_STN,
        "help": 0, "authKey": config.KMA_AUTH_KEY})
    r.raise_for_status()
    for line in r.text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        # 컬럼: TM STN WD WS GST_WD GST_WS GST_TM PA PS PT PR TA TD HM ...  (help=1로 호출하면 설명이 나온다)
        cols = line.split()
        ta, hm = float(cols[11]), float(cols[13])
        if ta < -50:  # -99 = 결측
            raise ValueError("KMA 결측값")
        return ta, (hm if hm >= 0 else None)
    raise ValueError("KMA 빈 응답")


async def fetch_open_meteo(client: httpx.AsyncClient, hour: datetime) -> tuple[float, float | None]:
    r = await client.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": config.LAT, "longitude": config.LON, "timezone": "UTC",
        "hourly": "temperature_2m,relative_humidity_2m", "past_days": 1, "forecast_days": 1})
    r.raise_for_status()
    h = r.json()["hourly"]
    i = h["time"].index(hour.strftime("%Y-%m-%dT%H:00"))
    return h["temperature_2m"][i], h["relative_humidity_2m"][i]


async def sync_hour(client: httpx.AsyncClient, hour: datetime) -> str:
    source = "kma"
    try:
        if not config.KMA_AUTH_KEY:
            raise ValueError("KMA_AUTH_KEY 없음")
        t, rh = await fetch_kma(client, hour)
    except Exception as e:
        log.info("KMA 실패(%s) → Open-Meteo", e)
        source = "open-meteo"
        t, rh = await fetch_open_meteo(client, hour)
    await db().execute(
        """INSERT INTO weather_hourly (time, region_code, t_ext, rh_ext, source) VALUES ($1, $2, $3, $4, $5)
           ON CONFLICT (region_code, time) DO UPDATE SET t_ext = $3, rh_ext = $4, source = $5""",
        hour, config.REGION_CODE, t, rh, source)
    return source


async def run():
    fallback_streak = 0
    async with httpx.AsyncClient(timeout=10) as client:
        while True:
            hour = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
            try:
                fallback_streak = fallback_streak + 1 if await sync_hour(client, hour) != "kma" else 0
                if fallback_streak >= 24:
                    log.warning("외기온 폴백 %d시간 연속 — KMA 키/응답 확인", fallback_streak)
            except Exception:
                log.exception("외기온 두 소스 모두 실패 %s", hour)
            # 정시 관측이 올라오는 매시 10분에 다음 호출
            await asyncio.sleep((hour + timedelta(hours=1, minutes=10) - datetime.now(UTC)).total_seconds())
