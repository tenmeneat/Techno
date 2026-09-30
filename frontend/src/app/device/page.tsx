"use client";
// 상세 차트 (§10.2): Ts / Td / T80 3선 + 위험 밴드, 24h / 7d / 30d
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { RiskChart } from "@/components/RiskChart";
import { StateBadge } from "@/components/StateBadge";
import { api, type Current, type Event, type ProbeReading, RANGES, type RangeKey, rangeParams } from "@/lib/api";
import { hhmm, STATE } from "@/lib/format";
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

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">{id}</h1>
        {cur.data && <StateBadge state={cur.data.state} />}
      </div>

      <div className="flex gap-2">
        {(Object.keys(RANGES) as RangeKey[]).map((r) => (
          <button key={r} onClick={() => setRange(r)}
            className={`rounded-lg px-3 py-1 text-sm ${r === range ? "bg-blue-700 text-white" : "bg-white"}`}>{r}</button>
        ))}
      </div>

      <div className="rounded-2xl bg-white p-2 shadow-sm">
        {series.data ? <RiskChart series={series.data} events={events.data ?? []} from={from} to={to} /> : <p className="p-4">불러오는 중…</p>}
      </div>

      <section className="rounded-2xl bg-white p-4 shadow-sm">
        <h2 className="mb-2 font-semibold">상태 이벤트</h2>
        <ul className="grid gap-1 text-sm">
          {(events.data ?? []).filter((e) => e.state !== "WATCH").map((e) => (
            <li key={e.id} className="flex justify-between">
              <span style={{ color: STATE[e.state].color }}>{STATE[e.state].label}</span>
              <span className="text-gray-500">{hhmm(e.started_at)} – {e.ended_at ? hhmm(e.ended_at) : "진행 중"}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
