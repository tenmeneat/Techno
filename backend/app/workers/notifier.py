
"""Web Push 알림 처리.

현재 ingest.py와 호환되는 1차 안정화 버전.
알림 실패가 센서 데이터 수집을 중단시키지 않도록 한다.
"""

import asyncio
import json
import logging
import time
from collections import defaultdict
from datetime import datetime

from pywebpush import WebPushException, webpush

from app.core import config
from app.db.pool import db
from app.domain.forecast import Forecast

log = logging.getLogger(__name__)

STATE_PUSH = {
    "ALERT": (
        "곰팡이 위험 구간",
        "벽면 습도가 80%를 넘었습니다. 환기하세요.",
    ),
    "CONDENSING": (
        "결로 발생 중",
        "벽면에 물이 맺히는 조건입니다. 지금 환기하세요.",
    ),
}

_forecast_sent: dict[str, list[float]] = defaultdict(list)
_forecast_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


def _quiet(hour: int, start: int, end: int) -> bool:
    """알림 무음 시간인지 판단한다."""
    if start == end:
        return False

    if start > end:
        return hour >= start or hour < end

    return start <= hour < end


async def send(
    title: str,
    body: str,
    url: str,
    bypass_quiet: bool = False,
) -> bool:
    """푸시 발송. 한 구독이라도 성공하면 True."""

    try:
        if not config.VAPID_PRIVATE_KEY:
            log.info("[push 미설정] %s — %s", title, body)
            return False

        subscriptions = await db().fetch(
            """
            SELECT endpoint, keys, quiet_start, quiet_end
            FROM push_subscriptions
            """
        )

        hour = datetime.now(config.TZ).hour
        payload = json.dumps({
            "title": title,
            "body": body,
            "url": url,
        })

        success_count = 0

        for subscription in subscriptions:
            if (
                not bypass_quiet
                and _quiet(
                    hour,
                    subscription["quiet_start"],
                    subscription["quiet_end"],
                )
            ):
                continue

            try:
                keys = subscription["keys"]

                if isinstance(keys, str):
                    keys = json.loads(keys)

                await asyncio.wait_for(
                    asyncio.to_thread(
                        webpush,
                        subscription_info={
                            "endpoint": subscription["endpoint"],
                            "keys": keys,
                        },
                        data=payload,
                        vapid_private_key=config.VAPID_PRIVATE_KEY,
                        vapid_claims={
                            "sub": config.VAPID_SUBJECT,
                        },
                        timeout=5,
                    ),
                    timeout=8,
                )

                success_count += 1

            except WebPushException as exc:
                response = exc.response

                if (
                    response is not None
                    and response.status_code in (404, 410)
                ):
                    try:
                        await db().execute(
                            """
                            DELETE FROM push_subscriptions
                            WHERE endpoint = $1
                            """,
                            subscription["endpoint"],
                        )
                    except Exception:
                        log.exception(
                            "만료된 푸시 구독 삭제 실패"
                        )
                else:
                    log.warning(
                        "Web Push 발송 실패: %s",
                        exc,
                    )

            except Exception:
                log.exception(
                    "구독자별 푸시 처리 실패: %s",
                    subscription["endpoint"],
                )

        return success_count > 0

    except Exception:
        log.exception("알림 시스템 처리 실패")
        return False


async def on_state(device_id: str, state: str) -> None:
    """기존 ingest.py 호출 형태를 유지한다."""

    try:
        if state not in STATE_PUSH:
            return

        title, body = STATE_PUSH[state]

        await send(
            title,
            body,
            f"/device/?id={device_id}",
            bypass_quiet=(state == "CONDENSING"),
        )

    except Exception:
        log.exception(
            "상태 알림 처리 실패: %s",
            device_id,
        )


async def on_forecast(
    device_id: str,
    state: str,
    fc: Forecast,
) -> None:
    """예측 알림: 24시간 최대 2회, 최소 간격 3시간."""

    if state not in ("SAFE", "WATCH"):
        return

    try:
        async with _forecast_locks[device_id]:
            now = time.time()

            sent = [
                t for t in _forecast_sent[device_id]
                if now - t < 86400
            ]

            _forecast_sent[device_id] = sent

            if len(sent) >= 2:
                return

            if sent and now - sent[-1] < 3 * 3600:
                return

            what = (
                "곰팡이 위험 구간"
                if fc.target < 100
                else "결로"
            )

            success = await send(
                "곧 습해집니다",
                (
                    f"약 {fc.hours_low:.1f}–"
                    f"{fc.hours_high:.1f}시간 뒤 "
                    f"{what} 진입 예상. "
                    "미리 환기하세요."
                ),
                f"/device/?id={device_id}",
            )

            # 실제 발송 성공 시에만 횟수를 기록
            if success:
                sent.append(time.time())

    except Exception:
        log.exception(
            "예측 알림 처리 실패: %s",
            device_id,
        )
