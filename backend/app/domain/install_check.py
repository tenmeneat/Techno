"""설치 직후 자가 점검 (B-07). 순수함수만 — I/O 금지.

프로브 단열·위치를 사용자가 직접 처리하므로, 잘못 설치하면 '위험을 안전으로' 판정하는 가장 나쁜 오류가 난다.
설치 후 첫 몇 시간 데이터로 다음을 본다.
  1) 데이터가 충분한가
  2) 벽면온도가 실내온도와 구분되는가 — 프로브가 공기 중에 떠 있으면 Ts ≈ Ta
     외기온을 알면 더 엄격히: 겉보기 fRsi = (Ts−Te)/(Ta−Te)가 1에 가까우면 외벽 표면일 수 없다
  3) 값이 지나치게 흔들리지 않는가 — 접촉 불량·통풍 노출

★ 임계값은 11-26 파일럿 초기 데이터로 정한다. 지금 값은 잠정치이고 InstallCheckParams로만 바꾼다.
"""
import statistics
from dataclasses import dataclass, field

# 사유 코드 — 프런트 안내 문구와 연결되는 계약 값 (§11.4 승인 후 API 노출)
OK = "OK"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
PROBE_NOT_CONTACTING_WALL = "PROBE_NOT_CONTACTING_WALL"
PROBE_NOISY = "PROBE_NOISY"


@dataclass(frozen=True)
class InstallCheckParams:
    min_hours: float = 6.0             # 이보다 짧으면 판정 보류
    min_samples: int = 360             # 30초 주기 6시간의 반 (결측 허용)
    min_air_wall_gap: float = 0.5      # 평균 (Ta − Ts) [K]가 이보다 작으면 벽에서 떨어진 것으로 의심
    max_apparent_frsi: float = 0.97    # 외기온이 있을 때: 겉보기 fRsi가 이보다 크면 외벽 표면으로 보기 어려움
    min_te_gap_for_frsi: float = 5.0   # 실내외 온도차가 이보다 작으면 fRsi 검사 생략(분모가 작아 불안정)
    max_step_std: float = 0.3          # 30초 간격 벽면온도 변화량의 표준편차 [K]. 크면 흔들림


@dataclass(frozen=True)
class InstallCheckResult:
    status: str                         # 위 사유 코드 중 하나 (여러 문제면 가장 심각한 것)
    reasons: list[str] = field(default_factory=list)  # 걸린 사유 전부
    hours: float = 0.0
    n_samples: int = 0
    air_wall_gap: float | None = None   # 평균 Ta − Ts [K]
    apparent_frsi: float | None = None
    step_std: float | None = None


def install_check(samples: list[tuple[float, float, float]],
                  t_ext: float | None = None,
                  params: InstallCheckParams = InstallCheckParams()) -> InstallCheckResult:
    """samples: (epoch초, Ta, Ts), 시간순. t_ext: 같은 기간 평균 외기온(없으면 None)."""
    n = len(samples)
    hours = (samples[-1][0] - samples[0][0]) / 3600 if n >= 2 else 0.0
    if n < params.min_samples or hours < params.min_hours:
        return InstallCheckResult(INSUFFICIENT_DATA, [INSUFFICIENT_DATA], hours, n)

    ta = [s[1] for s in samples]
    ts = [s[2] for s in samples]
    gap = statistics.fmean(a - s for a, s in zip(ta, ts))
    steps = [b - a for a, b in zip(ts, ts[1:])]
    step_std = statistics.pstdev(steps) if len(steps) >= 2 else 0.0

    reasons: list[str] = []
    apparent = None
    if gap < params.min_air_wall_gap:
        reasons.append(PROBE_NOT_CONTACTING_WALL)
    if t_ext is not None:
        ta_m, ts_m = statistics.fmean(ta), statistics.fmean(ts)
        if ta_m - t_ext >= params.min_te_gap_for_frsi:
            apparent = (ts_m - t_ext) / (ta_m - t_ext)
            if apparent > params.max_apparent_frsi and PROBE_NOT_CONTACTING_WALL not in reasons:
                reasons.append(PROBE_NOT_CONTACTING_WALL)
    if step_std > params.max_step_std:
        reasons.append(PROBE_NOISY)

    status = reasons[0] if reasons else OK  # 벽 미접촉이 흔들림보다 심각 → 먼저 넣었으므로 첫 번째가 대표
    return InstallCheckResult(status, reasons, hours, n, gap, apparent, step_std)
