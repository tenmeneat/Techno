import json

from fastapi import APIRouter

from app.api.v1.schemas import PushSubscription
from app.core.config import VAPID_PUBLIC_KEY
from app.db.pool import db

router = APIRouter(prefix="/push", tags=["push"])


@router.get("/vapid-public-key")
async def vapid_public_key() -> str:
    return VAPID_PUBLIC_KEY


@router.post("/subscribe", status_code=204)
async def subscribe(body: PushSubscription):
    await db().execute(
        """INSERT INTO push_subscriptions (endpoint, keys, quiet_start, quiet_end) VALUES ($1, $2, $3, $4)
           ON CONFLICT (endpoint) DO UPDATE SET keys = $2, quiet_start = $3, quiet_end = $4""",
        body.endpoint, json.dumps(body.keys), body.quiet_start, body.quiet_end)
