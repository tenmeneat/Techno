"use client";
// 홈 (§10.2): 기기별 상태 카드 — RHs 링게이지, 온·습도, ΔT, 상태 배지, 예측 구간
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { StateBadge } from "@/components/StateBadge";
import { api, type Current, type Device } from "@/lib/api";
import { fmt, STATE } from "@/lib/format";
import { useLive } from "@/lib/live";

export default function Home() {
  useLive();
  const { data: devices, error } = useQuery({ queryKey: ["devices"], queryFn: () => api<Device[]>("/devices") });
  if (error) return <p className="text-red-600">서버에 연결할 수 없습니다.</p>;
  if (!devices) return <p>불러오는 중…</p>;
  if (!devices.length) return <p>등록된 기기가 없습니다. 기기가 첫 측정값을 보내면 자동 등록됩니다.</p>;
  return (
    <div className="grid gap-4">
      {devices.map((d) => <DeviceCard key={d.id} device={d} />)}
    </div>
  );
}

function DeviceCard({ device }: { device: Device }) {
  const { data: cur } = useQuery({
    queryKey: ["current", device.id],
    queryFn: () => api<Current>(`/devices/${device.id}/current`),
  });
  // 판정은 가장 위험한 프로브 기준 — 표시도 같게
  const worst = cur?.probes.reduce((a, b) => (b.rh_surf > a.rh_surf ? b : a), cur.probes[0]);
  const state = cur?.state ?? device.state;
  const fc = cur?.forecast;

  return (
    <Link href={`/device/?id=${encodeURIComponent(device.id)}`} className="block rounded-2xl bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <div className="font-semibold">{device.label ?? device.id}</div>
          <div className="text-xs text-gray-500">{device.location_tag}</div>
        </div>
        <StateBadge state={state} />
      </div>
      <div className="flex items-center gap-4">
        <Ring value={worst?.rh_surf} color={STATE[state].color} />
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
          <dt className="text-gray-500">실내</dt><dd>{fmt(worst?.t_air)}°C / {fmt(worst?.rh, 0)}%</dd>
          <dt className="text-gray-500">벽면 Ts</dt><dd>{fmt(worst?.t_surf)}°C</dd>
          <dt className="text-gray-500">이슬점 Td</dt><dd>{fmt(worst?.t_dew)}°C</dd>
          <dt className="text-gray-500">여유 ΔT</dt><dd>{worst ? fmt(worst.t_surf - worst.t_dew) : "—"} K</dd>
        </dl>
      </div>
      {fc && (
        <p className="mt-3 rounded-lg bg-orange-50 p-2 text-sm text-orange-900">
          약 {fc.hours_low.toFixed(1)}–{fc.hours_high.toFixed(1)}시간 뒤 {fc.target < 100 ? "곰팡이 위험 구간" : "결로"} 진입 예상
        </p>
      )}
    </Link>
  );
}

function Ring({ value, color }: { value?: number; color: string }) {
  const r = 34, c = 2 * Math.PI * r, v = Math.min(100, value ?? 0);
  return (
    <svg viewBox="0 0 80 80" className="h-24 w-24 shrink-0" role="img" aria-label={`벽면 습도 ${fmt(value, 0)}%`}>
      <circle cx="40" cy="40" r={r} fill="none" stroke="#e5e7eb" strokeWidth="8" />
      <circle cx="40" cy="40" r={r} fill="none" stroke={color} strokeWidth="8" strokeLinecap="round"
        strokeDasharray={`${(v / 100) * c} ${c}`} transform="rotate(-90 40 40)" />
      <text x="40" y="40" textAnchor="middle" fontSize="16" fontWeight="700">{fmt(value, 0)}%</text>
      <text x="40" y="54" textAnchor="middle" fontSize="8" fill="#6b7280">벽면 습도</text>
    </svg>
  );
}
