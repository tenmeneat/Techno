"""인공 결로 실험 분석 (B-08, 설계서 §12.2). 순수함수만 — I/O 금지.

검증 지표
  ① CONDENSING 판정 시각과 육안 결로 시각의 차이 [분]
  ② 육안 결로 시점의 (Ts − Td) 계산값 [K]  — 0에 가까울수록 센서·계산이 정확

readings 테이블의 t_dew·rh_surf는 샘플마다 계산한 값(보정 적용, 5분 중앙값·dwell 없음)이라 '원시'로 쓴다.
상태 전이(events)는 5분 중앙값 + dwell(CONDENSING 5분, ALERT 10분)을 거치므로, 원시 교차 시각과
전이 시각을 나란히 두면 필터 지연과 센서 오차를 분리해서 볼 수 있다.
"""
from dataclasses import asdict, dataclass, field

NEAREST_TOL_S = 90  # 육안 시각과 가장 가까운 샘플이 이보다 멀면 값 없음 처리


@dataclass(frozen=True)
class Row:
    t: float          # epoch초
    probe_id: str
    t_air: float
    rh: float
    t_surf: float
    t_dew: float
    rh_surf: float

    @property
    def ts_minus_td(self) -> float:
        return self.t_surf - self.t_dew


@dataclass(frozen=True)
class Event:
    state: str
    started: float          # epoch초
    ended: float | None


@dataclass
class ProbeResult:
    probe_id: str
    raw_first_80: float | None = None        # 원시 RHs가 처음 80 이상이 된 시각
    raw_first_100: float | None = None       # 원시 RHs가 처음 100(결로 조건)이 된 시각
    at_visual: dict = field(default_factory=dict)  # 육안 결로 시각별 {ts_minus_td, rh_surf, sample_t}


@dataclass
class ExperimentResult:
    window: tuple[float, float]
    meta: dict
    alert_at: float | None                   # 구간 내 첫 ALERT(또는 그 이상) 전이 시각
    condensing_at: float | None              # 구간 내 첫 CONDENSING 전이 시각
    visual: list[tuple[str, float]]          # (라벨, 육안 결로 시각)
    probes: list[ProbeResult]
    lags_min: dict                           # 비교 지표 [분], 양수 = 육안보다 늦음

    def to_dict(self) -> dict:
        return asdict(self)


def _first_at_or_above(rows: list[Row], key: str, thr: float) -> float | None:
    return next((r.t for r in rows if getattr(r, key) >= thr), None)


def _nearest(rows: list[Row], t: float, tol: float = NEAREST_TOL_S) -> Row | None:
    best = min(rows, key=lambda r: abs(r.t - t), default=None)
    return best if best is not None and abs(best.t - t) <= tol else None


def _mins(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else round((a - b) / 60, 1)


def analyze(rows: list[Row], events: list[Event], visual: list[tuple[str, float]],
            window: tuple[float, float], meta: dict | None = None) -> ExperimentResult:
    """rows·events는 이미 실험 구간·기기로 걸러진 것. visual: [(라벨, epoch초)], 실험자가 기록한 육안 결로 시각."""
    t0, t1 = window
    rows = sorted((r for r in rows if t0 <= r.t < t1), key=lambda r: r.t)
    by_probe: dict[str, list[Row]] = {}
    for r in rows:
        by_probe.setdefault(r.probe_id, []).append(r)

    probes = []
    for pid, rs in sorted(by_probe.items()):
        pr = ProbeResult(pid, _first_at_or_above(rs, "rh_surf", 80.0), _first_at_or_above(rs, "rh_surf", 100.0))
        for label, vt in visual:
            near = _nearest(rs, vt)
            pr.at_visual[label] = None if near is None else {
                "sample_t": near.t, "ts_minus_td": round(near.ts_minus_td, 2), "rh_surf": round(near.rh_surf, 1)}
        probes.append(pr)

    def first_event(states: set[str]) -> float | None:
        return min((e.started for e in events if e.state in states and t0 <= e.started < t1), default=None)

    alert_at = first_event({"ALERT", "CONDENSING"})
    condensing_at = first_event({"CONDENSING"})
    raw100 = min((p.raw_first_100 for p in probes if p.raw_first_100 is not None), default=None)
    raw80 = min((p.raw_first_80 for p in probes if p.raw_first_80 is not None), default=None)
    first_visual = min((vt for _, vt in visual), default=None)

    lags = {
        # ① 핵심 지표: 판정(경보)이 육안보다 몇 분 늦었나 (음수 = 먼저 경보)
        "condensing_vs_visual": _mins(condensing_at, first_visual),
        "alert_vs_visual": _mins(alert_at, first_visual),
        # 센서·계산 자체: 원시 RHs가 100에 닿은 시각 vs 육안
        "raw100_vs_visual": _mins(raw100, first_visual),
        # 필터 지연: 원시 교차 → 상태 전이 (중앙값·dwell 때문에 생기는 늦음)
        "filter_delay_condensing": _mins(condensing_at, raw100),
        "filter_delay_alert": _mins(alert_at, raw80),
    }
    return ExperimentResult(window, meta or {}, alert_at, condensing_at, list(visual), probes, lags)
