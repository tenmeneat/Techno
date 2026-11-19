"""실내 습도 상한 (B-01). 순수함수만 — I/O 금지.

"오늘 밤 이 벽이 버티는 실내 습도 상한"을 계산한다. 외기가 Te_min까지 내려갈 때 벽면은
    Ts_min = Te_min + fRsi · (Ta − Te_min)
이 되고, 그때 벽면 표면습도가 RH_c(곰팡이 기준 80 %)를 넘지 않으려면 실내 습도는
    RH_max = RH_c · es(Ts_min) / es(Ta)
이하여야 한다. (es: Magnus, psychrometrics와 같은 계수)
"""
import math
from dataclasses import dataclass

from app.domain.psychrometrics import A, B, C


def es(t: float) -> float:
    """포화수증기압 [hPa]."""
    return A * math.exp(B * t / (C + t))


def surface_temp(t_air: float, t_ext: float, f_rsi: float) -> float:
    """온도계수 정의를 뒤집은 것: Ts = Te + fRsi·(Ta − Te)."""
    return t_ext + f_rsi * (t_air - t_ext)


def rh_max(t_air: float, t_ext_min: float, f_rsi: float, rh_c: float = 80.0) -> float:
    """벽면 표면습도가 rh_c를 넘지 않는 실내 상대습도 상한 [%]."""
    if not 0 < f_rsi <= 1:
        raise ValueError(f"fRsi는 0~1: {f_rsi}")
    return rh_c * es(surface_temp(t_air, t_ext_min, f_rsi)) / es(t_air)


@dataclass(frozen=True)
class HumidityCap:
    rh_cap_pct: float    # 실내 습도 상한
    te_min_used: float   # 계산에 쓴 외기 최저
    f_rsi_used: float    # 계산에 쓴 fRsi


def humidity_cap(t_air: float, t_ext_min: float | None, f_rsi: float | None,
                 rh_c: float = 80.0) -> HumidityCap | None:
    """API용 묶음. fRsi나 외기 최저가 없으면 None (산출 안 함).

    fRsi 없는 날(가을·봄, D < 10 K)에 마지막 유효값을 쓸지 null로 둘지는 팀 결정 사항(결정 필요 #2)이라
    여기서는 호출 측이 넘긴 값만 쓴다.
    """
    if t_ext_min is None or f_rsi is None:
        return None
    return HumidityCap(round(rh_max(t_air, t_ext_min, f_rsi, rh_c), 1), t_ext_min, f_rsi)
