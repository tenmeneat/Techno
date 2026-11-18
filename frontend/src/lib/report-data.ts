import type { ProbeReading } from "./api";

const DAY = 86400_000;
export const koreaDay = (time = Date.now()) => new Date(time + 9 * 3600_000).toISOString().slice(0, 10);
export type ReportPeriod = { from: string; to: string };
export type ReportRow = { date: string; probe: string; air: number | null; humidity: number | null; wall: number | null; count: number };

/** Calendar-day presets include today, independent of the device's time zone. */
export function quickPeriod(days: 1 | 7 | 30, now = Date.now()): ReportPeriod {
  return { from: koreaDay(now - (days - 1) * DAY), to: koreaDay(now) };
}

/** These extrema describe received hourly aggregates, not raw sensor readings. */
export function hourlyStats(values: (number | null | undefined)[]) {
  const valid = values.filter((value): value is number => value != null && Number.isFinite(value));
  return {
    mean: average(valid),
    min: valid.length ? Math.min(...valid) : null,
    max: valid.length ? Math.max(...valid) : null,
  };
}

export function periodBounds(period: ReportPeriod) {
  const from = new Date(`${period.from}T00:00:00+09:00`).getTime();
  const to = new Date(`${period.to}T00:00:00+09:00`).getTime() + DAY;
  return { from, to };
}

export function periodError(period: ReportPeriod) {
  if (!period.from || !period.to) return "시작일과 종료일을 모두 선택해 주세요.";
  const { from, to } = periodBounds(period);
  if (!Number.isFinite(from) || !Number.isFinite(to)) return "올바른 날짜를 선택해 주세요.";
  if (from >= to) return "종료일은 시작일보다 빠를 수 없어요.";
  if (period.to > koreaDay()) return "오늘 이후의 날짜는 조회할 수 없어요.";
  if (to - from > DAY * 366) return "한 번에 최대 366일까지 조회할 수 있어요.";
  return "";
}

export function average(values: (number | null | undefined)[]) {
  const valid = values.filter((x): x is number => x != null && Number.isFinite(x));
  return valid.length ? valid.reduce((sum, x) => sum + x, 0) / valid.length : null;
}

// The API day bucket is UTC. Group hour aggregates by Korean calendar day here.
export function reportRows(series: ProbeReading[], period: ReportPeriod, daily: boolean): ReportRow[] {
  const { from, to } = periodBounds(period);
  const readings = series.filter(p => { const time = Date.parse(p.time); return time >= from && time < to; });
  const groups = new Map<string, { date: string; probe: string; readings: ProbeReading[] }>();
  if (daily) {
    const probes = [...new Set(readings.map(p => p.probe_id))].sort();
    for (let t = from; t < to; t += DAY) for (const probe of probes) {
      const date = koreaDay(t);
      groups.set(`${date}/${probe}`, { date, probe, readings: [] });
    }
  }
  for (const p of readings) {
    const date = daily ? koreaDay(Date.parse(p.time)) : p.time;
    const key = `${date}/${p.probe_id}`;
    const group = groups.get(key) ?? { date, probe: p.probe_id, readings: [] };
    group.readings.push(p);
    groups.set(key, group);
  }
  return [...groups.values()].map(g => ({
    date: g.date, probe: g.probe, count: g.readings.length,
    air: average(g.readings.map(p => p.t_air)), humidity: average(g.readings.map(p => p.rh)), wall: average(g.readings.map(p => p.t_surf)),
  })).sort((a, b) => a.date.localeCompare(b.date) || a.probe.localeCompare(b.probe));
}

export function sampleReport(period: ReportPeriod): ProbeReading[] {
  const { from, to } = periodBounds(period);
  const readings: ProbeReading[] = [];
  for (let t = from, i = 0; t < Math.min(to, Date.now()); t += 3600_000, i++) {
    const wave = Math.sin(i / 4);
    readings.push({ time: new Date(t).toISOString(), probe_id: "창가 벽면", t_air: 22.4 + wave * 1.1, rh: 52 + Math.cos(i / 5) * 5, t_surf: 18.2 + wave * 1.6, t_dew: 12.1, t80: 16, rh_surf: 65 });
  }
  return readings;
}
