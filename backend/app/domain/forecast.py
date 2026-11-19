"""단기 예측 (§6) — RHs(t)에 OLS 직선 + 게이팅. 믿을 수 없으면 None."""
import math
from dataclasses import dataclass

WINDOW_S = 1800      # 최근 30분
MIN_SAMPLES = 50     # 유효 샘플 ≥ 50/60
MIN_R2 = 0.5
HORIZON_H = 2.0      # §6.4 시상수 근거

# 급상승(스파이크) 필터 (B-02): 샤워·요리 직후처럼 몇 분 만에 치솟는 습도는 곧 내려오므로 직선 외삽하지 않는다.
# 5분 이동중앙값이 5분 만에 SPIKE_JUMP 이상 오르면 스파이크로 본다(= 시간당 60 %p 이상의 순간 상승).
# 할 일 문서의 예시 '> 10 %p/h'를 그대로 쓰면 꾸준히 오르는 진짜 위험(예: 시간당 10 %p로 80 % 접근)까지
# 예보에서 빠지므로, 기울기가 아니라 '짧은 구간의 급격한 점프'로 정의했다. 값은 파일럿 데이터로 조정.
SPIKE_SPAN_S = 300
SPIKE_JUMP = 5.0     # %p


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
    if has_spike(pts):
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


def has_spike(pts: list[tuple[float, float]], span_s: float = SPIKE_SPAN_S, jump: float = SPIKE_JUMP) -> bool:
    """pts: (시각[h], RHs), 시간순. 5분 이동중앙값이 5분 만에 jump 이상 오르면 True."""
    span_h = span_s / 3600
    med = []
    for i, (x, _) in enumerate(pts):
        win = sorted(y for xx, y in pts[: i + 1] if x - xx < span_h)
        k = len(win)
        med.append((x, win[k // 2] if k % 2 else (win[k // 2 - 1] + win[k // 2]) / 2))
    j = 0
    for x, m in med:
        while med[j][0] < x - span_h:
            j += 1
        if m - min(mm for xx, mm in med[j:] if xx <= x) >= jump:
            return True
    return False
