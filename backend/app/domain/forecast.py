"""단기 예측 (§6) — RHs(t)에 OLS 직선 + 게이팅. 믿을 수 없으면 None."""
import math
from dataclasses import dataclass

WINDOW_S = 1800      # 최근 30분
MIN_SAMPLES = 50     # 유효 샘플 ≥ 50/60
MIN_R2 = 0.5
HORIZON_H = 2.0      # §6.4 시상수 근거


@dataclass(frozen=True)
class Forecast:
    target: float      # 도달 예상 임계 RHs (80 또는 100)
    hours_low: float   # b1 + 2SE 기준 (빠른 쪽)
    hours_high: float  # b1 − 2SE 기준 (느린 쪽)
    slope: float       # %p/h
    r2: float


def forecast(samples: list[tuple[float, float]]) -> Forecast | None:
    """samples: (epoch초, RHs), 시간순."""
    if not samples:
        return None
    t_end = samples[-1][0]
    pts = [((t - t_end) / 3600, y) for t, y in samples if t_end - t <= WINDOW_S]
    n = len(pts)
    if n < MIN_SAMPLES:
        return None

    mx = sum(x for x, _ in pts) / n
    my = sum(y for _, y in pts) / n
    sxx = sum((x - mx) ** 2 for x, _ in pts)
    sst = sum((y - my) ** 2 for _, y in pts)
    if sxx == 0 or sst == 0:
        return None
    b1 = sum((x - mx) * (y - my) for x, y in pts) / sxx
    b0 = my - b1 * mx  # x=0(최신 시각)에서의 적합값
    sse = sum((y - b0 - b1 * x) ** 2 for x, y in pts)
    r2 = 1 - sse / sst
    se = math.sqrt(sse / (n - 2) / sxx)

    # 게이팅 (§6.3): 상승 추세, 유의성, 적합도
    if not (b1 > 0 and b1 > 2 * se and r2 >= MIN_R2) or b0 >= 100:
        return None
    target = 80.0 if b0 < 80 else 100.0
    gap = target - b0
    if gap / b1 > HORIZON_H:
        return None
    return Forecast(target, gap / (b1 + 2 * se), gap / (b1 - 2 * se), b1, r2)
