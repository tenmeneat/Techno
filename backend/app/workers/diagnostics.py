"""일간 진단 집계 (§4.3, §3.4). 매일 07:00 KST에 전날 분을 계산한다."""
import asyncio
import logging
import statistics
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from app.core import config
from app.db.pool import db
from app.domain.psychrometrics import f_rsi

log = logging.getLogger(__name__)
NIGHT_HOURS = range(2, 6)  # 02:00–06:00 KST만 fRsi에 사용 (일사 영향 배제)


async def compute_day(day: date):
    start = datetime.combine(day, time(0), config.TZ)
    end = start + timedelta(days=1)
    t_ext = {r["time"]: r["t_ext"] for r in await db().fetch(
        "SELECT time, t_ext FROM weather_hourly WHERE region_code = $1 AND time >= $2 AND time < $3",
        config.REGION_CODE, start, end)}
    t_ext_avg = statistics.fmean(t_ext.values()) if t_ext else None

    for dev in await db().fetch("SELECT id FROM devices"):
        rows = await db().fetch(
            """SELECT time, probe_id, t_air, t_surf, rh_surf FROM readings
               WHERE device_id = $1 AND time >= $2 AND time < $3 ORDER BY time""", dev["id"], start, end)
        f_by_probe, dose_by_probe, prev = defaultdict(list), defaultdict(float), {}
        for r in rows:
            p = r["probe_id"]
            # 곰팡이 노출량 D = Σ(RHs−80)·Δt [%·h]. 1분 넘는 공백은 1분으로 자른다
            if p in prev:
                dt = min((r["time"] - prev[p]).total_seconds(), 60) / 3600
                dose_by_probe[p] += max(0.0, r["rh_surf"] - 80) * dt
            prev[p] = r["time"]
            local = r["time"].astimezone(config.TZ)
            te = t_ext.get(r["time"].replace(minute=0, second=0, microsecond=0))
            if local.hour in NIGHT_HOURS and te is not None:
                f = f_rsi(r["t_air"], r["t_surf"], te)
                if f is not None:
                    f_by_probe[p].append(f)

        # 한 기기에 프로브가 여럿이면 가장 나쁜 지점을 대표값으로
        f_day = min((statistics.median(v) for v in f_by_probe.values()), default=None)
        minutes_alert = await db().fetchval(
            """SELECT coalesce(sum(extract(epoch FROM least(coalesce(ended_at, now()), $3) - greatest(started_at, $2))) / 60, 0)
               FROM events WHERE device_id = $1 AND state IN ('ALERT', 'CONDENSING')
                 AND started_at < $3 AND coalesce(ended_at, now()) > $2""", dev["id"], start, end)
        await db().execute(
            """INSERT INTO daily_diagnostics (day, device_id, f_rsi, tdr, t_ext_avg, minutes_alert, mould_dose)
               VALUES ($1, $2, $3, $4, $5, $6, $7)
               ON CONFLICT (day, device_id) DO UPDATE SET f_rsi = $3, tdr = $4, t_ext_avg = $5,
                 minutes_alert = $6, mould_dose = $7""",
            day, dev["id"], f_day, None if f_day is None else 1 - f_day, t_ext_avg,
            float(minutes_alert), max(dose_by_probe.values(), default=0.0))


async def run():
    while True:
        yesterday = datetime.now(config.TZ).date() - timedelta(days=1)
        try:
            await compute_day(yesterday)  # 기동 직후에도 한 번 — 07:00를 놓쳤어도 채워진다
        except Exception:
            log.exception("진단 집계 실패 %s", yesterday)
        now = datetime.now(config.TZ)
        nxt = datetime.combine(now.date(), time(7), config.TZ)
        if nxt <= now:
            nxt += timedelta(days=1)
        await asyncio.sleep((nxt - now).total_seconds())
