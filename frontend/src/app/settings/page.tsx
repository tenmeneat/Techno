"use client";
// 기기 · 알림 설정 (§10.2): 알림 켜기/무음 시간, 기기 이름·위치, 캘리브레이션 오프셋
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { StateBadge } from "@/components/StateBadge";
import { ExperienceChoice, useExperience } from "@/components/Experience";
import { api, type Device, post } from "@/lib/api";
import { sampleRoom } from "@/lib/demo";
import { hhmm, STATE } from "@/lib/format";
import { enableNotifications } from "@/lib/notifications";

// §8.3 부착 위치 우선순위
const LOCATIONS = ["외벽 하부 모서리", "창틀 하단", "외벽·내벽 수직 모서리", "옷장 뒤 벽"];

export default function SettingsPage() {
  const { mode, ready, setMode } = useExperience();
  const [sampleDevice] = useState(() => sampleRoom("SAFE", Date.now()).device);
  const devicesQuery = useQuery({
    queryKey: ["devices"], queryFn: () => api<Device[]>("/devices"),
    enabled: ready && mode === "live", retry: 1,
  });
  const demo = mode === "demo";
  const devices = demo ? [sampleDevice] : devicesQuery.data ?? [];

  if (!ready) return <div className="settings-page glass-panel rounded-2xl p-6 text-sm text-slate-600" role="status">설정 화면을 준비하고 있어요…</div>;
  if (mode === "welcome") return <ExperienceChoice />;

  return (
    <div className="settings-page grid gap-6">
      <header className="dashboard-heading">
        <div>
          <h1>내 공간에 맞게 설정해요<span>.</span></h1>
          <p>위험 알림을 받을 방법과 센서의 이름·위치를 정합니다.</p>
        </div>
        <button className="button secondary" type="button" onClick={() => setMode(demo ? "live" : "demo")}>
          {demo ? "실제 기기로 전환" : "샘플 설정 보기"}
        </button>
      </header>

      {demo && <div className="demo-banner" role="status"><div><strong>샘플 설정</strong><span>화면 체험용 가상 기기입니다. 입력값을 둘러볼 수 있지만 저장하거나 알림을 신청하지는 않습니다.</span></div></div>}

      <div className="grid gap-6 xl:grid-cols-5">
        <div className="xl:col-span-2"><NotificationCard key={mode} demo={demo} serverReady={devicesQuery.isSuccess} /></div>
        <div className="grid content-start gap-6 xl:col-span-3">
          <h2 className="-mb-2 text-sm font-semibold text-slate-600">{demo ? "샘플 기기" : "설치된 기기"}{(demo || devicesQuery.isSuccess) && ` ${devices.length}대`}</h2>
          {!demo && devicesQuery.isPending && <p className="glass-panel rounded-2xl p-6 text-sm text-slate-600" role="status">연결된 기기를 불러오고 있어요…</p>}
          {!demo && devicesQuery.isError && <div className="glass-panel grid gap-3 rounded-2xl p-6 text-sm text-slate-700" role="alert">
            <p className="font-semibold">기기 목록을 불러오지 못했어요</p>
            <p className="leading-relaxed">서버 연결을 확인한 뒤 다시 시도해 주세요. 연결 전에는 기기 저장과 알림 설정을 사용할 수 없어요.</p>
            <button className="button secondary justify-self-start" type="button" onClick={() => devicesQuery.refetch()} disabled={devicesQuery.isFetching}>{devicesQuery.isFetching ? "확인 중…" : "다시 확인"}</button>
          </div>}
          {(demo || !devicesQuery.isError) && devices.map((d) => <DeviceCard key={`${mode}-${d.id}`} device={d} demo={demo} />)}
          {!demo && devicesQuery.isSuccess && !devices.length && (
            <p className="glass-panel rounded-2xl p-6 text-sm leading-relaxed text-slate-600">
              아직 기기가 없습니다. 센서 전원을 켜고 Wi‑Fi에 연결되면 여기에 자동으로 나타납니다.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

/* ───────── 알림 ───────── */

type Perm = NotificationPermission | "unsupported";

function NotificationCard({ demo, serverReady }: { demo: boolean; serverReady: boolean }) {
  const [perm, setPerm] = useState<Perm>("default");
  const [quiet, setQuiet] = useState({ start: 23, end: 7 });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [configured, setConfigured] = useState(false);

  useEffect(() => {
    setPerm(typeof Notification === "undefined" || !("serviceWorker" in navigator) ? "unsupported" : Notification.permission);
  }, []);

  const apply = async () => {
    if (demo || !serverReady) return;
    setBusy(true);
    setMsg("");
    const ok = await enableNotifications(quiet.start, quiet.end).catch(() => false);
    setPerm(typeof Notification === "undefined" ? "unsupported" : Notification.permission);
    setMsg(ok ? "저장했습니다. 이제 위험할 때 알림이 옵니다." : "알림을 켜지 못했습니다. 브라우저 설정에서 알림을 허용해 주세요.");
    setConfigured(ok);
    setBusy(false);
  };

  const on = perm === "granted";
  const status = demo
    ? { t: "샘플", d: "알림 화면을 미리 살펴보세요. 실제 알림은 발송되지 않습니다.", c: "bg-indigo-50 text-indigo-800 ring-indigo-400/30" }
    : {
    granted: { t: configured ? "알림 설정 완료" : "알림 권한 허용됨", d: configured ? "이 기기의 알림 구독을 서버에 저장했습니다." : "아래 버튼으로 알림 구독과 무음 시간을 서버에 저장하세요.", c: "bg-green-50 text-green-800 ring-green-600/20" },
    default: { t: "알림 꺼짐", d: "아래 버튼을 눌러 알림을 허용하세요.", c: "bg-slate-100 text-slate-700 ring-slate-300" },
    denied: { t: "알림 차단됨", d: "브라우저 주소창 왼쪽 자물쇠 → 알림 → 허용으로 바꿔주세요.", c: "bg-red-50 text-red-800 ring-red-600/20" },
    unsupported: { t: "지원 안 됨", d: "이 브라우저는 알림을 지원하지 않습니다. 아이폰은 홈 화면에 추가한 뒤 사용하세요.", c: "bg-amber-50 text-amber-800 ring-amber-500/30" },
  }[perm];

  return (
    <section className="glass-panel rounded-2xl">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200/60 p-5 md:p-6">
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-blue-50 text-blue-700" aria-hidden>
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.9 1.9 0 0 0 3.4 0" />
            </svg>
          </span>
          <div>
            <h2 className="font-semibold">알림</h2>
            <p className="mt-1 text-sm leading-relaxed text-slate-600">{status.d}</p>
          </div>
        </div>
        <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset ${status.c}`}>{status.t}</span>
      </div>

      <div className="grid gap-6 p-5 md:p-6">
        <div>
          <h3 className="mb-3 text-sm font-semibold">이럴 때 알려드려요</h3>
          <ul className="grid gap-2">
            <Rule color={STATE.ALERT.color} title="곰팡이 위험" desc="벽면 습도가 80%를 10분 넘게 유지될 때" />
            <Rule color={STATE.CONDENSING.color} title="결로 발생" desc="벽에 물이 맺히는 조건일 때 · 무음 시간에도 알림" />
            <Rule color="#2a78d6" title="예보" desc="1~2시간 안에 위험해질 것 같을 때 · 하루 최대 2번" />
          </ul>
        </div>

        <div>
          <h3 className="text-sm font-semibold">무음 시간</h3>
          <p className="mb-3 text-sm text-slate-600">이 시간에는 결로 알림만 보냅니다.</p>
          <div className="flex flex-wrap items-center gap-2">
            <HourSelect value={quiet.start} onChange={(v) => setQuiet({ ...quiet, start: v })} label="무음 시작" />
            <span className="text-slate-400">부터</span>
            <HourSelect value={quiet.end} onChange={(v) => setQuiet({ ...quiet, end: v })} label="무음 끝" />
            <span className="text-slate-400">까지</span>
          </div>
        </div>

        <div>
          <button type="button" onClick={apply} disabled={demo || !serverReady || busy || perm === "unsupported"}
            className="button primary w-full">
            {demo ? "샘플 알림 신청 불가" : busy ? "설정 중…" : on ? "알림 · 무음 시간 저장" : "알림 켜기"}
          </button>
          {(demo || !serverReady) && <p className="mt-3 text-sm leading-relaxed text-slate-600">{demo ? "샘플 체험 중에는 알림 권한을 요청하지 않습니다. 실제 알림 설정은 서버 연결 후 사용할 수 있어요." : "실제 서버 연결을 확인한 뒤 알림을 설정할 수 있어요."}</p>}
          {msg && <p className="mt-2 text-center text-sm text-slate-600" role="status">{msg}</p>}
        </div>

        <div className="flex gap-3 rounded-xl border border-white/80 bg-white/45 p-4 text-sm leading-relaxed text-slate-600">
          <span className="text-base" aria-hidden>📱</span>
          <p><b className="text-slate-800">아이폰 사용자</b>는 Safari 아래쪽 공유 버튼 → “홈 화면에 추가”로 앱을 설치한 뒤, 그 앱에서 알림을 켜야 알림이 옵니다.</p>
        </div>
      </div>
    </section>
  );
}

const Rule = ({ color, title, desc }: { color: string; title: string; desc: string }) => (
  <li className="flex items-start gap-3 rounded-xl border border-white/80 bg-white/45 px-4 py-3">
    <span className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: color }} aria-hidden />
    <div>
      <div className="text-sm font-medium">{title}</div>
      <div className="mt-1 text-sm leading-relaxed text-slate-600">{desc}</div>
    </div>
  </li>
);

const HourSelect = ({ value, onChange, label }: { value: number; onChange: (v: number) => void; label: string }) => (
  <select aria-label={label} value={value} onChange={(e) => onChange(+e.target.value)}
    className="min-h-11 rounded-lg border border-slate-300 bg-white/70 px-3 py-2 text-sm font-medium tabular-nums focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20">
    {Array.from({ length: 24 }, (_, h) => (
      <option key={h} value={h}>{h < 12 ? "오전" : "오후"} {h % 12 || 12}시</option>
    ))}
  </select>
);

/* ───────── 기기 ───────── */

function DeviceCard({ device, demo }: { device: Device; demo: boolean }) {
  const qc = useQueryClient();
  const initial = {
    label: device.label ?? "", location_tag: device.location_tag ?? "",
    t_air: device.calib_t_air, rh: device.calib_rh, t_surf: device.calib_t_surf,
  };
  const [f, setF] = useState(initial);
  const dirty = JSON.stringify(f) !== JSON.stringify(initial);
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF({ ...f, [k]: v });

  const save = useMutation({
    mutationFn: async () => {
      if (demo) return;
      await post(`/devices/${device.id}`, { label: f.label, location_tag: f.location_tag }, "PATCH");
      await post(`/devices/${device.id}/calibration`, { t_air: f.t_air, rh: f.rh, t_surf: f.t_surf });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["devices"] }),
  });
  const calibrated = device.calib_t_air || device.calib_rh || device.calib_t_surf;

  return (
    <section className="glass-panel rounded-2xl">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200/60 p-5 md:px-6">
        <div className="flex items-center gap-3">
          <span className="relative grid h-10 w-10 place-items-center rounded-xl bg-slate-100 text-slate-600" aria-hidden>
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
              <rect x="6" y="3" width="12" height="18" rx="2" /><path d="M10 7h4M12 15v.01" />
            </svg>
            <span className={`absolute -right-0.5 -top-0.5 h-3 w-3 rounded-full ring-2 ring-white ${!demo && device.online ? "bg-green-500" : "bg-slate-300"}`} />
          </span>
          <div>
            <h3 className="font-semibold">{device.label || device.id}</h3>
            <p className="mt-1 text-sm leading-relaxed text-slate-600">
              {demo ? "샘플 기기 · 실제 연결 없음" : device.online ? "연결됨" : "연결 끊김"}
              {!demo && device.last_seen && ` · 마지막 수신 ${hhmm(device.last_seen)}`}
            </p>
          </div>
        </div>
        <StateBadge state={device.state} />
      </div>

      <div className="grid gap-5 p-5 md:px-6">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="이름" hint="예: 북향 방, 침실">
            <input className={INPUT} value={f.label} placeholder={device.id} onChange={(e) => set("label", e.target.value)} />
          </Field>
          <Field label="설치 위치" hint="벽 어디에 붙였나요?">
            <input className={INPUT} value={f.location_tag} placeholder="직접 입력" onChange={(e) => set("location_tag", e.target.value)} />
          </Field>
        </div>
        <div className="-mt-2 flex flex-wrap gap-1.5">
          {LOCATIONS.map((l) => (
            <button key={l} type="button" onClick={() => set("location_tag", l)}
              aria-pressed={f.location_tag === l}
              className={`min-h-11 rounded-full px-3 py-2 text-sm ring-1 ring-inset transition ${f.location_tag === l ? "bg-blue-50 text-blue-800 ring-blue-300" : "text-slate-600 ring-slate-300 hover:bg-white/60"}`}>
              {l}
            </button>
          ))}
        </div>

        <details className="group rounded-xl border border-white/80 bg-white/45 px-4 py-3">
          <summary className="flex cursor-pointer list-none items-center justify-between text-sm font-medium">
            <span><span className="mr-1 inline-block text-slate-500 transition group-open:rotate-90">›</span> 센서 보정값 <span className="text-sm font-normal text-slate-600">(고급)</span></span>
            <span className={`text-sm ${calibrated ? "text-green-800" : "text-slate-600"}`}>{calibrated ? "보정 적용됨" : "보정 전"}</span>
          </summary>
          <p className="mt-3 text-sm leading-relaxed text-slate-600">
            여러 기기를 같은 자리에 24시간 두고 잰 차이를 입력합니다. 측정값에 이 값을 더해서 계산합니다. 보정값을 모르면 0으로 두세요.
          </p>
          <div className="mt-3 grid grid-cols-3 gap-3">
            <Offset label="공기 온도" unit="℃" value={f.t_air} onChange={(v) => set("t_air", v)} />
            <Offset label="공기 습도" unit="%p" value={f.rh} onChange={(v) => set("rh", v)} />
            <Offset label="벽면 온도" unit="℃" value={f.t_surf} onChange={(v) => set("t_surf", v)} />
          </div>
        </details>

        {demo && <p className="text-sm leading-relaxed text-slate-600">샘플에서 바꾼 이름·위치·보정값은 저장되지 않습니다. 실제 기기 설정은 서버 연결 후 사용할 수 있어요.</p>}
        <div className="flex flex-wrap items-center justify-end gap-3">
          <span className="mr-auto text-sm text-slate-600">{demo ? "체험용 기기" : `ID ${device.id} · 펌웨어 ${device.fw ?? "—"}`}</span>
          {save.isSuccess && !dirty && <span className="text-sm text-green-700" role="status">저장됨 ✓</span>}
          {save.isError && <span className="text-sm text-red-700" role="status">저장 실패</span>}
          <button type="button" onClick={() => save.mutate()} disabled={demo || !dirty || save.isPending}
            className="button primary">
            {demo ? "샘플 저장 불가" : save.isPending ? "저장 중…" : "저장"}
          </button>
        </div>
      </div>
    </section>
  );
}

const INPUT = "min-h-11 w-full min-w-0 rounded-lg border border-slate-300 bg-white/70 px-3 py-2 text-sm text-slate-800 placeholder:text-slate-500 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20";

const Field = ({ label, hint, children }: { label: string; hint: string; children: React.ReactNode }) => (
  <label className="grid gap-1">
    <span className="text-sm font-medium text-slate-700">{label} <span className="text-sm font-normal text-slate-600">{hint}</span></span>
    {children}
  </label>
);

const Offset = ({ label, unit, value, onChange }: { label: string; unit: string; value: number; onChange: (v: number) => void }) => (
  <label className="grid min-w-0 gap-2 text-sm text-slate-600">
    {label}
    <span className="relative">
      <input type="number" step="0.1" value={value} onChange={(e) => onChange(+e.target.value)}
        className={`${INPUT} pr-9 tabular-nums`} />
      <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-slate-600">{unit}</span>
    </span>
  </label>
);
