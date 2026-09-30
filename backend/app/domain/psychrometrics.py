"""습공기 계산 (§2–§4). 순수함수만 — I/O 금지.

Magnus 근사식, Sonntag(1990) 계수. 펌웨어(OLED용 복제)와 test_vectors.csv로 일치 검증(§11.3).
"""
import math

A, B, C = 6.112, 17.62, 243.12  # hPa, -, °C
F_RSI_MIN_DT = 10.0  # §4.3 실내외 온도차 D ≥ 10K 일 때만 fRsi 산출


def clamp_inputs(t_air: float, rh: float, t_surf: float) -> tuple[float, float, float, bool]:
    """§2.5 방어 처리. RH>100은 100으로 자르고 saturated 플래그를 돌려준다."""
    saturated = rh > 100
    clip = lambda v, lo, hi: max(lo, min(hi, v))
    return clip(t_air, -40, 80), clip(rh, 1, 100), clip(t_surf, -40, 80), saturated


def alpha(t_air: float, rh: float) -> float:
    """α = ln(e/6.112) — 수증기압의 로그 형태(§2.2)."""
    return math.log(rh / 100) + B * t_air / (C + t_air)


def t_crit(t_air: float, rh: float, rh_crit: float = 100.0) -> float:
    """표면습도가 rh_crit에 도달하는 벽면온도(§3.1). rh_crit=100이면 이슬점."""
    beta = alpha(t_air, rh) - math.log(rh_crit / 100)
    return C * beta / (B - beta)


def dew_point(t_air: float, rh: float) -> float:
    return t_crit(t_air, rh, 100)


def t80(t_air: float, rh: float) -> float:
    return t_crit(t_air, rh, 80)


def rh_surface(t_air: float, rh: float, t_surf: float) -> float:
    """벽면 상대습도 RHs(§2.3). 100 초과(=결로)는 100으로 자른다."""
    return min(100.0, 100 * math.exp(alpha(t_air, rh) - B * t_surf / (C + t_surf)))


def f_rsi(t_air: float, t_surf: float, t_ext: float) -> float | None:
    """온도계수(§4.1). 분모가 작으면 불확도가 폭발하므로 None(§4.3)."""
    d = t_air - t_ext
    return None if d < F_RSI_MIN_DT else (t_surf - t_ext) / d
