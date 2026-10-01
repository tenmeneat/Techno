"use client";
// §10.3 핵심 차트: Ts / Td / T80 을 한 온도축에. Td 아래는 결로 띠, Td–T80 사이는 곰팡이 띠.
// Ts 선이 어느 띠에 들어와 있는지가 곧 상태다.
import { Area, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Event, ProbeReading } from "@/lib/api";
import { hhmm, STATE } from "@/lib/format";

type Row = { t: number; td: number; t80: number; [probe: string]: number };
const PROBE_COLORS = ["#2a78d6", "#4a3aa7"]; // 벽면 프로브 (상태색과 겹치지 않는 계열)
const CRIT = STATE.CONDENSING.color;
const SERIOUS = STATE.ALERT.color;

export function RiskChart({ series, events, from, to, height = 300 }: {
  series: ProbeReading[]; events: Event[]; from: number; to: number; height?: number;
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
  from = Math.max(from, data[0]?.t ?? from); // 데이터가 있는 구간부터 (설치 직후에 축이 텅 비지 않게)
  const yMin = Math.floor(Math.min(...series.map((p) => Math.min(p.t_dew, p.t_surf)), 99)) - 1;

  if (!series.length) {
    return <div className="grid place-items-center text-sm text-slate-400" style={{ height }}>이 기간에는 측정 데이터가 없습니다</div>;
  }
  return (
    <div>
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={data} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="#e2e8f0" />
          <XAxis dataKey="t" type="number" scale="time" domain={[from, to]} tickFormatter={hhmm} minTickGap={60}
            fontSize={11} stroke="#94a3b8" tickLine={false} axisLine={false} />
          <YAxis unit="°" domain={[yMin, "auto"]} fontSize={11} stroke="#94a3b8" allowDecimals={false} tickLine={false} axisLine={false} />
          <Tooltip labelFormatter={(t) => hhmm(t as number)}
            formatter={(v) => (Array.isArray(v) ? null : `${Number(v).toFixed(1)}°C`)}
            contentStyle={{ borderRadius: 10, border: "1px solid #e2e8f0", fontSize: 12 }} />
          <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} iconType="plainline" />
          <Area dataKey={(r: Row) => [yMin, r.td]} name="결로 구간" fill={CRIT} fillOpacity={0.07} stroke="none" isAnimationActive={false} legendType="none" />
          <Area dataKey={(r: Row) => [r.td, r.t80]} name="곰팡이 구간" fill={SERIOUS} fillOpacity={0.2} stroke="none" isAnimationActive={false} legendType="none" />
          <Line dataKey="t80" name="T80 곰팡이 임계" stroke={SERIOUS} strokeWidth={1.5} dot={false} isAnimationActive={false} />
          <Line dataKey="td" name="Td 이슬점" stroke={CRIT} strokeWidth={1.5} strokeDasharray="5 3" dot={false} isAnimationActive={false} />
          {[...probes].map((p, i) => (
            <Line key={p} dataKey={p} name={`벽면 ${i + 1}`} stroke={PROBE_COLORS[i % 2]} strokeWidth={2} dot={false} isAnimationActive={false} />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
      {/* 상태 이벤트는 선 위가 아니라 x축 아래 띠로 */}
      <div className="relative ml-[48px] mr-3 mt-1 h-2.5 overflow-hidden rounded-full bg-slate-100">
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
