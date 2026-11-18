"""실시간 푸시 (§10.4). WS는 갱신 신호일 뿐, 데이터 원천은 REST.

메시지:
  {"type": "reading", ...Current}
  {"type": "state", "device_id": str, "state": StateName, "at": iso8601}
"""
import asyncio
import hmac
from collections import defaultdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import API_TOKEN

router = APIRouter()
_subs: dict[str, set[WebSocket]] = defaultdict(set)  # device_id 또는 "*"(전체)
SEND_TIMEOUT_S = 2.0  # 느린(멈춘) 클라이언트 하나가 수집 파이프라인을 붙잡지 않게


async def _send(ws: WebSocket, msg: dict) -> bool:
    try:
        await asyncio.wait_for(ws.send_json(msg), SEND_TIMEOUT_S)
        return True
    except Exception:  # 타임아웃·끊김 모두 — 클라이언트는 재접속 후 REST로 공백을 메운다(live.ts)
        return False


async def broadcast(device_id: str, msg: dict):
    targets = list(_subs[device_id] | _subs["*"])
    # 동시에 보내므로 최악이어도 SEND_TIMEOUT_S 만큼만 기다린다
    for ws, ok in zip(targets, await asyncio.gather(*(_send(ws, msg) for ws in targets))):
        if not ok:
            _subs[device_id].discard(ws)
            _subs["*"].discard(ws)
            try:
                await asyncio.wait_for(ws.close(), 1)
            except Exception:
                pass


@router.websocket("/ws/live")
async def live(ws: WebSocket, device_id: str = "*", token: str = ""):
    if API_TOKEN and not hmac.compare_digest(token.encode(), API_TOKEN.encode()):
        await ws.close(code=1008)
        return
    await ws.accept()
    _subs[device_id].add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _subs[device_id].discard(ws)
