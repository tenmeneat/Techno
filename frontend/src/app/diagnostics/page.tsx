"use client";
// 진단 (§10.2): fRsi·TDR 추이, 일별 ALERT 누적 시간, 방 간 비교
import { useQueries, useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type Device, type Diagnostic } from "@/lib/api";
import { F_RSI_MIN, fmt, fRsiLabel } from "@/lib/format";

const COLORS = ["#1d4ed8", "#c2410c", "#7c3aed"];

export default function DiagnosticsPage() {
  const devices = useQuery({ queryKey: ["devices"], queryFn: () => api<Device[]>("/devices") }).data ?? [];
  const diags = useQueries({
    queries: devices.map((d) => ({
      queryKey: ["diagnostics", d.id],
      queryFn: () => api<Diagnostic[]>(`/devices/${d.id}/diagnostics?days=30`),
    })),
  });

  // day → { day, [device]: f_rsi, [device+"_alert"]: 시간 }
  const byDay = new Map<string, Record<string, number | string | null>>();
  devices.forEach((d, i) =>
    diags[i]?.data?.forEach((x) => {
      const row = byDay.get(x.day) ?? { day: x.day.slice(5) };
      row[d.id] = x.f_rsi;
      row[`${d.id}_alert`] = +(x.minutes_alert / 60).toFixed(1);
      byDay.set(x.day, row);
    }),
  );
  const data = [...byDay.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([, r]) => r);

  return (
    <div className="grid gap-4">
      <section className="rounded-2xl bg-white p-4 shadow-sm">
        <h2 className="font-semibold">단열 지표 fRsi (일간, 02–06시 중앙값)</h2>
        <p className="mb-2 text-xs text-gray-500">실내외 온도차 10K 미만인 날은 산출하지 않습니다. 기준선 0.70 = DIN 4108-2 · ISO 13788 관행.</p>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data} margin={{ left: -20, right: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="day" fontSize={11} />
            <YAxis domain={[0.5, 1]} fontSize={11} />
            <Tooltip />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <ReferenceLine y={F_RSI_MIN} stroke="#dc2626" strokeDasharray="4 3" />
            {devices.map((d, i) => (
              <Line key={d.id} dataKey={d.id} name={d.label ?? d.id} stroke={COLORS[i % 3]} connectNulls={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
        <ul className="mt-2 text-sm">
          {devices.map((d, i) => {
            const last = diags[i]?.data?.findLast((x) => x.f_rsi != null);
            return <li key={d.id}>{d.label ?? d.id}: {fmt(last?.f_rsi, 2)} (TDR {fmt(last?.tdr, 2)}) — {fRsiLabel(last?.f_rsi)}</li>;
          })}
        </ul>
      </section>

      <section className="rounded-2xl bg-white p-4 shadow-sm">
        <h2 className="mb-2 font-semibold">일별 곰팡이 위험(ALERT 이상) 누적 시간</h2>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={data} margin={{ left: -20, right: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="day" fontSize={11} />
            <YAxis unit="h" fontSize={11} />
            <Tooltip />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            {devices.map((d, i) => (
              <Bar key={d.id} dataKey={`${d.id}_alert`} name={d.label ?? d.id} fill={COLORS[i % 3]} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </section>
    </div>
  );
}
