"""진단·리포트 (§10.2, §10.6). PDF는 프런트가 인쇄용 페이지로 만든다(브라우저 PDF 저장)."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Query

from app.api.v1.devices import get_device
from app.api.v1.schemas import Diagnostic, Report, ReportRequest
from app.core.config import TZ
from app.db.pool import db

router = APIRouter(tags=["reports"])

DIAG_SQL = """SELECT day, f_rsi, tdr, t_ext_avg, minutes_alert, mould_dose FROM daily_diagnostics
              WHERE device_id = $1 AND day >= $2::date AND day <= $3::date ORDER BY day"""


@router.get("/devices/{device_id}/diagnostics", response_model=list[Diagnostic])
async def diagnostics(device_id: str, days: int = Query(30, ge=1, le=365)):
    return [dict(r) for r in await db().fetch(DIAG_SQL, device_id, _today() - timedelta(days=days), _today())]


def _today():
    return datetime.now(TZ).date()


@router.post("/reports", response_model=Report)
async def report(body: ReportRequest):
    device = await get_device(body.device_id)
    args = (body.device_id, body.from_, body.to)
    minutes = {r["state"]: r["m"] for r in await db().fetch(
        """SELECT state, sum(extract(epoch FROM least(coalesce(ended_at, now()), $3) - greatest(started_at, $2))) / 60 AS m
           FROM events WHERE device_id = $1 AND state IN ('ALERT', 'CONDENSING')
             AND started_at < $3 AND coalesce(ended_at, now()) > $2 GROUP BY state""", *args)}
    event_days = await db().fetch(
        """SELECT DISTINCT (started_at AT TIME ZONE 'Asia/Seoul')::date AS d FROM events
           WHERE device_id = $1 AND state IN ('ALERT', 'CONDENSING') AND started_at >= $2 AND started_at < $3
           ORDER BY d""", *args)
    mean_rhs = await db().fetchval(
        "SELECT avg(rh_surf) FROM readings_1h WHERE device_id = $1 AND bucket >= $2 AND bucket < $3", *args)
    sources = await db().fetch(
        "SELECT source, count(*) AS n FROM weather_hourly WHERE time >= $1 AND time < $2 GROUP BY source",
        body.from_, body.to)
    return {
        "device": device, "from_": body.from_, "to": body.to,
        "minutes_alert": float(minutes.get("ALERT", 0)), "minutes_condensing": float(minutes.get("CONDENSING", 0)),
        "event_days": [r["d"] for r in event_days], "mean_rh_surf": mean_rhs,
        "diagnostics": [dict(r) for r in await db().fetch(
            DIAG_SQL, body.device_id, body.from_.astimezone(TZ).date(), body.to.astimezone(TZ).date())],
        "weather_sources": {r["source"]: r["n"] for r in sources},
    }
