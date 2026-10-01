"use client";
// 기기 · 알림 설정 (§10.2): 알림 켜기/무음 시간, 기기 이름·위치, 캘리브레이션 오프셋
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { StateBadge } from "@/components/StateBadge";
import { api, type Device, post } from "@/lib/api";
import { hhmm, STATE } from "@/lib/format";
import { enableNotifications } from "@/lib/notifications";

// §8.3 부착 위치 우선순위
const LOCATIONS = ["외벽 하부 모서리", "창틀 하단", "외벽·내벽 수직 모서리", "옷장 뒤 벽"];

export default function SettingsPage() {
  const devices = useQuery({ queryKey: ["devices"], queryFn: () => api<Device[]>("/devices") }).data ?? [];
  return (
    <div className="grid gap-6">
      <header>
        <h1 className="text-2xl font-bold tracking-tight md:text-3xl">기기 · 알림 설정</h1>
        <p className="mt-1 text-sm text-slate-500">위험할 때 알림을 받을 방법과, 방에 설치한 센서의 이름·위치를 정합니다.</p>
      </header>

      <div className="grid gap-6 xl:grid-cols-5">
        <div className="xl:col-span-2"><NotificationCard /></div>
        <div className="grid content-start gap-6 xl:col-span-3">
          <h2 className="-mb-2 text-sm font-semibold text-slate-500">설치된 기기 {devices.length}대</h2>
          {devices.map((d) => <DeviceCard key={d.id} device={d} />)}
          {!devices.length && (
            <p className="rounded-2xl bg-white p-6 text-sm text-slate-500 ring-1 ring-slate-200">
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

function NotificationCard() {
  const [perm, setPerm] = useState<Perm>("default");
  const [quiet, setQuiet] = useState({ start: 23, end: 7 });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    setPerm(typeof Notification === "undefined" || !("serviceWorker" in navigator) ? "unsupported" : Notification.permission);
  }, []);

  const apply = async () => {
    setBusy(true);
    setMsg("");
    const ok = await enableNotifications(quiet.start, quiet.end).catch(() => false);
    setPerm(typeof Notification === "undefined" ? "unsupported" : Notification.permission);
    setMsg(ok ? "저장했습니다. 이제 위험할 때 알림이 옵니다." : "알림을 켜지 못했습니다. 브라우저 설정에서 알림을 허용해 주세요.");
    setBusy(false);
  };

  const on = perm === "granted";
  const status = {
    granted: { t: "알림 켜짐", d: "이 기기로 알림을 받고 있습니다.", c: "bg-green-50 text-green-800 ring-green-600/20" },
    default: { t: "알림 꺼짐", d: "아래 버튼을 눌러 알림을 허용하세요.", c: "bg-slate-100 text-slate-700 ring-slate-300" },
    denied: { t: "알림 차단됨", d: "브라우저 주소창 왼쪽 자물쇠 → 알림 → 허용으로 바꿔주세요.", c: "bg-red-50 text-red-800 ring-red-600/20" },
    unsupported: { t: "지원 안 됨", d: "이 브라우저는 알림을 지원하지 않습니다. 아이폰은 홈 화면에 추가한 뒤 사용하세요.", c: "bg-amber-50 text-amber-800 ring-amber-500/30" },
  }[perm];

  return (
    <section className="rounded-2xl bg-white shadow-sm ring-1 ring-slate-200">
      <div className="flex items-center justify-between gap-3 border-b border-slate-100 p-5 md:p-6">
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-blue-50 text-blue-700" aria-hidden>
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.9 1.9 0 0 0 3.4 0" />
            </svg>
          </span>
          <div>
            <h2 className="font-semibold">알림</h2>
            <p className="text-xs text-slate-500">{status.d}</p>
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
          <p className="mb-3 text-xs text-slate-500">이 시간에는 결로 알림만 보냅니다.</p>
          <div className="flex items-center gap-2">
            <HourSelect value={quiet.start} onChange={(v) => setQuiet({ ...quiet, start: v })} label="무음 시작" />
            <span className="text-slate-400">부터</span>
            <HourSelect value={quiet.end} onChange={(v) => setQuiet({ ...quiet, end: v })} label="무음 끝" />
            <span className="text-slate-400">까지</span>
          </div>
        </div>

        <div>
          <button onClick={apply} disabled={busy || perm === "unsupported"}
            className="w-full rounded-xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:opacity-40">
            {busy ? "설정 중…" : on ? "무음 시간 저장" : "알림 켜기"}
          </button>
          {msg && <p className="mt-2 text-center text-sm text-slate-600" role="status">{msg}</p>}
        </div>

        <div className="flex gap-3 rounded-xl bg-slate-50 p-4 text-xs leading-relaxed text-slate-600">
          <span className="text-base" aria-hidden>📱</span>
          <p><b className="text-slate-800">아이폰 사용자</b>는 Safari 아래쪽 공유 버튼 → “홈 화면에 추가”로 앱을 설치한 뒤, 그 앱에서 알림을 켜야 알림이 옵니다.</p>
        </div>
      </div>
    </section>
  );
}

const Rule = ({ color, title, desc }: { color: string; title: string; desc: string }) => (
  <li className="flex items-start gap-3 rounded-xl bg-slate-50 px-4 py-3">
    <span className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: color }} aria-hidden />
    <div>
      <div className="text-sm font-medium">{title}</div>
      <div className="text-xs text-slate-500">{desc}</div>
    </div>
  </li>
);

const HourSelect = ({ value, onChange, label }: { value: number; onChange: (v: number) => void; label: string }) => (
  <select aria-label={label} value={value} onChange={(e) => onChange(+e.target.value)}
    className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium tabular-nums focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20">
    {Array.from({ length: 24 }, (_, h) => (
      <option key={h} value={h}>{h < 12 ? "오전" : "오후"} {h % 12 || 12}시</option>
    ))}
  </select>
);

/* ───────── 기기 ───────── */

function DeviceCard({ device }: { device: Device }) {
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
      await post(`/devices/${device.id}`, { label: f.label, location_tag: f.location_tag }, "PATCH");
      await post(`/devices/${device.id}/calibration`, { t_air: f.t_air, rh: f.rh, t_surf: f.t_surf });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["devices"] }),
  });
  const calibrated = device.calib_t_air || device.calib_rh || device.calib_t_surf;

  return (
    <section className="rounded-2xl bg-white shadow-sm ring-1 ring-slate-200">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 p-5 md:px-6">
        <div className="flex items-center gap-3">
          <span className="relative grid h-10 w-10 place-items-center rounded-xl bg-slate-100 text-slate-600" aria-hidden>
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
              <rect x="6" y="3" width="12" height="18" rx="2" /><path d="M10 7h4M12 15v.01" />
            </svg>
            <span className={`absolute -right-0.5 -top-0.5 h-3 w-3 rounded-full ring-2 ring-white ${device.online ? "bg-green-500" : "bg-slate-300"}`} />
          </span>
          <div>
            <h3 className="font-semibold">{device.label || device.id}</h3>
            <p className="text-xs text-slate-500">
              {device.online ? "연결됨" : "연결 끊김"}
              {device.last_seen && ` · 마지막 수신 ${hhmm(device.last_seen)}`}
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
              className={`rounded-full px-3 py-1 text-xs ring-1 ring-inset transition ${f.location_tag === l ? "bg-blue-50 text-blue-700 ring-blue-300" : "text-slate-600 ring-slate-200 hover:bg-slate-50"}`}>
              {l}
            </button>
          ))}
        </div>

        <details className="group rounded-xl bg-slate-50 px-4 py-3">
          <summary className="flex cursor-pointer list-none items-center justify-between text-sm font-medium">
            <span><span className="mr-1 inline-block text-slate-400 transition group-open:rotate-90">›</span> 센서 보정값 <span className="text-xs font-normal text-slate-400">(고급)</span></span>
            <span className={`text-xs ${calibrated ? "text-green-700" : "text-slate-400"}`}>{calibrated ? "보정 적용됨" : "보정 전"}</span>
          </summary>
          <p className="mt-2 text-xs leading-relaxed text-slate-500">
            여러 기기를 같은 자리에 24시간 두고 잰 차이를 입력합니다(§8.4). 측정값에 이 값을 더해서 계산합니다. 잘 모르면 0으로 두세요.
          </p>
          <div className="mt-3 grid grid-cols-3 gap-3">
            <Offset label="공기 온도" unit="℃" value={f.t_air} onChange={(v) => set("t_air", v)} />
            <Offset label="공기 습도" unit="%p" value={f.rh} onChange={(v) => set("rh", v)} />
            <Offset label="벽면 온도" unit="℃" value={f.t_surf} onChange={(v) => set("t_surf", v)} />
          </div>
        </details>

        <div className="flex items-center justify-end gap-3">
          <span className="text-xs text-slate-400">ID {device.id} · 펌웨어 {device.fw ?? "—"}</span>
          {save.isSuccess && !dirty && <span className="text-sm text-green-700" role="status">저장됨 ✓</span>}
          {save.isError && <span className="text-sm text-red-700" role="status">저장 실패</span>}
          <button onClick={() => save.mutate()} disabled={!dirty || save.isPending}
            className="rounded-xl bg-slate-900 px-5 py-2 text-sm font-semibold text-white transition hover:bg-slate-700 disabled:bg-slate-200 disabled:text-slate-400">
            {save.isPending ? "저장 중…" : "저장"}
          </button>
        </div>
      </div>
    </section>
  );
}

const INPUT = "w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm placeholder:text-slate-300 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20";

const Field = ({ label, hint, children }: { label: string; hint: string; children: React.ReactNode }) => (
  <label className="grid gap-1">
    <span className="text-sm font-medium">{label} <span className="text-xs font-normal text-slate-400">{hint}</span></span>
    {children}
  </label>
);

const Offset = ({ label, unit, value, onChange }: { label: string; unit: string; value: number; onChange: (v: number) => void }) => (
  <label className="grid gap-1 text-xs text-slate-500">
    {label}
    <span className="relative">
      <input type="number" step="0.1" value={value} onChange={(e) => onChange(+e.target.value)}
        className={`${INPUT} pr-9 tabular-nums`} />
      <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-400">{unit}</span>
    </span>
  </label>
);
