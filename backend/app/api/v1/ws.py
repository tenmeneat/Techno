"""실시간 푸시 (§10.4). WS는 갱신 신호일 뿐, 데이터 원천은 REST.

메시지:
  {"type": "reading", ...Current}
  {"type": "state", "device_id": str, "state": StateName, "at": iso8601}
"""
from collections import defaultdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import API_TOKEN

router = APIRouter()
_subs: dict[str, set[WebSocket]] = defaultdict(set)  # device_id 또는 "*"(전체)


async def broadcast(device_id: str, msg: dict):
    for ws in list(_subs[device_id] | _subs["*"]):
        try:
            await ws.send_json(msg)
        except Exception:
            _subs[device_id].discard(ws)
            _subs["*"].discard(ws)


@router.websocket("/ws/live")
async def live(ws: WebSocket, device_id: str = "*", token: str = ""):
    if API_TOKEN and token != API_TOKEN:
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
