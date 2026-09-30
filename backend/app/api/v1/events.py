from datetime import datetime

from fastapi import APIRouter, Query

from app.api.v1.schemas import Event
from app.db.pool import db

router = APIRouter(prefix="/devices", tags=["events"])


@router.get("/{device_id}/events", response_model=list[Event])
async def events(device_id: str, from_: datetime = Query(alias="from"), to: datetime = Query()):
    return [dict(r) for r in await db().fetch(
        """SELECT id, state, started_at, ended_at, peak_rh_surf, min_delta_t FROM events
           WHERE device_id = $1 AND started_at < $3 AND coalesce(ended_at, now()) > $2
           ORDER BY started_at""", device_id, from_, to)]
