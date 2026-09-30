"""도메인 단위테스트. `pytest` 또는 `python tests/test_domain.py`로 실행."""
import csv
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.domain.forecast import forecast
from app.domain.psychrometrics import dew_point, f_rsi, rh_surface, t80
from app.domain.risk_state import RiskMachine, State

VECTORS = Path(__file__).resolve().parents[2] / "test_vectors.csv"


def test_vectors():
    """§11.3 공유 테스트 벡터 — 펌웨어도 같은 파일로 검증."""
    for r in csv.DictReader(VECTORS.open()):
        ta, rh, ts = float(r["t_air"]), float(r["rh"]), float(r["t_surf"])
        assert abs(dew_point(ta, rh) - float(r["t_dew"])) <= 0.05, r
        assert abs(rh_surface(ta, rh, ts) - float(r["rh_surf"])) <= 1.0, r


def test_t80_table():
    """§3.2 표."""
    for ta, rh, want in [(15, 60, 10.60), (20, 40, 9.26), (20, 60, 15.43), (25, 60, 20.26)]:
        assert abs(t80(ta, rh) - want) <= 0.05, (ta, rh)


def test_f_rsi_gate():
    assert f_rsi(20, 15, 15) is None  # D=5K → 산출 안 함
    assert abs(f_rsi(20, 14, 0) - 0.7) < 1e-9


def test_state_machine():
    m, t = RiskMachine(), 0.0
    for _ in range(20):  # 81%를 0~570s → dwell 미달
        m.update(81, t)
        t += 30
    assert m.state == State.SAFE  # 스파이크는 경보로 안 간다
    m.update(81, t)  # 600s 경과 → WATCH를 건너뛰고 바로 ALERT
    assert m.state == State.ALERT
    m.update(78, t + 30)
    assert m.state == State.ALERT  # 히스테리시스: 77 이상이면 유지
    m.update(76, t + 60)
    assert m.state == State.WATCH
    m.update(50, t + 90)
    assert m.state == State.SAFE


def test_forecast_gating():
    random.seed(1)
    rising = [(i * 30.0, 60 + i * 0.25 + random.gauss(0, 0.3)) for i in range(60)]  # 30%p/h
    fc = forecast(rising)
    assert fc and fc.target == 80 and fc.hours_low <= fc.hours_high
    flat = [(i * 30.0, 60 + random.gauss(0, 2)) for i in range(60)]
    assert forecast(flat) is None
    assert forecast(rising[:40]) is None  # 유효 샘플 부족


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
