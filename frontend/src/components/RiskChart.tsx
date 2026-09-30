"use client";
// §10.3 핵심 차트: Ts / Td / T80 을 한 온도축에. Td 아래는 위험색, Td–T80 사이는 경고색.
// Ts 선이 어느 띠에 들어와 있는지가 곧 상태다.
import { Area, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Event, ProbeReading } from "@/lib/api";
import { hhmm, STATE } from "@/lib/format";

type Row = { t: number; td: number; t80: number; [probe: string]: number };
const PROBE_COLORS = ["#1d4ed8", "#7c3aed", "#0891b2"];

export function RiskChart({ series, events, from, to }: {
  series: ProbeReading[]; events: Event[]; from: number; to: number;
}) {
  const rows = new Map<number, Row>();
  const probes = new Set<string>();
  for (const p of series) {
    const t = new Date(p.time).getTime();
    const r = rows.get(t) ?? { t, td: p.t_dew, t80: p.t80 };
    r[p.probe_id] = p.t_surf;
    rows.set(t, r);
    probes.add(p.probe_id);
  }
  const data = [...rows.values()].sort((a, b) => a.t - b.t);
  to = Math.max(to, data.at(-1)?.t ?? to); // WS로 붙는 새 점이 잘리지 않게
  const yMin = Math.floor(Math.min(...series.map((p) => Math.min(p.t_dew, p.t_surf)), 99)) - 1;

  return (
    <div>
      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey="t" type="number" scale="time" domain={[from, to]} tickFormatter={hhmm} minTickGap={40} fontSize={11} />
          <YAxis unit="°" domain={[yMin, "auto"]} fontSize={11} allowDecimals={false} />
          <Tooltip labelFormatter={(t) => hhmm(t as number)} formatter={(v) => (Array.isArray(v) ? null : `${Number(v).toFixed(1)}°C`)} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Area dataKey={(r: Row) => [yMin, r.td]} name="결로 구간" fill="#fecaca" stroke="none" isAnimationActive={false} legendType="none" />
          <Area dataKey={(r: Row) => [r.td, r.t80]} name="곰팡이 구간" fill="#fed7aa" stroke="none" isAnimationActive={false} legendType="none" />
          <Line dataKey="t80" name="T80 (곰팡이 임계)" stroke="#fb923c" strokeWidth={1} dot={false} isAnimationActive={false} />
          <Line dataKey="td" name="Td (이슬점)" stroke="#dc2626" strokeDasharray="5 3" dot={false} isAnimationActive={false} />
          {[...probes].map((p, i) => (
            <Line key={p} dataKey={p} name={`Ts ${p.slice(-4)}`} stroke={PROBE_COLORS[i % 3]} strokeWidth={2} dot={false} isAnimationActive={false} />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
      {/* 상태 이벤트는 선 위가 아니라 x축 아래 띠로 */}
      <div className="relative ml-[44px] mr-2 h-3 rounded bg-emerald-100">
        {events.map((e) => {
          const s = Math.max(from, new Date(e.started_at).getTime());
          const end = Math.min(to, e.ended_at ? new Date(e.ended_at).getTime() : to);
          return (
            <div key={e.id} title={`${STATE[e.state].label} ${hhmm(s)}`} className="absolute h-full"
              style={{ left: `${((s - from) / (to - from)) * 100}%`, width: `${((end - s) / (to - from)) * 100}%`, background: STATE[e.state].color }} />
          );
        })}
      </div>
    </div>
  );
}
