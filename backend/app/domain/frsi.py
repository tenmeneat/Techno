"""fRsi 여러 날 누적비 (B-05, 설계서 §4.3 개정). 순수함수만 — I/O 금지.

기존: 02~06시 샘플마다 (Ts−Te)/(Ta−Te)를 구해 하루 중앙값.
문제: 벽은 열용량이 있어 야간 난방 off·외기 하강 때 Ts가 늦게 따라간다 → 비정상상태 편향이 샘플마다 같은 방향이라
      중앙값으로 지워지지 않는다.
개정: 최소 3일치를 모아 누적비 Σ(Ts−Te) / Σ(Ta−Te). 온도가 빠르게 변하는 구간은 뺀다.
      일별로 (Σ(Ts−Te), Σ(Ta−Te), n)만 저장해 두면 슬라이딩 누적이 가능하다(daily_diagnostics 컬럼 추가는 스키마 담당).
기존 규칙(실내외 온도차 D ≥ 10 K, 02~06시)은 유지한다.
"""
from dataclasses import dataclass

MIN_DT = 10.0            # §4.3 실내외 온도차 D ≥ 10 K
NIGHT_HOURS = range(2, 6)
MAX_RATE_K_PER_H = 0.5   # Ta·Ts 변화율이 이보다 크면 비정상상태로 보고 제외 (잠정치, 파일럿 데이터로 조정)
RATE_WINDOW_S = 3600     # 변화율을 재는 구간
MIN_DAYS = 3


@dataclass(frozen=True)
class DaySums:
    sum_ts_te: float
    sum_ta_te: float
    n_samples: int


@dataclass(frozen=True)
class Sample:
    t: float       # epoch초
    hour: int      # 현지(KST) 시
    t_air: float
    t_surf: float
    t_ext: float


def _rate(samples: list[Sample], i: int, attr: str) -> float:
    """i번째 샘플 직전 RATE_WINDOW_S 동안의 평균 변화율 [K/h]. 구간 시작 샘플이 없으면 0."""
    t0 = samples[i].t - RATE_WINDOW_S
    j = i
    while j > 0 and samples[j - 1].t >= t0:
        j -= 1
    dt = samples[i].t - samples[j].t
    return 0.0 if dt <= 0 else (getattr(samples[i], attr) - getattr(samples[j], attr)) / dt * 3600


def usable(samples: list[Sample], max_rate: float = MAX_RATE_K_PER_H) -> list[bool]:
    """각 샘플을 누적에 써도 되는가. samples는 시간순."""
    out = []
    for i, s in enumerate(samples):
        ok = (s.hour in NIGHT_HOURS and s.t_air - s.t_ext >= MIN_DT
              and abs(_rate(samples, i, "t_air")) <= max_rate
              and abs(_rate(samples, i, "t_surf")) <= max_rate)
        out.append(ok)
    return out


def day_sums(samples: list[Sample], max_rate: float = MAX_RATE_K_PER_H) -> DaySums:
    """하루치(또는 임의 구간) 샘플의 누적 합. 앞뒤 1시간 변화율을 보려면 전날 밤 샘플을 함께 넘겨도 된다."""
    st = sa = 0.0
    n = 0
    for s, ok in zip(samples, usable(samples, max_rate)):
        if ok:
            st += s.t_surf - s.t_ext
            sa += s.t_air - s.t_ext
            n += 1
    return DaySums(st, sa, n)


def cumulative_frsi(days: list[DaySums], min_days: int = MIN_DAYS, min_samples_per_day: int = 1) -> float | None:
    """여러 날 합으로 fRsi. 샘플이 있는 날이 min_days 미만이면 None(산출 조건 미달)."""
    valid = [d for d in days if d.n_samples >= min_samples_per_day and d.sum_ta_te > 0]
    if len(valid) < min_days:
        return None
    return sum(d.sum_ts_te for d in valid) / sum(d.sum_ta_te for d in valid)
