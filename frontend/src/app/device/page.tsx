"use client";
// 상세 차트 (§10.2): Ts / Td / T80 3선 + 위험 밴드, 24h / 7d / 30d
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { RiskChart } from "@/components/RiskChart";
import { StateBadge } from "@/components/StateBadge";
import { api, type Current, type Event, type ProbeReading, RANGES, type RangeKey, rangeParams } from "@/lib/api";
import { fmt, hhmm, STATE } from "@/lib/format";
import { useLive } from "@/lib/live";

// 정적 export라 동적 경로 대신 /device/?id=... (useSearchParams는 Suspense 안에서만)
export default function DevicePage() {
  return <Suspense><DeviceView /></Suspense>;
}

function DeviceView() {
  const id = useSearchParams().get("id") ?? "";
  const [range, setRange] = useState<RangeKey>("24h");
  useLive(id);

  // 기간 경계는 range가 바뀔 때만 다시 잡는다
  const { from, to, qs } = useMemo(() => rangeParams(range), [range]);

  const cur = useQuery({ queryKey: ["current", id], queryFn: () => api<Current>(`/devices/${id}/current`) });
  const series = useQuery({
    queryKey: ["series", id, range],
    queryFn: () => api<ProbeReading[]>(`/devices/${id}/series?${qs}&bucket=${RANGES[range].bucket}`),
  });
  const events = useQuery({ queryKey: ["events", id, range], queryFn: () => api<Event[]>(`/devices/${id}/events?${qs}`) });

  const worst = cur.data?.probes.reduce((a, b) => (b.rh_surf > a.rh_surf ? b : a), cur.data.probes[0]);
  const list = (events.data ?? []).filter((e) => e.state !== "STALE").slice().reverse();

  return (
    <div className="grid gap-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link href="/" className="text-sm text-slate-500 hover:text-slate-800">← 실시간 현황</Link>
          <h1 className="mt-1 text-2xl font-bold tracking-tight md:text-3xl">{id}</h1>
        </div>
        {cur.data && <StateBadge state={cur.data.state} large />}
      </header>

      <div className="grid gap-6 xl:grid-cols-3">
        <section className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200 md:p-6 xl:col-span-2">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="font-semibold">벽면 온도와 위험 띠</h2>
              <p className="text-xs text-slate-500">벽면 선이 주황 띠에 들어가면 곰팡이 위험, 빨간 띠면 결로</p>
            </div>
            <div className="inline-flex rounded-lg bg-slate-100 p-1">
              {(Object.keys(RANGES) as RangeKey[]).map((r) => (
                <button key={r} onClick={() => setRange(r)}
                  className={`rounded-md px-3 py-1 text-sm font-medium ${r === range ? "bg-white text-slate-900 shadow-sm" : "text-slate-500"}`}>{r}</button>
              ))}
            </div>
          </div>
          {series.data
            ? <RiskChart series={series.data} events={events.data ?? []} from={from} to={to} height={420} />
            : <div className="h-[420px] animate-pulse rounded-xl bg-slate-50" />}
        </section>

        <div className="grid content-start gap-6">
          <section className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
            <h2 className="mb-3 font-semibold">지금</h2>
            <dl className="grid grid-cols-2 gap-3 text-sm">
              {[
                ["벽면 상대습도", fmt(worst?.rh_surf, 0), "%"],
                ["결로 여유", worst ? fmt(worst.t_surf - worst.t_dew) : "—", "K"],
                ["실내", `${fmt(worst?.t_air)}° / ${fmt(worst?.rh, 0)}`, "%"],
                ["벽면 온도", fmt(worst?.t_surf), "°C"],
              ].map(([k, v, u]) => (
                <div key={k} className="rounded-xl bg-slate-50 p-3">
                  <dt className="text-xs text-slate-500">{k}</dt>
                  <dd className="mt-1 text-xl font-semibold tabular-nums">{v}<span className="ml-0.5 text-sm font-normal text-slate-500">{u}</span></dd>
                </div>
              ))}
            </dl>
            {cur.data?.forecast && (
              <p className="mt-3 rounded-xl bg-orange-50 p-3 text-sm text-orange-900 ring-1 ring-orange-200">
                약 {cur.data.forecast.hours_low.toFixed(1)}–{cur.data.forecast.hours_high.toFixed(1)}시간 뒤 {cur.data.forecast.target < 100 ? "곰팡이 위험 구간" : "결로"} 진입 예상
              </p>
            )}
          </section>

          <section className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
            <h2 className="mb-3 font-semibold">상태 이벤트 <span className="text-sm font-normal text-slate-400">{range}</span></h2>
            {list.length ? (
              <ol className="relative grid gap-3 border-l-2 border-slate-100 pl-4">
                {list.map((e) => (
                  <li key={e.id} className="relative">
                    <span className="absolute -left-[23px] top-1.5 h-3 w-3 rounded-full ring-2 ring-white" style={{ background: STATE[e.state].color }} />
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium">{STATE[e.state].label}</span>
                      {e.peak_rh_surf != null && <span className="text-xs text-slate-400">최고 {e.peak_rh_surf.toFixed(0)}%</span>}
                    </div>
                    <div className="text-xs tabular-nums text-slate-500">{hhmm(e.started_at)} – {e.ended_at ? hhmm(e.ended_at) : "진행 중"}</div>
                  </li>
                ))}
              </ol>
            ) : <p className="text-sm text-slate-400">이 기간에 주의 단계 이상으로 올라간 적이 없습니다.</p>}
          </section>
        </div>
      </div>
    </div>
  );
}
