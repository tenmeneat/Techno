"use client";
// 홈 (§10.2): 기기마다 상태 히어로 + 지표 타일 + 24시간 차트를 한 패널에
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo } from "react";
import { RiskChart } from "@/components/RiskChart";
import { StateBadge } from "@/components/StateBadge";
import { api, type Current, type Device, type Event, type ProbeReading, rangeParams } from "@/lib/api";
import { clock, fmt, STATE } from "@/lib/format";
import { useLive } from "@/lib/live";

export default function Home() {
  useLive();
  const { data: devices, error } = useQuery({ queryKey: ["devices"], queryFn: () => api<Device[]>("/devices") });
  const lastSeen = devices?.map((d) => d.last_seen).filter(Boolean).sort().at(-1);

  return (
    <div className="grid gap-6">
      <header className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold tracking-tight md:text-3xl">실시간 현황</h1>
          <p className="mt-1 text-sm text-slate-500">
            기기 {devices?.length ?? 0}대{lastSeen && ` · 마지막 수신 ${clock(lastSeen)}`}
          </p>
        </div>
        <Legend />
      </header>

      {error && <Notice tone="error">서버에 연결할 수 없습니다. 백엔드(Docker)가 켜져 있는지 확인하세요.</Notice>}
      {devices && !devices.length && <Notice>등록된 기기가 없습니다. 기기가 첫 측정값을 보내면 자동으로 나타납니다.</Notice>}
      {!devices && !error && <div className="h-96 animate-pulse rounded-2xl bg-white" />}
      {devices?.map((d) => <DevicePanel key={d.id} device={d} />)}
    </div>
  );
}

function DevicePanel({ device }: { device: Device }) {
  const { from, to, qs } = useMemo(() => rangeParams("24h"), []);
  const { data: cur } = useQuery({ queryKey: ["current", device.id], queryFn: () => api<Current>(`/devices/${device.id}/current`) });
  const series = useQuery({ queryKey: ["series", device.id, "24h"], queryFn: () => api<ProbeReading[]>(`/devices/${device.id}/series?${qs}&bucket=1m`) });
  const events = useQuery({ queryKey: ["events", device.id, "24h"], queryFn: () => api<Event[]>(`/devices/${device.id}/events?${qs}`) });

  // 판정은 가장 위험한 프로브 기준 — 표시도 같게
  const worst = cur?.probes.reduce((a, b) => (b.rh_surf > a.rh_surf ? b : a), cur.probes[0]);
  const state = cur?.state ?? device.state;
  const s = STATE[state];
  const fc = cur?.forecast;
  const alertMin = (events.data ?? [])
    .filter((e) => e.state === "ALERT" || e.state === "CONDENSING")
    .reduce((m, e) => m + ((e.ended_at ? new Date(e.ended_at).getTime() : Date.now()) - Math.max(from, new Date(e.started_at).getTime())) / 60000, 0);

  return (
    <section className="overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-slate-200">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-5 py-4 md:px-6">
        <div>
          <h2 className="text-lg font-semibold">{device.label ?? device.id}</h2>
          <p className="text-xs text-slate-500">{device.location_tag ?? "위치 미지정"} · {device.id}</p>
        </div>
        <Link href={`/device/?id=${encodeURIComponent(device.id)}`} className="rounded-lg px-3 py-1.5 text-sm font-medium text-blue-700 hover:bg-blue-50">
          상세 보기 →
        </Link>
      </div>

      <div className="grid lg:grid-cols-12">
        {/* 상태 히어로 */}
        <div className={`flex flex-col items-center gap-4 p-6 ring-1 ring-inset lg:col-span-4 ${s.soft}`}>
          <StateBadge state={state} large />
          <Gauge value={worst?.rh_surf} color={s.color} />
          <p className={`text-center text-sm font-medium ${s.text}`}>{s.advice}</p>
          {fc && (
            <div className="w-full rounded-xl bg-white/80 p-3 text-center text-sm ring-1 ring-orange-200">
              <div className="text-xs font-semibold text-orange-700">예보</div>
              약 <b>{fc.hours_low.toFixed(1)}–{fc.hours_high.toFixed(1)}시간</b> 뒤 {fc.target < 100 ? "곰팡이 위험 구간" : "결로"} 진입 예상
            </div>
          )}
          <Scale value={worst?.rh_surf} />
        </div>

        {/* 지표 + 차트 */}
        <div className="grid gap-5 p-5 md:p-6 lg:col-span-8">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
            <Tile label="실내 온도" value={fmt(worst?.t_air)} unit="°C" />
            <Tile label="실내 습도" value={fmt(worst?.rh, 0)} unit="%" />
            <Tile label="벽면 온도" value={fmt(worst?.t_surf)} unit="°C" hint="가장 찬 지점" />
            <Tile label="이슬점" value={fmt(worst?.t_dew)} unit="°C" hint="벽이 이보다 차면 결로" />
            <Tile label="곰팡이 임계" value={fmt(worst?.t80)} unit="°C" hint="벽이 이보다 차면 위험" />
            <Tile label="결로 여유" value={worst ? fmt(worst.t_surf - worst.t_dew) : "—"} unit="K" hint={`24h 위험 ${Math.round(alertMin)}분`} />
          </div>
          <div>
            <div className="mb-2 flex items-baseline justify-between">
              <h3 className="text-sm font-semibold text-slate-700">최근 24시간 벽면 온도</h3>
              <span className="text-xs text-slate-400">벽면 선이 색 띠 안으로 들어가면 위험</span>
            </div>
            {series.data
              ? <RiskChart series={series.data} events={events.data ?? []} from={from} to={to} height={260} />
              : <div className="h-[260px] animate-pulse rounded-xl bg-slate-50" />}
          </div>
        </div>
      </div>

      <EventStrip events={events.data ?? []} />
    </section>
  );
}

function EventStrip({ events }: { events: Event[] }) {
  const recent = events.filter((e) => e.state !== "STALE").slice(-6).reverse();
  return (
    <div className="border-t border-slate-100 px-5 py-4 md:px-6">
      <h3 className="mb-2 text-sm font-semibold text-slate-700">최근 24시간 상태 변화</h3>
      {recent.length ? (
        <ol className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {recent.map((e) => (
            <li key={e.id} className="flex items-center justify-between gap-2 rounded-lg bg-slate-50 px-3 py-2 text-sm">
              <StateBadge state={e.state} />
              <span className="tabular-nums text-slate-500">
                {clock(e.started_at)} – {e.ended_at ? clock(e.ended_at) : "진행 중"}
                {e.peak_rh_surf != null && <span className="ml-2 text-slate-400">최고 {e.peak_rh_surf.toFixed(0)}%</span>}
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-sm text-slate-400">24시간 동안 주의 단계 이상으로 올라간 적이 없습니다.</p>
      )}
    </div>
  );
}

function Tile({ label, value, unit, hint }: { label: string; value: string; unit: string; hint?: string }) {
  return (
    <div className="rounded-xl bg-slate-50 p-3 ring-1 ring-slate-100">
      <div className="text-xs font-medium text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums tracking-tight">
        {value}<span className="ml-0.5 text-sm font-normal text-slate-500">{unit}</span>
      </div>
      {hint && <div className="mt-0.5 truncate text-[11px] text-slate-400">{hint}</div>}
    </div>
  );
}

function Gauge({ value, color }: { value?: number; color: string }) {
  const r = 70, c = 2 * Math.PI * r, arc = c * 0.75, v = Math.min(100, value ?? 0);
  return (
    <svg viewBox="0 0 180 160" className="w-48 md:w-56" role="img" aria-label={`벽면 습도 ${fmt(value, 0)}%`}>
      <g transform="rotate(135 90 90)">
        <circle cx="90" cy="90" r={r} fill="none" stroke="#e2e8f0" strokeWidth="14" strokeLinecap="round" strokeDasharray={`${arc} ${c}`} />
        <circle cx="90" cy="90" r={r} fill="none" stroke={color} strokeWidth="14" strokeLinecap="round"
          strokeDasharray={`${(v / 100) * arc} ${c}`} style={{ transition: "stroke-dasharray .6s" }} />
      </g>
      <text x="90" y="92" textAnchor="middle" fontSize="38" fontWeight="700" fill="#0f172a">{fmt(value, 0)}<tspan fontSize="18">%</tspan></text>
      <text x="90" y="116" textAnchor="middle" fontSize="12" fill="#64748b">벽면 상대습도</text>
    </svg>
  );
}

// 판정 눈금: 72 주의 / 80 곰팡이 / 100 결로 (§3.3)
function Scale({ value }: { value?: number }) {
  const lo = 40, pct = (x: number) => `${((Math.min(100, Math.max(lo, x)) - lo) / (100 - lo)) * 100}%`;
  return (
    <div className="w-full">
      <div className="relative h-2 overflow-hidden rounded-full" style={{
        background: `linear-gradient(90deg, ${STATE.SAFE.color} 0 ${pct(72)}, ${STATE.WATCH.color} ${pct(72)} ${pct(80)}, ${STATE.ALERT.color} ${pct(80)} 97%, ${STATE.CONDENSING.color} 97%)`,
      }} />
      {value != null && (
        <div className="relative h-0">
          <div className="absolute -top-3.5 h-5 w-1 -translate-x-1/2 rounded-full bg-slate-900 ring-2 ring-white" style={{ left: pct(value) }} />
        </div>
      )}
      <div className="relative mt-1.5 h-4 text-[10px] text-slate-500">
        {[[40, "40"], [72, "72 주의"], [80, "80 곰팡이"], [100, "결로"]].map(([x, l]) => (
          <span key={x} className="absolute -translate-x-1/2 whitespace-nowrap first:translate-x-0 last:-translate-x-full" style={{ left: pct(+x) }}>{l}</span>
        ))}
      </div>
    </div>
  );
}

function Legend() {
  return (
    <div className="flex flex-wrap gap-3 text-xs text-slate-600">
      {(["SAFE", "WATCH", "ALERT", "CONDENSING"] as const).map((k) => (
        <span key={k} className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: STATE[k].color }} />{STATE[k].label}
        </span>
      ))}
    </div>
  );
}

function Notice({ children, tone }: { children: React.ReactNode; tone?: "error" }) {
  return (
    <div className={`rounded-2xl p-6 text-sm ring-1 ${tone === "error" ? "bg-red-50 text-red-800 ring-red-200" : "bg-white text-slate-600 ring-slate-200"}`}>
      {children}
    </div>
  );
}
