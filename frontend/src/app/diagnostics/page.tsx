"use client";
// 진단 (§10.2): 방별 비교 카드 + fRsi 추이 + 일별 위험 시간
import { useQueries, useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type Device, type Diagnostic } from "@/lib/api";
import { F_RSI_MIN, fmt, fRsiLabel, fRsiMedian7, STATE } from "@/lib/format";

const COLORS = ["#2a78d6", "#eb6834", "#1baf7a"]; // 범주형 팔레트 고정 순서 (방마다 같은 색)
const AXIS = { fontSize: 11, stroke: "#94a3b8", tickLine: false, axisLine: false } as const;
const TOOLTIP = { borderRadius: 10, border: "1px solid #e2e8f0", fontSize: 12 };

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
      const row = byDay.get(x.day) ?? { day: x.day.slice(5).replace("-", "/") };
      row[d.id] = x.f_rsi;
      row[`${d.id}_alert`] = +(x.minutes_alert / 60).toFixed(1);
      byDay.set(x.day, row);
    }),
  );
  const data = [...byDay.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([, r]) => r);

  return (
    <div className="grid gap-6">
      <header>
        <h1 className="text-2xl font-bold tracking-tight md:text-3xl">단열 진단</h1>
        <p className="mt-1 text-sm text-slate-500">환기로는 바뀌지 않는 벽체 자체의 성질(온도계수 fRsi)과 곰팡이 위험 노출을 방끼리 비교합니다. 최근 30일.</p>
      </header>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {devices.map((d, i) => <RoomCard key={d.id} device={d} color={COLORS[i % 3]} days={diags[i]?.data ?? []} />)}
      </div>

      {!data.length ? (
        <p className="rounded-2xl bg-white p-6 text-sm text-slate-500 ring-1 ring-slate-200">
          아직 일간 진단 결과가 없습니다. 매일 07시에 전날 데이터로 계산됩니다.
        </p>
      ) : (
        <div className="grid gap-6 xl:grid-cols-2">
          <Card title="온도계수 fRsi 추이" sub="02–06시 중앙값 · 실내외 온도차 10K 미만인 날은 산출하지 않음 · 붉은 영역 = 기준 0.70 미달">
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={data} margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke="#e2e8f0" />
                <XAxis dataKey="day" minTickGap={24} {...AXIS} />
                <YAxis domain={[0.5, 1]} ticks={[0.5, 0.6, 0.7, 0.8, 0.9, 1]} {...AXIS} />
                <ReferenceArea y1={0.5} y2={F_RSI_MIN} fill={STATE.CONDENSING.color} fillOpacity={0.06} />
                <ReferenceLine y={F_RSI_MIN} stroke={STATE.CONDENSING.color} strokeDasharray="5 3"
                  label={{ value: "기준 0.70", position: "insideTopRight", fontSize: 11, fill: STATE.CONDENSING.color }} />
                <Tooltip contentStyle={TOOLTIP} formatter={(v) => (v == null ? "산출 안 함" : Number(v).toFixed(2))} />
                <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} iconType="plainline" />
                {devices.map((d, i) => (
                  <Line key={d.id} dataKey={d.id} name={d.label ?? d.id} stroke={COLORS[i % 3]} strokeWidth={2}
                    dot={{ r: 3, strokeWidth: 0, fill: COLORS[i % 3] }} activeDot={{ r: 5 }} connectNulls={false} isAnimationActive={false} />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </Card>

          <Card title="일별 곰팡이 위험 시간" sub="벽면 상대습도 80% 이상(곰팡이 위험·결로)에 머문 시간">
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={data} margin={{ top: 8, right: 12, left: -16, bottom: 0 }} barGap={2}>
                <CartesianGrid vertical={false} stroke="#e2e8f0" />
                <XAxis dataKey="day" minTickGap={24} {...AXIS} />
                <YAxis unit="h" allowDecimals={false} {...AXIS} />
                <Tooltip contentStyle={TOOLTIP} cursor={{ fill: "#f1f5f9" }} formatter={(v) => `${v}시간`} />
                <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
                {devices.map((d, i) => (
                  <Bar key={d.id} dataKey={`${d.id}_alert`} name={d.label ?? d.id} fill={COLORS[i % 3]} radius={[4, 4, 0, 0]} isAnimationActive={false} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </div>
      )}
    </div>
  );
}

function RoomCard({ device, color, days }: { device: Device; color: string; days: Diagnostic[] }) {
  const f = days.filter((x) => x.f_rsi != null).map((x) => x.f_rsi as number);
  const median7 = fRsiMedian7(days);
  const alertH = days.reduce((s, x) => s + x.minutes_alert, 0) / 60;
  const dose = days.reduce((s, x) => s + x.mould_dose, 0);
  const below = median7 != null && median7 < F_RSI_MIN;

  return (
    <section className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
      <div className="flex items-center gap-2">
        <span className="h-3 w-3 rounded-full" style={{ background: color }} />
        <h2 className="font-semibold">{device.label ?? device.id}</h2>
        <span className="text-xs text-slate-400">{device.location_tag}</span>
      </div>
      <div className="mt-4 flex items-end gap-2">
        <span className="text-4xl font-bold tabular-nums tracking-tight">{fmt(median7, 2)}</span>
        <span className="pb-1 text-sm text-slate-500">fRsi (7일 중앙값) · TDR {fmt(median7 == null ? null : 1 - median7, 2)}</span>
      </div>
      <p className={`mt-1 text-sm font-medium ${below ? "text-red-700" : "text-slate-600"}`}>{fRsiLabel(median7)}</p>
      <dl className="mt-4 grid grid-cols-3 gap-2 text-center">
        {[
          ["30일 위험 시간", `${alertH.toFixed(0)}h`],
          ["곰팡이 노출량", `${dose.toFixed(0)} %·h`],
          ["fRsi 산출일", `${f.length}/${days.length}일`],
        ].map(([k, v]) => (
          <div key={k} className="rounded-lg bg-slate-50 py-2">
            <dd className="font-semibold tabular-nums">{v}</dd>
            <dt className="text-[11px] text-slate-500">{k}</dt>
          </div>
        ))}
      </dl>
    </section>
  );
}

function Card({ title, sub, children }: { title: string; sub: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200 md:p-6">
      <h2 className="font-semibold">{title}</h2>
      <p className="mb-4 text-xs text-slate-500">{sub}</p>
      {children}
    </section>
  );
}
