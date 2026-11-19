"""B-01·B-02·B-04·B-05·B-07 계산 함수와 B-08 실험 분석 테스트 — DB 없이 돈다.
`pytest` 또는 `python tests/test_analysis.py`.
"""
import math
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis.experiment import Event, Row, analyze
from app.domain import forecast as fc
from app.domain.frsi import DaySums, Sample, cumulative_frsi, day_sums
from app.domain.humidity_cap import es, humidity_cap, rh_max, surface_temp
from app.domain.install_check import (INSUFFICIENT_DATA, OK, PROBE_NOISY, PROBE_NOT_CONTACTING_WALL,
                                      InstallCheckParams, install_check)
from app.domain.night_forecast import forecast_night
from app.domain.psychrometrics import dew_point, rh_surface, t80
from app.domain.uncertainty import is_borderline, nominal_u_rhs, rhs_band, sensitivities, u_rhs

H = 3600


# ───────── B-01 실내 습도 상한 ─────────

def test_rh_max_table():
    """할 일 문서 표(Ta 20 °C, RH_c 80) 16칸을 소수 첫째 자리까지 재현."""
    table = {5: [56.9, 60.3, 66.3, 71.5], 0: [50.6, 54.7, 62.2, 68.9],
             -5: [44.9, 49.6, 58.4, 66.3], -10: [39.9, 44.9, 54.7, 63.8]}
    for te, row in table.items():
        for f, want in zip((0.64, 0.70, 0.80, 0.88), row):
            assert round(rh_max(20, te, f), 1) == want, (te, f, rh_max(20, te, f))


def test_rh_max_is_consistent_with_surface_rh():
    """상한 습도에서 벽면 표면습도가 정확히 80 %가 돼야 한다."""
    for ta, te, f in [(20, 0, 0.7), (22, -8, 0.8), (18, 3, 0.65)]:
        cap = rh_max(ta, te, f)
        assert abs(rh_surface(ta, cap, surface_temp(ta, te, f)) - 80) < 1e-9


def test_humidity_cap_missing_inputs():
    assert humidity_cap(20, None, 0.7) is None   # 외기 최저 없음
    assert humidity_cap(20, 0, None) is None     # fRsi 산출 안 된 날
    c = humidity_cap(20, 0, 0.7)
    assert c.rh_cap_pct == 54.7 and c.te_min_used == 0 and c.f_rsi_used == 0.7
    try:
        rh_max(20, 0, 1.5)
        assert False
    except ValueError:
        pass


# ───────── B-04 불확도 ─────────

def test_sensitivities_match_numeric_derivative():
    for ta, rh, ts in [(20, 60, 15), (22, 50, 14), (18, 70, 13)]:
        a, h, s = sensitivities(ta, rh, ts)
        e = 1e-5
        raw = lambda T, R, S: 100 * R / 100 * es(T) / es(S)
        assert abs(a - (raw(ta + e, rh, ts) - raw(ta - e, rh, ts)) / (2 * e)) < 1e-4
        assert abs(h - (raw(ta, rh + e, ts) - raw(ta, rh - e, ts)) / (2 * e)) < 1e-4
        assert abs(s - (raw(ta, rh, ts + e) - raw(ta, rh, ts - e)) / (2 * e)) < 1e-4


def test_sensitivity_values_in_docs():
    """기준 조건(20 °C·60 %·벽 15 °C)에서 ∂RHs/∂RH ≈ 1.37, 80 % 경계에서는 80/RH ≈ 1.33."""
    assert round(sensitivities(20, 60, 15)[1], 2) == 1.37
    assert round(sensitivities(20, 60, t80(20, 60))[1], 2) == 1.33


def test_nominal_uncertainty_matches_design():
    """설계서 §5.4의 ±4.5 %p와 같은 수준이어야 한다 (±4 %p와 ±4.5 %p 불일치 정리)."""
    assert 4.4 <= nominal_u_rhs() <= 4.8, nominal_u_rhs()
    assert abs(2 * 1.37 - sensitivities(20, 60, 15)[1] * 2) < 0.01  # 습도 ±2 %p → RHs 약 ±2.7 %p


def test_rhs_band_and_borderline():
    b = rhs_band(20, 60, 15)                   # RHs ≈ 82 → 기준 80이 범위 안
    assert b.borderline and b.lo < 80 < b.hi
    assert not rhs_band(20, 45, 15).borderline  # RHs ≈ 61 — 확실히 안전 쪽
    assert not rhs_band(20, 75, 13).borderline  # RHs 100 근처 — 확실히 위험 쪽
    assert rhs_band(20, 75, 13).hi == 100.0     # 100 넘게 표시하지 않음
    assert is_borderline(80.0, 0.1) and not is_borderline(85.0, 2.0)
    assert u_rhs(20, 60, 15, u_rh=5.0) > u_rhs(20, 60, 15)  # 고습·저온 사양(±5 %p)을 넣으면 커짐


# ───────── B-07 설치 직후 자가 점검 ─────────

def _install_samples(hours, ta=20.0, ts=15.0, noise=0.03, seed=1):
    rnd = random.Random(seed)
    return [(i * 30.0, ta + rnd.gauss(0, 0.05), ts + rnd.gauss(0, noise)) for i in range(int(hours * 120))]


def test_install_ok():
    r = install_check(_install_samples(8))
    assert r.status == OK and r.reasons == [] and r.air_wall_gap > 4


def test_install_insufficient_data():
    assert install_check(_install_samples(2)).status == INSUFFICIENT_DATA
    assert install_check([]).status == INSUFFICIENT_DATA


def test_install_probe_in_air():
    """프로브가 공기 중에 떠 있으면 벽면온도 ≈ 실내온도."""
    r = install_check(_install_samples(8, ts=19.8))
    assert r.status == PROBE_NOT_CONTACTING_WALL


def test_install_apparent_frsi_check():
    """실내외 차이 20 K인데 벽이 실내보다 0.55 K만 낮다 → 겉보기 fRsi 0.97 초과: 외벽 표면으로 보기 어려움."""
    s = _install_samples(8, ts=19.45)
    assert install_check(s).status == OK                  # 외기온 없으면 간격 기준(0.5 K)만으로는 통과
    assert install_check(s, t_ext=0.0).status == PROBE_NOT_CONTACTING_WALL
    assert install_check(_install_samples(8, ts=15.0), t_ext=0.0).status == OK  # fRsi 0.75 — 정상


def test_install_noisy_probe():
    r = install_check(_install_samples(8, noise=0.5))
    assert r.status == PROBE_NOISY
    # 기준값은 파라미터로만 바꾼다(파일럿 데이터로 조정 예정)
    assert install_check(_install_samples(8, noise=0.5), params=InstallCheckParams(max_step_std=2.0)).status == OK


# ───────── B-05 fRsi 누적비 ─────────

def _night(day, f=0.7, te=0.0, heater_off=False, tau_h=2.0):
    """01~07시 1분 간격. heater_off면 01시에 난방이 꺼져 Ta가 22→17로 2시간에 걸쳐 떨어지고,
    벽면은 시상수 tau_h로 늦게 따라간다(벽 열용량)."""
    out = []
    ts = te + f * (22 - te)
    for k in range(6 * 60):
        t = day * 86400 + H + k * 60
        hour = 1 + k // 60
        ta = 22.0 if not heater_off else max(17.0, 22.0 - 2.5 * (k / 60))
        eq = te + f * (ta - te)
        ts += (eq - ts) * (60 / (tau_h * H))
        out.append(Sample(t, hour, ta, ts, te))
    return out


def _old_daily_median(samples):
    """기존 방식: 02~06시, D ≥ 10 K 샘플별 비율의 중앙값."""
    v = [(s.t_surf - s.t_ext) / (s.t_air - s.t_ext) for s in samples if 2 <= s.hour < 6 and s.t_air - s.t_ext >= 10]
    return statistics.median(v)


def test_cumulative_frsi_steady_state_exact():
    days = [day_sums(_night(d)) for d in range(3)]
    assert abs(cumulative_frsi(days) - 0.7) < 1e-9


def test_cumulative_frsi_needs_three_days():
    days = [day_sums(_night(d)) for d in range(2)]
    assert cumulative_frsi(days) is None
    assert cumulative_frsi(days + [DaySums(0, 0, 0)]) is None  # 샘플 없는 날은 날짜 수에 안 침


def test_cumulative_frsi_reduces_transient_bias():
    """난방 off 밤에는 벽이 늦게 식어 Ts가 높게 남는다 → 기존 중앙값은 fRsi를 높게(단열이 좋게) 본다."""
    nights = [_night(d, heater_off=True) for d in range(3)]
    old = statistics.median(_old_daily_median(n) for n in nights)
    new = cumulative_frsi([day_sums(n) for n in nights])
    assert old - 0.7 > 0.03                 # 기존 방식은 편향이 눈에 띄게 큼
    assert abs(new - 0.7) < abs(old - 0.7)  # 누적비 + 변화율 제외가 더 정확


# ───────── B-02 밤사이 예보 + 급상승 필터 ─────────

def test_forecast_night_constant_outdoor_is_flat():
    te = [(i * H, 0.0) for i in range(8)]
    r = forecast_night(20, 50, 0.7, te)
    want = rh_surface(20, 50, surface_temp(20, 0, 0.7))
    assert all(abs(v - want) < 1e-9 for _, v in r.curve)
    assert r.first_over_at is None and r.hours_over == 0


def test_forecast_night_falling_outdoor():
    """외기가 밤새 5 °C → −5 °C로 떨어지면 표면습도가 계속 오르고 어느 시점에 80 %를 넘는다."""
    te = [(i * H, 5.0 - 10.0 * i / 7) for i in range(8)]
    r = forecast_night(20, 52, 0.7, te)
    vals = [v for _, v in r.curve]
    assert vals == sorted(vals)
    assert r.max_at == 7 * H and r.first_over_at is not None and r.hours_over >= 1
    # 80 %를 처음 넘는 시각은 그 시각 외기에서의 습도 상한이 52 % 아래로 내려가는 시점과 같다
    t_first = r.first_over_at
    te_first = dict(te)[t_first]
    assert rh_max(20, te_first, 0.7) <= 52
    assert forecast_night(20, 52, 0.7, []) is None


def test_spike_filter_blocks_shower():
    """샤워 직후: 25분 평탄 뒤 3분 만에 RHs가 15 %p 치솟음 → 직선 외삽하지 않는다."""
    rnd = random.Random(3)
    pts = [(i * 30.0, 62 + rnd.gauss(0, 0.3)) for i in range(50)]
    pts += [(1500 + i * 30.0, 62 + min(15, 2.5 * (i + 1)) + rnd.gauss(0, 0.3)) for i in range(10)]
    assert fc.has_spike([((t - pts[-1][0]) / H, y) for t, y in pts])
    assert fc.forecast(pts) is None


def test_spike_filter_keeps_steady_rise():
    """꾸준한 상승(시간당 30 %p, 기존 test_domain의 예측 시나리오)은 스파이크가 아니다."""
    rnd = random.Random(1)
    rising = [(i * 30.0, 60 + i * 0.25 + rnd.gauss(0, 0.3)) for i in range(60)]
    assert not fc.has_spike([((t - rising[-1][0]) / H, y) for t, y in rising])
    assert fc.forecast(rising) is not None


# ───────── B-08 인공 결로 실험 분석 ─────────

def _ramp_rows(t0, minutes, probe="p0"):
    """실내 20 °C·60 %, 벽면을 분당 0.1 K씩 냉각(16 → ...). 이슬점은 약 12.0 °C."""
    rows = []
    for k in range(minutes * 2):
        t = t0 + k * 30
        ts = 16.0 - 0.1 * (k / 2)
        rows.append(Row(t, probe, 20.0, 60.0, ts, dew_point(20, 60), rh_surface(20, 60, ts)))
    return rows


def test_experiment_analysis():
    t0 = 1_800_000_000
    rows = _ramp_rows(t0, 60)
    td = dew_point(20, 60)
    t_cross = t0 + (16.0 - td) / 0.1 * 60           # 원시 RHs가 100이 되는 시각(벽면 = 이슬점)
    visual = [("1차", t_cross + 120)]               # 육안 결로는 2분 뒤 확인
    events = [Event("ALERT", t0 + 900, t0 + 1600), Event("CONDENSING", t_cross + 420, None)]
    r = analyze(rows, events, visual, (t0, t0 + 3600), {"cooling": "아이스팩", "ramp": "0.1K/min"})

    p = r.probes[0]
    assert abs(p.raw_first_100 - t_cross) <= 30
    assert abs(p.at_visual["1차"]["ts_minus_td"] - (-0.2)) <= 0.06  # 2분 뒤라 벽이 이슬점보다 0.2 K 낮음
    assert r.lags_min["condensing_vs_visual"] == 5.0                 # 판정이 육안보다 5분 늦음
    assert abs(r.lags_min["filter_delay_condensing"] - 7.0) <= 0.5    # 원시 교차 → 전이: 필터 지연 약 7분
    assert r.meta["cooling"] == "아이스팩"
    assert r.condensing_at == t_cross + 420 and r.alert_at == t0 + 900


def test_experiment_analysis_no_sample_near_visual():
    t0 = 1_800_000_000
    r = analyze(_ramp_rows(t0, 10), [], [("1차", t0 + 7200)], (t0, t0 + 3 * H))
    assert r.probes[0].at_visual["1차"] is None
    assert r.lags_min["condensing_vs_visual"] is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
