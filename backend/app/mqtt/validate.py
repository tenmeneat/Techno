"""수집 입력 검증과 판정 게이트 (§9.5). 순수 함수만 — I/O 금지, DB 없이 테스트한다.

하드웨어 계약이 확정되기 전까지는 방어적으로 둔다 (확정되면 이 파일의 상수만 고친다):
- ts는 epoch 초(int). NTP 동기 전 값(1970년대)이나 밀리초는 범위 검사에서 걸러진다.
- 센서 오류는 null, NaN, 또는 DS18B20 고유 오류값(-127 연결 끊김, 85 전원 리셋)으로 올 수 있다.
- 오프라인 버퍼(최대 6시간, §8.2)는 재접속 후 실시간 데이터보다 먼저 올 수도, 섞여 올 수도 있다.
"""
import math
from typing import Literal

# 센서 유효 범위 — 원룸 실내·벽면 기준. 밖이면 고장으로 본다
T_AIR_RANGE = (-20.0, 50.0)
RH_RANGE = (0.0, 100.0)          # 0 초과 ~ 100 이하
T_SURF_RANGE = (-30.0, 50.0)
DS18B20_ERRORS = (-127.0, 85.0)  # 범위 밖이라 어차피 걸리지만, 의도를 남겨 둔다

# 기기 시각 허용 범위
MAX_FUTURE_S = 300           # 기기 시계가 앞서 있어도 5분까지는 허용
MAX_AGE_S = 7 * 3600         # 오프라인 버퍼 6시간 + 여유
LIVE_WINDOW_S = 300          # 이보다 오래된 데이터는 판정은 하되 알림은 보내지 않는다

Kind = Literal["live", "late", "out_of_order"]


def _finite(v: float | None) -> bool:
    return v is not None and math.isfinite(v)


def check_ts(ts: int, now: float) -> str | None:
    """기기 시각 검사. 문제가 있으면 사유 문자열, 정상이면 None."""
    if ts > now + MAX_FUTURE_S:
        return f"ts가 미래({ts - now:.0f}s 앞섬) — 밀리초 단위이거나 기기 시계 오류"
    if ts < now - MAX_AGE_S:
        return f"ts가 너무 과거({(now - ts) / 3600:.1f}h 전) — NTP 동기 전 값이거나 버퍼 한도 초과"
    return None


def check_air(t_air: float | None, rh: float | None) -> str | None:
    """실내 온습도 검사. 이게 틀리면 모든 프로브의 표면습도가 틀리므로 메시지 전체를 버린다."""
    if not _finite(t_air) or not T_AIR_RANGE[0] <= t_air <= T_AIR_RANGE[1]:
        return f"실내 온도 이상값: {t_air}"
    if not _finite(rh) or not RH_RANGE[0] < rh <= RH_RANGE[1]:
        return f"실내 습도 이상값: {rh}"
    return None


def surface_ok(t_surf: float | None) -> bool:
    """벽면 프로브 값이 쓸 수 있는가. 고장 프로브 하나 때문에 메시지 전체를 버리지 않도록 프로브 단위로 본다."""
    return (_finite(t_surf) and t_surf not in DS18B20_ERRORS
            and T_SURF_RANGE[0] <= t_surf <= T_SURF_RANGE[1])


def classify(ts: int, last_ts: int, now: float) -> Kind:
    """저장은 항상 하고, 이 결과로 판정·알림 여부를 정한다.

    - out_of_order: 이미 처리한 시각 이하 → 저장만. 상태·중앙값·예측을 건드리지 않는다
    - late: 순서는 맞지만 오래됨(백로그) → 판정은 하되 알림은 보내지 않는다
    - live: 실시간 → 판정 + 알림
    """
    if ts <= last_ts:
        return "out_of_order"
    if now - ts > LIVE_WINDOW_S:
        return "late"
    return "live"
