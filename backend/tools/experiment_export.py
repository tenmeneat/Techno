"""인공 결로 실험 데이터 추출·분석 (B-08).

필터(5분 중앙값·dwell)를 거치지 않은 원시 Ts·Td·RHs 시계열을 실험 구간만 CSV로 뽑고,
육안 결로 시각을 넣으면 그 시점의 (Ts − Td)와 상태 전이 시각을 나란히 출력한다.

  cd backend
  python tools/experiment_export.py --device dev-a --from 2026-11-27T20:00+09:00 --to 2026-11-27T23:00+09:00 \
      --visual "1차=2026-11-27T21:35+09:00" --meta cooling=아이스팩 --meta ramp=0.3K/min --out exp1

결과: <out>/raw.csv, <out>/events.csv, <out>/summary.json (+ 화면에 요약)
DB 접속은 서버와 같은 DATABASE_URL 환경변수를 쓴다. 읽기만 한다.
"""
import argparse
import asyncio
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis.experiment import Event, Row, analyze  # noqa: E402

KST = ZoneInfo("Asia/Seoul")


def _ts(s: str) -> float:
    d = datetime.fromisoformat(s)
    return (d if d.tzinfo else d.replace(tzinfo=KST)).timestamp()


def _kst(t: float | None) -> str:
    return "" if t is None else datetime.fromtimestamp(t, KST).strftime("%Y-%m-%d %H:%M:%S")


def parse_visual(items: list[str]) -> list[tuple[str, float]]:
    out = []
    for i, it in enumerate(items, 1):
        label, _, when = it.rpartition("=") if "=" in it else (f"{i}차", "", it)
        out.append((label or f"{i}차", _ts(when)))
    return out


def parse_meta(items: list[str]) -> dict:
    return dict(it.split("=", 1) for it in items)


async def fetch(device: str, t0: float, t1: float) -> tuple[list[Row], list[Event]]:
    import asyncpg
    con = await asyncpg.connect(os.getenv("DATABASE_URL", "postgresql://dg:dg@localhost:5432/dg"))
    try:
        a, b = datetime.fromtimestamp(t0, KST), datetime.fromtimestamp(t1, KST)
        rows = await con.fetch(
            """SELECT time, probe_id, t_air, rh, t_surf, t_dew, rh_surf FROM readings
               WHERE device_id = $1 AND time >= $2 AND time < $3 ORDER BY time, probe_id""", device, a, b)
        evs = await con.fetch(
            """SELECT state, started_at, ended_at FROM events
               WHERE device_id = $1 AND started_at < $3 AND coalesce(ended_at, now()) > $2 ORDER BY started_at""",
            device, a, b)
    finally:
        await con.close()
    return ([Row(r["time"].timestamp(), r["probe_id"], r["t_air"], r["rh"], r["t_surf"], r["t_dew"], r["rh_surf"])
             for r in rows],
            [Event(e["state"], e["started_at"].timestamp(), e["ended_at"] and e["ended_at"].timestamp())
             for e in evs])


def write_outputs(out: Path, rows: list[Row], events: list[Event], result) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "raw.csv", "w", newline="", encoding="utf-8-sig") as f:  # 엑셀에서 한글이 안 깨지게 BOM
        w = csv.writer(f)
        w.writerow(["time_kst", "probe_id", "t_air", "rh", "t_surf", "t_dew", "ts_minus_td", "rh_surf"])
        for r in sorted(rows, key=lambda r: (r.t, r.probe_id)):
            w.writerow([_kst(r.t), r.probe_id, r.t_air, r.rh, r.t_surf, round(r.t_dew, 3),
                        round(r.ts_minus_td, 3), round(r.rh_surf, 2)])
    with open(out / "events.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["state", "started_kst", "ended_kst"])
        for e in events:
            w.writerow([e.state, _kst(e.started), _kst(e.ended)])
    d = result.to_dict()
    d["kst"] = {"alert_at": _kst(result.alert_at), "condensing_at": _kst(result.condensing_at),
                "visual": {lbl: _kst(t) for lbl, t in result.visual}}
    (out / "summary.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def summary_text(result) -> str:
    lines = [f"구간 {_kst(result.window[0])} ~ {_kst(result.window[1])}",
             f"실험 조건: {result.meta or '(없음)'}",
             f"첫 ALERT 전이: {_kst(result.alert_at) or '없음'} / 첫 CONDENSING 전이: {_kst(result.condensing_at) or '없음'}"]
    for p in result.probes:
        lines.append(f"[{p.probe_id}] 원시 RHs≥80 {_kst(p.raw_first_80) or '없음'}, ≥100 {_kst(p.raw_first_100) or '없음'}")
        for lbl, v in p.at_visual.items():
            lines.append(f"   육안 {lbl}: " + ("근처 샘플 없음" if v is None else
                                            f"Ts−Td = {v['ts_minus_td']} K, RHs = {v['rh_surf']} %"))
    lines.append("지연 [분, 양수=육안보다 늦음]: " + ", ".join(f"{k}={v}" for k, v in result.lags_min.items()))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--device", required=True)
    ap.add_argument("--from", dest="t_from", required=True, help="실험 시작 (ISO, 시간대 없으면 KST)")
    ap.add_argument("--to", dest="t_to", required=True)
    ap.add_argument("--visual", action="append", default=[], help="육안 결로 시각. '라벨=ISO' 또는 'ISO', 여러 번 가능")
    ap.add_argument("--meta", action="append", default=[], help="실험 조건 key=value (냉각 방식, 램프 속도 등)")
    ap.add_argument("--out", default="experiment_out")
    a = ap.parse_args(argv)

    window = (_ts(a.t_from), _ts(a.t_to))
    rows, events = asyncio.run(fetch(a.device, *window))
    result = analyze(rows, events, parse_visual(a.visual), window, parse_meta(a.meta))
    write_outputs(Path(a.out), rows, events, result)
    print(summary_text(result))
    print(f"\n저장: {Path(a.out).resolve()}")


if __name__ == "__main__":
    main()
