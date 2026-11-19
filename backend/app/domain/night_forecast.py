"""밤사이 물리 기반 예측 (B-02 계산 부분). 순수함수만 — I/O 금지.

현행 OLS(forecast.py)는 2시간 지평이라 취침 시점에 필요한 6~8시간 예측을 못 한다.
여기서는 외기 예보 Te(t)와 벽의 fRsi로 벽면온도를 구하고, 실내 수증기압은 지금 값을 유지한다고 보고
벽면 표면습도 곡선을 계산한다.
    Ts(t)  = Te(t) + fRsi · (Ta − Te(t))
    RHs(t) = e / es(Ts(t)),  e = RH · es(Ta)  (실내 수증기량 유지)
가정: 실내 온도 Ta·수증기량 일정(난방·환기·샤워 없음). 실제 생활 변화는 반영하지 않으므로 '이대로 두면' 시나리오다.
외기 예보 소스(기상청 단기예보 vs Open-Meteo)와 저장 테이블은 팀 결정 후 workers 쪽에서 붙인다.
"""
from dataclasses import dataclass

from app.domain.humidity_cap import es, surface_temp

RHS_LIMIT = 80.0


@dataclass(frozen=True)
class NightForecast:
    max_rh_surf: float               # 밤사이 최대 표면습도 [%] (100 클립)
    max_at: float                    # 최대가 되는 시각 (epoch초)
    first_over_at: float | None      # 처음 기준(80 %)을 넘는 시각, 안 넘으면 None
    hours_over: float                # 기준 이상인 시간 합 [h]
    curve: list[tuple[float, float]]  # (epoch초, RHs)


def forecast_night(t_air: float, rh: float, f_rsi: float,
                   te_hourly: list[tuple[float, float]],
                   ta_hourly: list[tuple[float, float]] | None = None,
                   limit: float = RHS_LIMIT) -> NightForecast | None:
    """te_hourly: (epoch초, 외기 예보 °C), 시간순·등간격. ta_hourly를 주면 실내 온도도 시간별로 바꾼다
    (예: 난방 예약). 실내 수증기압은 현재값 유지."""
    if not te_hourly:
        return None
    e = rh / 100 * es(t_air)
    ta_at = dict(ta_hourly or [])
    curve = []
    for t, te in te_hourly:
        ta = ta_at.get(t, t_air)
        rhs = min(100.0, 100 * e / es(surface_temp(ta, te, f_rsi)))
        curve.append((t, rhs))

    step_h = (te_hourly[1][0] - te_hourly[0][0]) / 3600 if len(te_hourly) > 1 else 1.0
    max_t, max_v = max(curve, key=lambda p: p[1])
    over = [t for t, v in curve if v >= limit]
    return NightForecast(max_v, max_t, over[0] if over else None, len(over) * step_h, curve)
