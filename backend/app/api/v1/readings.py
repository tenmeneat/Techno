from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Query

from app.api.v1.schemas import ProbeReading
from app.db.pool import db
from app.domain.psychrometrics import t80

router = APIRouter(prefix="/devices", tags=["readings"])

# bucket → (원천 테이블/뷰, 시간 컬럼, 버킷 폭). 장기 그래프는 집계 뷰를 읽는다(§9.4)
SOURCES = {
    "raw": ("readings", "time", timedelta(seconds=1)),
    "1m": ("readings_1m", "bucket", timedelta(minutes=1)),
    "1h": ("readings_1h", "bucket", timedelta(hours=1)),
    "1d": ("readings_1h", "bucket", timedelta(days=1)),
}


@router.get("/{device_id}/series", response_model=list[ProbeReading])
async def series(device_id: str, from_: datetime = Query(alias="from"), to: datetime = Query(),
                 bucket: Literal["raw", "1m", "1h", "1d"] = "1m"):
    src, col, width = SOURCES[bucket]
    rows = await db().fetch(
        f"""SELECT time_bucket($4::interval, {col}) AS time, probe_id,
                   avg(t_air) AS t_air, avg(rh) AS rh, avg(t_surf) AS t_surf, avg(t_dew) AS t_dew, avg(rh_surf) AS rh_surf
            FROM {src} WHERE device_id = $1 AND {col} >= $2 AND {col} < $3
            GROUP BY 1, 2 ORDER BY 1""", device_id, from_, to, width)
    return [{**r, "t80": t80(r["t_air"], r["rh"])} for r in rows]
