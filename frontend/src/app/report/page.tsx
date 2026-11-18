"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Icon } from "@/components/Icon";
import { ExperienceChoice, useExperience } from "@/components/Experience";
import { api, type Device, type ProbeReading } from "@/lib/api";
import { fmt } from "@/lib/format";
import { downloadReportPdf } from "@/lib/report-pdf";
import { hourlyStats, koreaDay, periodBounds, periodError, quickPeriod, reportRows, sampleReport, type ReportPeriod } from "@/lib/report-data";

const initialPeriod = () => quickPeriod(7);
const dateLabel = (value: string, daily: boolean) => new Date(value.length === 10 ? `${value}T00:00:00+09:00` : value).toLocaleString("ko-KR", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit", ...(!daily && { hour: "2-digit", minute: "2-digit", hour12: false }) });

export default function ReportPage() {
  const { mode, ready, setMode } = useExperience();
  const demo = mode === "demo";
  const [picked, setPicked] = useState("");
  const [draft, setDraft] = useState<ReportPeriod>(initialPeriod);
  const [period, setPeriod] = useState<ReportPeriod>(initialPeriod);
  const [daily, setDaily] = useState(true);
  const [saving, setSaving] = useState(false);
  const [pdfError, setPdfError] = useState("");
  const devices = useQuery({ queryKey: ["devices"], queryFn: () => api<Device[]>("/devices"), enabled: ready && mode === "live", retry: 1 });
  const device = devices.data?.find(d => d.id === picked) ?? devices.data?.[0];
  const readings = useQuery({
    queryKey: ["report-series", device?.id, period.from, period.to],
    enabled: ready && mode === "live" && !!device && !periodError(period), retry: 1,
    queryFn: () => {
      const { from, to } = periodBounds(period);
      const params = new URLSearchParams({ from: new Date(from).toISOString(), to: new Date(to).toISOString(), bucket: "1h" });
      return api<ProbeReading[]>(`/devices/${encodeURIComponent(device!.id)}/series?${params}`);
    },
  });
  const sample = useMemo(() => sampleReport(period), [period]);
  const series = demo ? sample : readings.data;
  const rows = useMemo(() => reportRows(series ?? [], period, daily), [series, period, daily]);
  const hasData = rows.some(r => r.count > 0);
  const invalid = periodError(draft);
  const dirty = draft.from !== period.from || draft.to !== period.to;
  const busy = mode === "live" && (devices.isPending || (!!device && readings.isPending));
  const failed = mode === "live" && (devices.isError || (!!device && readings.isError));
  const days = (periodBounds(period).to - periodBounds(period).from) / 86400_000;
  const title = demo ? "나의 방 · 샘플" : device?.label || device?.id || "측정 기기";
  const summary = [
    { name: "실내 온도", icon: "temp", stats: hourlyStats((series ?? []).map(p => p.t_air)), unit: "°C", className: "air" },
    { name: "실내 습도", icon: "drop", stats: hourlyStats((series ?? []).map(p => p.rh)), unit: "%", className: "humidity" },
    { name: "벽면 온도", icon: "wall", stats: hourlyStats((series ?? []).map(p => p.t_surf)), unit: "°C", className: "wall" },
  ];

  if (!ready) return <div className="loading-card" role="status">화면을 준비하고 있어요…</div>;
  if (mode === "welcome") return <ExperienceChoice />;

  return <div className="dashboard report-page">
    <div className="page-eyebrow print:hidden"><span>내 공간의 기록</span><span>대시보드 / 측정 리포트</span></div>
    <header className="dashboard-heading print:hidden"><div><h1>우리 집의 기록을 차곡차곡<span>.</span></h1><p>기간을 선택하고, 온도와 습도의 변화를 편하게 살펴보세요.</p></div><button className="button secondary" onClick={() => setMode(demo ? "live" : "demo")}>{demo ? "내 기기 기록 보기" : "샘플 리포트 보기"}<Icon name="arrow" /></button></header>
    {demo && <div className="demo-banner print:hidden" role="status"><div><strong>샘플 리포트</strong><span>가상 데이터입니다. 날짜 선택과 PDF 저장을 미리 확인할 수 있어요.</span></div></div>}
    <form className="report-filters glass-panel print:hidden" onSubmit={e => { e.preventDefault(); if (!invalid) { if (!dirty && !demo) readings.refetch(); setPeriod({ ...draft }); } }}>
      <div className="filter-heading"><Icon name="report" /><div><h2>어떤 기간을 살펴볼까요?</h2><p>선택한 종료일까지 포함해 조회합니다. 한국 시간 기준.</p></div></div>
      <div className="quick-periods" role="group" aria-label="빠른 조회 기간">
        {([1, 7, 30] as const).map(days => {
          const preset = quickPeriod(days);
          const active = !dirty && period.from === preset.from && period.to === preset.to;
          return <button key={days} type="button" aria-pressed={active} disabled={saving} onClick={() => { const next = quickPeriod(days); setDraft(next); setPeriod(next); setPdfError(""); }}>{days === 1 ? "오늘" : `최근 ${days}일`}</button>;
        })}
      </div>
      <div className="filter-fields">
        <label><span>측정 공간</span><select value={demo ? "sample" : device?.id ?? ""} onChange={e => setPicked(e.target.value)} disabled={demo || !devices.data?.length}>{demo ? <option value="sample">나의 방 · 샘플</option> : devices.data?.length ? devices.data.map(d => <option key={d.id} value={d.id}>{d.label || d.id}</option>) : <option value="">연결된 기기 없음</option>}</select></label>
        <label><span>시작일</span><input type="date" required aria-describedby="period-message" value={draft.from} max={draft.to || koreaDay()} onInput={e => setDraft({ ...draft, from: e.currentTarget.value })} onChange={e => setDraft({ ...draft, from: e.target.value })} /></label>
        <label><span>종료일</span><input type="date" required aria-describedby="period-message" value={draft.to} min={draft.from} max={koreaDay()} onInput={e => setDraft({ ...draft, to: e.currentTarget.value })} onChange={e => setDraft({ ...draft, to: e.target.value })} /></label>
        <button className="button primary" type="submit" disabled={!!invalid || (!demo && !device) || (!demo && readings.isFetching)}><Icon name="chart" />{!demo && readings.isFetching ? "불러오는 중…" : "기록 조회"}</button>
      </div>
      <p id="period-message" className={invalid ? "filter-message invalid" : "filter-message"} role="status">{invalid || (dirty ? "날짜를 바꿨어요. ‘기록 조회’를 눌러 적용해 주세요." : "일별 평균과 시간별 평균으로 측정 기록을 확인할 수 있어요.")}</p>
    </form>
    {failed && <div className="empty-card print:hidden" role="alert"><Icon name="wall" className="h-8 w-8" /><h2>측정 기록을 불러오지 못했어요</h2><p>서버 연결을 확인하거나 샘플 리포트로 먼저 살펴보세요.</p><button className="button secondary" onClick={() => devices.isError ? devices.refetch() : readings.refetch()}>다시 시도</button></div>}
    {busy && <div className="loading-card print:hidden" role="status">측정 기록을 정리하고 있어요…</div>}
    {!busy && !failed && <article className="report-document">
      <header className="report-document-heading"><div><span className="section-kicker">INDOOR ENVIRONMENT REPORT</span><h2>{title} 측정 리포트</h2><p>{dateLabel(period.from, true)} — {dateLabel(period.to, true)} <span>· {days}일 · 한국 시간</span></p></div><button type="button" className="button primary print:hidden" disabled={!hasData || dirty || !!invalid || saving} onClick={async () => { setSaving(true); setPdfError(""); try { await downloadReportPdf({ title, period, rows, daily, sample: demo, averages: summary.map(item => item.stats.mean), extremes: summary.map(item => ({ min: item.stats.min, max: item.stats.max })) }); } catch { setPdfError("PDF를 저장하지 못했어요. 잠시 후 다시 시도해 주세요."); } finally { setSaving(false); } }}><Icon name="report" />{saving ? "PDF 만드는 중…" : "PDF 저장"}</button></header>
      {pdfError && <p className="filter-message invalid" role="alert">{pdfError}</p>}
      {demo && <p className="print-sample-label">샘플 데이터 · 실제 측정 결과가 아닙니다.</p>}
      <div className="report-summary">{summary.map(item => <section key={item.name} className={`report-stat glass-panel ${item.className}`}><div><span className="stat-icon"><Icon name={item.icon} /></span><h3>평균 {item.name}</h3></div><p>{fmt(item.stats.mean)}<span>{item.unit}</span></p><div className="stat-extremes"><span>최저 <b>{fmt(item.stats.min)}{item.unit}</b></span><span>최고 <b>{fmt(item.stats.max)}{item.unit}</b></span></div><small>평균·최고·최저 모두 수신된 시간별 평균 기준</small></section>)}</div>
      <section className="report-records glass-panel">
        <div className="report-table-heading"><div><h3>날짜별 측정 기록</h3><p>{daily ? "날짜별 평균값" : "시간별 평균값"} · {rows.length.toLocaleString()}개 행{!daily && " · 측정 시간 기준"}</p></div><div className="range-tabs print:hidden" role="group" aria-label="리포트 집계 단위"><button type="button" aria-pressed={daily} onClick={() => setDaily(true)}>일별 평균</button><button type="button" aria-pressed={!daily} onClick={() => setDaily(false)}>시간별 평균</button></div></div>
        {!hasData ? <div className="report-empty"><Icon name="report" className="h-8 w-8" /><h3>{!demo && !device ? "연결된 측정 기기가 없어요" : "이 기간의 기록이 아직 없어요"}</h3><p>다른 날짜를 선택하거나 기기 연결 상태를 확인해 주세요.</p></div> : <div className="report-table-scroll" tabIndex={0} role="region" aria-label="온도 및 습도 측정 기록"><table className="report-table"><caption className="sr-only">{title}, {period.from}부터 {period.to}까지 {daily ? "일별" : "시간별"} 실내 온도·습도·벽면 온도 평균</caption><thead><tr><th scope="col">{daily ? "측정 날짜" : "측정 일시"}</th><th scope="col" className="air-text">실내 온도 <span>°C</span></th><th scope="col" className="humidity-text">실내 습도 <span>%</span></th><th scope="col" className="wall-text">벽면 온도 <span>°C</span></th></tr></thead><tbody>{rows.map(row => <tr key={`${row.date}/${row.probe}`}><th scope="row"><span>{dateLabel(row.date, daily)}</span><small>{row.probe}{!row.count && " · 수신 기록 없음"}</small></th><td className="air-text">{fmt(row.air)}</td><td className="humidity-text">{fmt(row.humidity)}</td><td className="wall-text">{fmt(row.wall)}</td></tr>)}</tbody></table></div>}
        <div className="report-table-note"><Icon name="shield" /><p>일별 값은 한국 시간 00:00~23:59의 수신된 시간별 집계값을 평균한 값입니다. 센서가 여러 개면 각각 표시하며, 기록이 없는 날은 ‘—’로 표시합니다. 오늘은 현재까지의 기록입니다.</p></div>
      </section>
      <footer className="report-footnote"><span>벽면 곰팡이 예보 · 환경 측정 기록</span><p className="print:hidden">선택한 집계 단위의 모든 행을 PDF로 바로 저장합니다. 한글 글꼴을 유지하기 위해 이미지 기반으로 저장됩니다.</p><p>이 리포트는 측정 환경을 이해하기 위한 참고자료입니다.</p></footer>
    </article>}
  </div>;
}
