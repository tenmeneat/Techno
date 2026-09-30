from fastapi import APIRouter, HTTPException

from app.api.v1.schemas import Calibration, Current, Device, DevicePatch
from app.db.pool import db
from app.domain.psychrometrics import t80
from app.mqtt.ingest import runtimes

router = APIRouter(prefix="/devices", tags=["devices"])

DEVICE_COLS = "id, home_id, label, location_tag, fw, last_seen, online, calib_t_air, calib_rh, calib_t_surf"


def _state(device_id: str) -> str:
    rt = runtimes.get(device_id)
    return rt.state if rt else "STALE"


@router.get("", response_model=list[Device])
async def list_devices():
    rows = await db().fetch(f"SELECT {DEVICE_COLS} FROM devices ORDER BY id")
    return [{**r, "state": _state(r["id"])} for r in rows]


async def get_device(device_id: str) -> dict:
    r = await db().fetchrow(f"SELECT {DEVICE_COLS} FROM devices WHERE id = $1", device_id)
    if not r:
        raise HTTPException(404, "device not found")
    return {**r, "state": _state(device_id)}


@router.get("/{device_id}", response_model=Device)
async def device(device_id: str):
    return await get_device(device_id)


@router.patch("/{device_id}", response_model=Device)
async def patch_device(device_id: str, body: DevicePatch):
    await db().execute(
        "UPDATE devices SET label = coalesce($2, label), location_tag = coalesce($3, location_tag) WHERE id = $1",
        device_id, body.label, body.location_tag)
    return await get_device(device_id)


@router.get("/{device_id}/current", response_model=Current)
async def current(device_id: str):
    rows = await db().fetch(
        """SELECT DISTINCT ON (probe_id) time, probe_id, t_air, rh, t_surf, t_dew, rh_surf FROM readings
           WHERE device_id = $1 AND time > now() - interval '1 day' ORDER BY probe_id, time DESC""", device_id)
    rt = runtimes.get(device_id)
    return {"device_id": device_id, "state": _state(device_id), "forecast": rt.forecast if rt else None,
            "probes": [{**r, "t80": t80(r["t_air"], r["rh"])} for r in rows]}


@router.post("/{device_id}/calibration", response_model=Device)
async def calibrate(device_id: str, body: Calibration):
    """§8.4 오프셋. 이후 수신분부터 적용된다."""
    await db().execute(
        "UPDATE devices SET calib_t_air = $2, calib_rh = $3, calib_t_surf = $4 WHERE id = $1",
        device_id, body.t_air, body.rh, body.t_surf)
    return await get_device(device_id)
