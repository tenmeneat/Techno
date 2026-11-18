"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ExperienceChoice, useExperience } from "@/components/Experience";
import { Icon } from "@/components/Icon";
import { RiskChart } from "@/components/RiskChart";
import { StateBadge } from "@/components/StateBadge";
import { api, type Current, type Device, type Event, type ProbeReading, type StateName, type RangeKey, rangeParams, RANGES } from "@/lib/api";
import { clock, fmt, STATE } from "@/lib/format";
import { useLive } from "@/lib/live";
import { sampleRoom } from "@/lib/demo";

const ACTIONS: Record<StateName, string> = {
  SAFE: "공기가 잘 순환하도록 유지해 주세요.",
  WATCH: "벽면 습도가 높아지고 있어요. 환기를 준비하세요.",
  ALERT: "창문을 열어 환기해 주세요.",
  CONDENSING: "환기하고 벽면 물기를 닦아 주세요.",
  STALE: "기기 전원과 Wi-Fi 연결을 확인해 주세요.",
};

export default function Home() {
  const { mode, ready, setMode, href } = useExperience();
  const demo = mode === "demo";
  const [sampleState, setSampleState] = useState<StateName>("SAFE");
  const [sampleTime] = useState(() => Date.now());
  useLive(undefined, ready && mode === "live");
  const devices = useQuery({
    queryKey: ["devices"],
    queryFn: () => api<Device[]>("/devices"),
    enabled: ready && mode === "live",
    retry: 1,
  });
  const sample = useMemo(() => sampleRoom(sampleState, sampleTime), [sampleState, sampleTime]);
  const rooms = demo ? [sample.device] : devices.data;

  if (!ready) return <div className="loading-card" role="status">화면을 준비하고 있어요…</div>;
  if (mode === "welcome") return <ExperienceChoice />;

  return (
    <div className="dashboard home-dashboard quick-home">
      <header className="quick-heading">
        <h1>실시간 현황</h1>
        <div className="quick-controls">
          {demo && (
            <select
              aria-label="샘플 상태"
              value={sampleState}
              onChange={(event) => setSampleState(event.target.value as StateName)}
            >
              {Object.entries(STATE).map(([key, value]) => <option key={key} value={key}>{value.label}</option>)}
            </select>
          )}
          <button className="button secondary" onClick={() => setMode(demo ? "live" : "demo")}>
            {demo ? "실제 기기" : "샘플 보기"}
          </button>
        </div>
      </header>
      {!demo && devices.isError && (
        <div className="empty-card" role="alert">
          <h2>측정 서버에 연결되지 않았어요</h2>
          <button className="button primary" onClick={() => devices.refetch()} disabled={devices.isFetching}>
            {devices.isFetching ? "연결 중…" : "다시 연결"}
          </button>
        </div>
      )}
      {!demo && devices.isPending && <div className="loading-card" role="status">기기 정보를 불러오고 있어요…</div>}
      {rooms?.length === 0 && (
        <div className="empty-card">
          <h2>연결된 기기가 없어요</h2>
          <Link className="button primary" href={href("/settings/")}>기기 설정 확인</Link>
        </div>
      )}
      {rooms?.map((device) => <Room key={mode + device.id} device={device} sample={demo ? sample : undefined} />)}
    </div>
  );
}

function Room({ device, sample }: { device: Device; sample?: ReturnType<typeof sampleRoom> }) {
  const { href } = useExperience();
  const [expanded, setExpanded] = useState(false);
  const [range, setRange] = useState<RangeKey>("24h");
  const recent = useMemo(() => rangeParams("24h"), []);
  const detail = useMemo(() => range === "24h" ? recent : rangeParams(range), [range, recent]);
  const devicePath = "/devices/" + encodeURIComponent(device.id);

  const current = useQuery({
    queryKey: ["current", device.id],
    queryFn: () => api<Current>(devicePath + "/current"),
    enabled: !sample,
    retry: 1,
  });
  const recentReadings = useQuery({
    queryKey: ["series", device.id, "24h"],
    queryFn: () => api<ProbeReading[]>(devicePath + "/series?" + recent.qs + "&bucket=" + RANGES["24h"].bucket),
    enabled: !sample,
    retry: 1,
  });
  const longerReadings = useQuery({
    queryKey: ["series", device.id, range],
    queryFn: () => api<ProbeReading[]>(devicePath + "/series?" + detail.qs + "&bucket=" + RANGES[range].bucket),
    enabled: !sample && expanded && range !== "24h",
    retry: 1,
  });
  const events = useQuery({
    queryKey: ["events", device.id, range],
    queryFn: () => api<Event[]>(devicePath + "/events?" + detail.qs),
    enabled: !sample && expanded,
    retry: 1,
  });

  const measurement = sample?.current ?? current.data;
  const worst = measurement?.probes.reduce<ProbeReading | undefined>(
    (a, b) => !a || b.rh_surf > a.rh_surf ? b : a,
    undefined,
  );
  const state = device.online && worst && !current.isError ? measurement?.state ?? "STALE" : "STALE";
  const value = state !== "STALE" ? worst : undefined;
  const forecast = value ? measurement?.forecast : null;
  const detailReadings = range === "24h" ? recentReadings : longerReadings;
  const trend = sample?.series ?? recentReadings.data;
  const detailSeries = sample?.series ?? detailReadings.data;

  return (
    <section className="quick-room" aria-label={device.label || device.id}>
      <div className="quick-room-heading">
        <div>
          <h2>{device.label || device.id}</h2>
          {device.location_tag && <p>{device.location_tag}</p>}
        </div>
        <UpdatedAt time={worst?.time ?? device.last_seen} sample={!!sample} online={!!value} />
      </div>

      <div className={state.toLowerCase()}>
        <section className="status-card quick-status" aria-label="현재 위험 상태">
          <div className="quick-status-copy">
            <StateBadge state={state} />
            <p>{ACTIONS[state]}</p>
          </div>
          <div className="quick-humidity">
            <span>벽면 습도</span>
            <strong>{value ? fmt(value.rh_surf, 0) + "%" : "—"}</strong>
          </div>
        </section>
      </div>

      {forecast && (
        <p className="quick-forecast" role="status">
          약 {forecast.hours_low.toFixed(1)}~{forecast.hours_high.toFixed(1)}시간 뒤{" "}
          {forecast.target < 100 ? "곰팡이 위험 구간" : "결로 구간"} 진입 예상
        </p>
      )}

      <section className="glass-panel quick-trend" aria-label="최근 24시간 벽면 온도 추이">
        <div className="quick-trend-heading">
          <h3>벽면 온도 추이</h3>
          <span>최근 24시간</span>
        </div>
        {recentReadings.isError && !sample ? (
          <div className="quick-chart-message" role="alert">
            온도 기록을 불러오지 못했어요.
            <button className="text-link" onClick={() => recentReadings.refetch()}>다시 시도</button>
          </div>
        ) : trend ? (
          <RiskChart series={trend} events={[]} from={recent.from} to={recent.to} height={112} compact />
        ) : (
          <p className="quick-chart-message" role="status">온도 기록을 불러오는 중…</p>
        )}
        {!!trend?.length && (
          <ul className="quick-legend" aria-label="그래프 범례">
            <li><i className="wall-line" />벽면 온도</li>
            <li><i className="risk-line" />곰팡이 기준</li>
            <li><i className="dew-line" />이슬점</li>
          </ul>
        )}
      </section>

      <dl className="quick-metrics glass-panel">
        <Metric label="실내 온도" value={value?.t_air} unit="°C" />
        <Metric label="실내 습도" value={value?.rh} unit="%" />
        <Metric label="벽면 온도" value={value?.t_surf} unit="°C" />
      </dl>

      <div className="quick-more">
        <details className="glass-panel quick-details" onToggle={(event) => setExpanded(event.currentTarget.open)}>
          <summary>상세 그래프와 상태 기록</summary>
          {expanded && (
            <div className="quick-details-content">
              <p>결로까지 온도 여유 <strong>{value ? fmt(value.t_surf - value.t_dew) + "°C" : "—"}</strong></p>
              {!sample && (
                <div className="range-tabs" role="group" aria-label="상세 그래프 조회 기간">
                  {(["24h", "7d", "30d"] as const).map((period, index) => (
                    <button key={period} aria-pressed={range === period} onClick={() => setRange(period)}>
                      {["24시간", "7일", "30일"][index]}
                    </button>
                  ))}
                </div>
              )}
              {detailReadings.isError && !sample ? (
                <p role="alert">상세 기록을 불러오지 못했어요. <button className="text-link" onClick={() => detailReadings.refetch()}>다시 시도</button></p>
              ) : detailSeries ? (
                <RiskChart series={detailSeries} events={sample ? [] : events.data ?? []} from={detail.from} to={detail.to} height={245} />
              ) : (
                <p role="status">상세 기록을 불러오는 중…</p>
              )}
              <h4>최근 상태 변화</h4>
              {!sample && events.isError ? <p>상태 기록을 불러오지 못했어요.</p>
                : !sample && events.isPending ? <p>상태 기록을 불러오는 중…</p>
                : !sample && events.data?.length ? (
                  <ol className="quick-events">
                    {events.data.slice(-3).reverse().map((event) => (
                      <li key={event.id}>
                        <StateBadge state={event.state} />
                        <span>{clock(event.started_at)} — {event.ended_at ? clock(event.ended_at) : "진행 중"}</span>
                      </li>
                    ))}
                  </ol>
                ) : <p>이 기간에 기록된 상태 변화가 없어요.</p>}
            </div>
          )}
        </details>
        <Link className="quick-report-link" href={href("/report/")}>리포트 보기 <Icon name="arrow" /></Link>
      </div>
    </section>
  );
}

function Metric({ label, value, unit }: { label: string; value?: number; unit: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{fmt(value)}{value != null && <span>{unit}</span>}</dd>
    </div>
  );
}

function UpdatedAt({ time, sample, online }: { time: string | null; sample: boolean; online: boolean }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (sample) return;
    const timer = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(timer);
  }, [sample]);

  if (sample) return <span className="quick-updated">샘플 데이터</span>;

  const timestamp = time ? Date.parse(time) : NaN;
  const minutes = Number.isFinite(timestamp) ? Math.max(0, Math.floor((now - timestamp) / 60_000)) : null;
  let ago = "수신 기록 없음";
  if (minutes != null) {
    if (minutes < 1) ago = "방금 갱신";
    else if (minutes < 60) ago = minutes + "분 전";
    else if (minutes < 1440) ago = Math.floor(minutes / 60) + "시간 전";
    else ago = Math.floor(minutes / 1440) + "일 전";
  }

  return (
    <span className="quick-updated" role="status" title={time ? new Date(time).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" }) : undefined}>
      {!online && "연결 확인 · "}{ago}
    </span>
  );
}
