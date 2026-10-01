"use client";
// 리포트 (§10.6). 일반 사용자가 읽는 문서: 결론 → 숫자 → 그림 → 행동 안내 → (접힌) 측정 방법.
// 인쇄용 페이지 → 브라우저 "PDF로 저장". 표현 수위는 §4.4: '하자', '책임' 같은 단어는 쓰지 않는다.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type Device, post, type Report } from "@/lib/api";
import { F_RSI_MIN, fmt, fRsiMedian7, STATE } from "@/lib/format";

const isoDay = (d: Date) => d.toISOString().slice(0, 10);
const kDate = (s: string | Date) => new Date(s).toLocaleDateString("ko-KR", { month: "long", day: "numeric" });

export default function ReportPage() {
  const devices = useQuery({ queryKey: ["devices"], queryFn: () => api<Device[]>("/devices") }).data ?? [];
  const [picked, setPicked] = useState("");
  const [from, setFrom] = useState(isoDay(new Date(Date.now() - 21 * 86400_000)));
  const [to, setTo] = useState(isoDay(new Date()));
  const deviceId = picked || devices[0]?.id;

  const report = useQuery({
    queryKey: ["report", deviceId, from, to],
    enabled: !!deviceId,
    queryFn: () => post<Report>("/reports", {
      device_id: deviceId,
      from: new Date(`${from}T00:00:00+09:00`).toISOString(),
      to: new Date(new Date(`${to}T00:00:00+09:00`).getTime() + 86400_000).toISOString(),
    }),
  });

  return (
    <div className="grid gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4 print:hidden">
        <div>
          <h1 className="text-2xl font-bold tracking-tight md:text-3xl">리포트</h1>
          <p className="mt-1 text-sm text-slate-500">기간을 고르면 바로 만들어집니다. 집주인·관리인과 이야기할 때 PDF로 저장해 보여주세요.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 rounded-xl bg-white p-2 shadow-sm ring-1 ring-slate-200">
          <select className="rounded-lg border-0 bg-slate-50 px-3 py-2 text-sm" value={deviceId ?? ""} onChange={(e) => setPicked(e.target.value)} aria-label="방">
            {devices.map((d) => <option key={d.id} value={d.id}>{d.label ?? d.id}</option>)}
          </select>
          <input type="date" className="rounded-lg bg-slate-50 px-3 py-2 text-sm" value={from} max={to} onChange={(e) => setFrom(e.target.value)} aria-label="시작일" />
          <span className="text-slate-400">~</span>
          <input type="date" className="rounded-lg bg-slate-50 px-3 py-2 text-sm" value={to} min={from} onChange={(e) => setTo(e.target.value)} aria-label="종료일" />
          <button className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
            disabled={!report.data} onClick={() => window.print()}>PDF 저장</button>
        </div>
      </header>

      {report.isError && <p className="rounded-2xl bg-red-50 p-6 text-sm text-red-800 ring-1 ring-red-200">리포트를 만들지 못했습니다. 서버 연결을 확인하세요.</p>}
      {report.isLoading && <div className="h-96 animate-pulse rounded-2xl bg-white" />}
      {report.data && <ReportView r={report.data} />}
    </div>
  );
}

function ReportView({ r }: { r: Report }) {
  useEffect(() => { // PDF에는 접힌 '자세히'도 펼쳐서 들어가게
    const open = () => document.querySelectorAll("details").forEach((d) => (d.open = true));
    addEventListener("beforeprint", open);
    return () => removeEventListener("beforeprint", open);
  }, []);
  const days = Math.max(1, Math.round((new Date(r.to).getTime() - new Date(r.from).getTime()) / 86400_000));
  // 일간 집계(어제까지)와 이벤트 기록(오늘 포함) 중 큰 쪽 — 위 숫자와 아래 그래프가 어긋나지 않게
  const riskH = Math.max(r.diagnostics.reduce((s, d) => s + d.minutes_alert, 0), r.minutes_alert + r.minutes_condensing) / 60;
  const wetH = r.minutes_condensing / 60;
  const riskDays = r.diagnostics.filter((d) => d.minutes_alert > 0).length || r.event_days.length;
  const f = fRsiMedian7(r.diagnostics);
  const insulationWeak = f != null && f < F_RSI_MIN;
  const level = wetH > 0 || riskDays > days / 3 ? "CONDENSING" : riskH > 0 ? "ALERT" : "SAFE";
  const headline =
    level === "SAFE" ? "이 기간 동안 벽면은 대체로 곰팡이가 자라기 어려운 상태였습니다."
    : level === "ALERT" ? `${days}일 중 ${riskDays}일, 벽면이 곰팡이가 자라기 쉬운 습도까지 올라갔습니다.`
    : `${days}일 중 ${riskDays}일 벽면이 곰팡이가 자라기 쉬운 상태였고, ${wetH >= 1 ? `${wetH.toFixed(0)}시간 동안` : "한때"} 벽에 물이 맺히는 조건이었습니다.`;

  return (
    <article className="mx-auto grid w-full max-w-5xl gap-6 print:max-w-none print:gap-4">
      {/* 표지 + 결론 */}
      <section className="overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-slate-200">
        <div className="bg-slate-900 px-6 py-5 text-white md:px-8">
          <div className="text-xs font-medium tracking-wide text-slate-400">벽면 결로 · 곰팡이 측정 기록</div>
          <h2 className="mt-1 text-xl font-bold md:text-2xl">{r.device.label ?? r.device.id}{r.device.location_tag && <span className="font-normal text-slate-300"> · {r.device.location_tag}</span>}</h2>
          <div className="mt-1 text-sm text-slate-300">{kDate(r.from)} ~ {kDate(new Date(new Date(r.to).getTime() - 1))} ({days}일간 30초마다 측정)</div>
        </div>
        <div className={`flex items-start gap-3 px-6 py-5 md:px-8 ${STATE[level].soft} ring-1 ring-inset`}>
          <span className="mt-1.5 h-3 w-3 shrink-0 rounded-full" style={{ background: STATE[level].color }} aria-hidden />
          <div>
            <div className={`text-xs font-semibold ${STATE[level].text}`}>한 줄 요약</div>
            <p className="mt-0.5 text-lg font-semibold leading-snug md:text-xl">{headline}</p>
          </div>
        </div>
      </section>

      {/* 큰 숫자 */}
      <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Kpi label="곰팡이가 자라기 쉬웠던 시간" value={riskH.toFixed(0)} unit="시간" note={`하루 평균 ${(riskH / days * 60).toFixed(0)}분`} color={STATE.ALERT.color} />
        <Kpi label="벽에 물이 맺힌 시간" value={wetH.toFixed(0)} unit="시간" note="결로 조건" color={STATE.CONDENSING.color} />
        <Kpi label="위험했던 날" value={`${riskDays}`} unit={`/ ${days}일`} note="하루 중 한 번이라도" color={STATE.WATCH.color} />
        <Kpi label="벽면 평균 습도" value={fmt(r.mean_rh_surf, 0)} unit="%" note="기준 80% 미만이 안전" color={(r.mean_rh_surf ?? 0) >= 80 ? STATE.CONDENSING.color : STATE.SAFE.color} />
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* 평균 습도 vs 기준 */}
        <Card title="벽면 습도, 기준과 비교하면?" desc="벽에 닿은 공기의 습도가 80%를 넘으면 곰팡이가 자라기 시작합니다 (국제 기준 ISO 13788).">
          <HumidityBar value={r.mean_rh_surf} />
        </Card>

        {/* 단열 점수 */}
        <Card title="벽의 단열 상태는?" desc="바깥 추위가 방 안쪽 벽면까지 얼마나 전해지는지를 0~1 점수로 나타낸 값입니다. 높을수록 단열이 잘 된 벽입니다.">
          <InsulationBar value={f} />
          <p className={`mt-4 rounded-xl p-3 text-sm ${insulationWeak ? "bg-red-50 text-red-900" : "bg-slate-50 text-slate-700"}`}>
            {f == null
              ? "바깥이 충분히 춥지 않은 날만 있어서 아직 점수를 낼 수 없습니다. 겨울철(실내외 온도차 10℃ 이상)에 다시 확인하세요."
              : insulationWeak
                ? "설계 기준(0.70)보다 낮습니다. 이 경우 환기만으로는 벽이 젖는 것을 막기 어려울 수 있습니다."
                : "설계 기준(0.70) 이상입니다. 벽 자체보다는 실내 습도 관리가 더 중요한 상태입니다."}
          </p>
        </Card>
      </div>

      {/* 날짜별 */}
      <Card title="날짜별 위험 시간" desc="막대가 길수록 그날 벽면이 곰팡이가 자라기 쉬운 상태로 오래 있었다는 뜻입니다.">
        {r.diagnostics.length ? (
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={r.diagnostics.map((d) => ({ day: kDate(d.day), h: +(d.minutes_alert / 60).toFixed(1) }))} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="#e2e8f0" />
              <XAxis dataKey="day" fontSize={11} stroke="#94a3b8" tickLine={false} axisLine={false} minTickGap={16} />
              <YAxis unit="h" fontSize={11} stroke="#94a3b8" tickLine={false} axisLine={false} allowDecimals={false} />
              <Tooltip formatter={(v) => [`${v}시간`, "위험 시간"]} contentStyle={{ borderRadius: 10, border: "1px solid #e2e8f0", fontSize: 12 }} cursor={{ fill: "#f1f5f9" }} />
              <ReferenceLine y={0} stroke="#cbd5e1" />
              <Bar dataKey="h" fill={STATE.ALERT.color} radius={[4, 4, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        ) : <p className="text-sm text-slate-400">날짜별 집계가 아직 없습니다 (매일 아침 7시에 전날 분이 계산됩니다).</p>}
      </Card>

      {/* 행동 안내 */}
      <Card title="이렇게 해보세요" desc="측정 결과를 바탕으로 한 생활 안내입니다.">
        <ul className="grid gap-3 md:grid-cols-2">
          {riskH > 0 && <Tip icon="🪟">습해지는 시간대(샤워 후, 요리 후, 새벽)에 창문을 10분 정도 열어 환기하세요.</Tip>}
          {riskH > 0 && <Tip icon="🛋️">가구를 벽에서 10cm 이상 띄우면 벽면에 공기가 돌아 덜 습해집니다.</Tip>}
          {wetH > 0 && <Tip icon="🧽">물이 맺힌 날에는 마른 걸레로 벽과 창틀을 닦아 곰팡이가 자리 잡지 못하게 하세요.</Tip>}
          {insulationWeak && <Tip icon="📄">벽 단열 점수가 기준보다 낮습니다. 관리인과 상담할 때 이 리포트를 참고자료로 보여줄 수 있습니다.</Tip>}
          {riskH === 0 && <Tip icon="✅">지금처럼 관리하면 됩니다. 기온이 크게 떨어지는 날엔 알림을 확인하세요.</Tip>}
          <Tip icon="🔔">앱 알림을 켜두면 위험해지기 1~2시간 전에 미리 알려드립니다.</Tip>
        </ul>
      </Card>

      {/* 전문 내용 — 접어둠, 인쇄 시에는 펼침 */}
      <details className="group rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200 md:p-6">
        <summary className="cursor-pointer list-none font-semibold">
          <span className="mr-1 inline-block transition group-open:rotate-90">›</span> 측정 방법과 정확도 (자세히)
        </summary>
        <div className="mt-4 grid gap-4 text-sm text-slate-600 md:grid-cols-2">
          <dl className="grid gap-2">
            <Term k="벽면 상대습도">벽에 닿은 공기의 습도. 실내 온습도와 벽 표면온도로 계산합니다. 80% 이상이면 곰팡이 위험(ISO 13788), 100%면 결로.</Term>
            <Term k="결로">벽 온도가 이슬점보다 낮아져 공기 중 수증기가 물방울로 맺히는 현상.</Term>
            <Term k="단열 점수 (fRsi)">(벽 표면온도 − 바깥온도) ÷ (실내온도 − 바깥온도). 실내외 온도차 10℃ 이상인 새벽 2~6시 값만 사용, 최근 7일 중앙값. 기준 0.70 (DIN 4108-2 · ISO 13788 관행). 현재 {fmt(f, 2)}.</Term>
          </dl>
          <dl className="grid gap-2">
            <Term k="센서">실내 DHT22(온도 ±0.5℃, 습도 ±2~5%), 벽면 DS18B20(±0.5℃)를 단열재로 덮어 부착. 30초 간격.</Term>
            <Term k="정확도">벽면 습도 계산값은 약 ±4.5%p 오차가 있습니다. 절대값보다는 같은 방의 시간 변화나 방끼리 비교에 적합합니다.</Term>
            <Term k="보정값">공기온도 {fmt(r.device.calib_t_air, 2)}℃ · 습도 {fmt(r.device.calib_rh, 1)}%p · 벽면온도 {fmt(r.device.calib_t_surf, 2)}℃</Term>
            <Term k="바깥 기온 출처">기상청 API허브 {r.weather_sources["kma"] ?? 0}시간 · Open-Meteo(CC BY 4.0) {r.weather_sources["open-meteo"] ?? 0}시간</Term>
          </dl>
        </div>
        <p className="mt-4 text-xs text-slate-400">이 자료는 국제 기준 대비 측정값을 정리한 참고자료이며, 건물 하자 여부를 판정하지 않습니다.</p>
      </details>
    </article>
  );
}

function Kpi({ label, value, unit, note, color }: { label: string; value: string; unit: string; note: string; color: string }) {
  return (
    <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
      <div className="flex items-center gap-1.5 text-xs font-medium text-slate-500">
        <span className="h-2 w-2 rounded-full" style={{ background: color }} aria-hidden />{label}
      </div>
      <div className="mt-2 text-3xl font-bold tabular-nums tracking-tight md:text-4xl">
        {value}<span className="ml-1 text-base font-medium text-slate-500">{unit}</span>
      </div>
      <div className="mt-1 text-xs text-slate-400">{note}</div>
    </div>
  );
}

function Card({ title, desc, children }: { title: string; desc: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200 md:p-6">
      <h3 className="text-lg font-semibold">{title}</h3>
      <p className="mb-5 mt-1 text-sm text-slate-500">{desc}</p>
      {children}
    </section>
  );
}

// 눈금 막대 + 현재 위치 표시. zones: [끝값, 색, 라벨]
function ZoneBar({ min, max, zones, value, fmtValue }: {
  min: number; max: number; zones: [number, string, string][]; value: number | null; fmtValue: (v: number) => string;
}) {
  const pct = (x: number) => ((Math.min(max, Math.max(min, x)) - min) / (max - min)) * 100;
  let start = min;
  return (
    <div className="pt-8">
      <div className="relative">
        {value != null && (
          <div className="absolute -top-8 -translate-x-1/2 text-center" style={{ left: `${pct(value)}%` }}>
            <div className="rounded-md bg-slate-900 px-2 py-0.5 text-sm font-bold text-white tabular-nums">{fmtValue(value)}</div>
            <div className="mx-auto h-0 w-0 border-x-[6px] border-t-[6px] border-x-transparent border-t-slate-900" />
          </div>
        )}
        <div className="flex h-4 gap-0.5 overflow-hidden rounded-full">
          {zones.map(([end, color]) => {
            const w = pct(end) - pct(start); start = end;
            return <div key={end} style={{ width: `${w}%`, background: color }} />;
          })}
        </div>
      </div>
      <div className="relative mt-2 h-8 text-[11px] leading-tight text-slate-600">
        {(() => { let s = min; return zones.map(([end, , label]) => {
          const mid = (pct(s) + pct(end)) / 2; s = end;
          // 좁은 끝 칸 라벨은 막대 안쪽으로 붙여 잘리지 않게
          const edge = mid > 94 ? "right" : mid < 6 ? "left" : null;
          return <span key={end} className={`absolute whitespace-nowrap ${edge === "right" ? "-translate-x-full" : edge ? "" : "-translate-x-1/2"}`}
            style={{ left: `${edge === "right" ? 100 : edge ? 0 : mid}%` }}>{label}</span>;
        }); })()}
      </div>
    </div>
  );
}

const HumidityBar = ({ value }: { value: number | null }) => (
  <ZoneBar min={40} max={100} value={value} fmtValue={(v) => `평균 ${v.toFixed(0)}%`} zones={[
    [72, STATE.SAFE.color, "안전"], [80, STATE.WATCH.color, "주의"], [97, STATE.ALERT.color, "곰팡이 위험"], [100, STATE.CONDENSING.color, "결로"],
  ]} />
);

const InsulationBar = ({ value }: { value: number | null }) => (
  <ZoneBar min={0.5} max={1} value={value} fmtValue={(v) => v.toFixed(2)} zones={[
    [0.7, STATE.CONDENSING.color, "기준 미달"], [0.75, STATE.ALERT.color, "경계"], [0.85, STATE.WATCH.color, "보통"], [1, STATE.SAFE.color, "양호"],
  ]} />
);

const Tip = ({ icon, children }: { icon: string; children: React.ReactNode }) => (
  <li className="flex gap-3 rounded-xl bg-slate-50 p-4 text-sm leading-relaxed text-slate-700">
    <span className="text-xl" aria-hidden>{icon}</span>{children}
  </li>
);

const Term = ({ k, children }: { k: string; children: React.ReactNode }) => (
  <div>
    <dt className="font-semibold text-slate-800">{k}</dt>
    <dd>{children}</dd>
  </div>
);
