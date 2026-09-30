"use client";
// 리포트 (§10.6). 인쇄용 페이지 → 브라우저 "PDF로 저장". 표현 수위는 §4.4를 따른다.
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { api, type Device, post, type Report } from "@/lib/api";
import { F_RSI_MIN, fmt, fRsiLabel } from "@/lib/format";

const isoDay = (d: Date) => d.toISOString().slice(0, 10);

export default function ReportPage() {
  const devices = useQuery({ queryKey: ["devices"], queryFn: () => api<Device[]>("/devices") }).data ?? [];
  const [deviceId, setDeviceId] = useState("");
  const [from, setFrom] = useState(isoDay(new Date(Date.now() - 21 * 86400_000)));
  const [to, setTo] = useState(isoDay(new Date()));
  const gen = useMutation({
    mutationFn: () => post<Report>("/reports", {
      device_id: deviceId || devices[0]?.id,
      from: new Date(`${from}T00:00:00+09:00`).toISOString(),
      to: new Date(`${to}T24:00:00+09:00`).toISOString(),
    }),
  });
  const r = gen.data;

  return (
    <div className="grid gap-4">
      <form className="flex flex-wrap items-end gap-2 print:hidden" onSubmit={(e) => { e.preventDefault(); gen.mutate(); }}>
        <select className="rounded border p-1" value={deviceId} onChange={(e) => setDeviceId(e.target.value)}>
          {devices.map((d) => <option key={d.id} value={d.id}>{d.label ?? d.id}</option>)}
        </select>
        <input type="date" className="rounded border p-1" value={from} onChange={(e) => setFrom(e.target.value)} />
        <input type="date" className="rounded border p-1" value={to} onChange={(e) => setTo(e.target.value)} />
        <button className="rounded bg-blue-700 px-3 py-1 text-white" disabled={!devices.length}>생성</button>
        {r && <button type="button" className="rounded bg-gray-800 px-3 py-1 text-white" onClick={() => window.print()}>PDF 저장</button>}
      </form>

      {r && (
        <article className="grid gap-6 bg-white p-6 text-sm">
          <h1 className="text-xl font-bold">벽면 결로·곰팡이 상시 측정 기록</h1>

          <section>
            <h2 className="mb-1 font-semibold">1. 측정 개요</h2>
            <p>기간 {new Date(r.from).toLocaleDateString("ko-KR")} – {new Date(r.to).toLocaleDateString("ko-KR")}</p>
            <p>기기 {r.device.label ?? r.device.id} · 위치 {r.device.location_tag ?? "—"} · 펌웨어 {r.device.fw ?? "—"}</p>
            <p>캘리브레이션 오프셋: 공기온도 {fmt(r.device.calib_t_air, 2)}K, 습도 {fmt(r.device.calib_rh, 1)}%p, 벽면온도 {fmt(r.device.calib_t_surf, 2)}K</p>
          </section>

          <section>
            <h2 className="mb-1 font-semibold">2. 위험 상태 누적</h2>
            <p>곰팡이 위험(벽면 상대습도 ≥ 80%) {(r.minutes_alert / 60).toFixed(1)}시간 · 결로(≥ 100%) {(r.minutes_condensing / 60).toFixed(1)}시간</p>
            <p>기간 평균 벽면 상대습도 {fmt(r.mean_rh_surf)}% (ISO 13788 곰팡이 방지 기준: 월평균 80% 미만)</p>
            <p>발생 일자: {r.event_days.join(", ") || "없음"}</p>
          </section>

          <section>
            <h2 className="mb-1 font-semibold">3. 온도계수 fRsi 추이</h2>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={r.diagnostics} margin={{ left: -20, right: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="day" fontSize={10} />
                <YAxis domain={[0.5, 1]} fontSize={10} />
                <ReferenceLine y={F_RSI_MIN} stroke="#dc2626" strokeDasharray="4 3" label={{ value: "0.70", fontSize: 10 }} />
                <Line dataKey="f_rsi" stroke="#1d4ed8" isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
            <p>최근 값: {fRsiLabel(r.diagnostics.findLast((d) => d.f_rsi != null)?.f_rsi)}</p>
            <p className="text-gray-500">본 자료는 규격 기준 대비 측정값이며, 하자 여부에 대한 판정이 아닙니다.</p>
          </section>

          <section>
            <h2 className="mb-1 font-semibold">4. 측정 방법 및 불확도</h2>
            <ul className="list-disc pl-5">
              <li>센서: 공기 DHT22(±0.5K, ±2–5%p), 벽면 DS18B20(±0.5K) 단열 차폐 부착. 30초 간격.</li>
              <li>결로 여유도 ΔT 표준불확도 약 ±1.0K, 벽면 상대습도 약 ±4.5%p. 판정은 5분 중앙값과 히스테리시스(3%p)를 적용.</li>
              <li>절대값보다 동일 기기의 시간 변화, 캘리브레이션된 기기 간 비교에 유효합니다.</li>
              <li>fRsi는 실내외 온도차 10K 이상인 02–06시 측정값의 일간 중앙값. 외기온 대표성 불확도 ±1.0K 반영.</li>
              <li>외기온 출처: 기상청 API허브 ASOS {r.weather_sources["kma"] ?? 0}시간, Open-Meteo (CC BY 4.0, open-meteo.com) {r.weather_sources["open-meteo"] ?? 0}시간.</li>
            </ul>
          </section>
        </article>
      )}
    </div>
  );
}
