"use client";
// 기기 관리 (§10.2): 라벨·위치 태그, 캘리브레이션 offset, 알림 설정
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type Device, post } from "@/lib/api";
import { enableNotifications } from "@/lib/notifications";

export default function SettingsPage() {
  const devices = useQuery({ queryKey: ["devices"], queryFn: () => api<Device[]>("/devices") }).data ?? [];
  return (
    <div className="grid gap-4">
      <NotificationSettings />
      {devices.map((d) => <DeviceForm key={d.id} device={d} />)}
    </div>
  );
}

function NotificationSettings() {
  const [quiet, setQuiet] = useState({ start: 23, end: 7 });
  const [msg, setMsg] = useState("");
  const hours = Array.from({ length: 24 }, (_, h) => h);
  return (
    <section className="rounded-2xl bg-white p-4 shadow-sm">
      <h2 className="mb-2 font-semibold">알림</h2>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        무음
        <select className="rounded border p-1" value={quiet.start} onChange={(e) => setQuiet({ ...quiet, start: +e.target.value })}>
          {hours.map((h) => <option key={h} value={h}>{h}시</option>)}
        </select>
        –
        <select className="rounded border p-1" value={quiet.end} onChange={(e) => setQuiet({ ...quiet, end: +e.target.value })}>
          {hours.map((h) => <option key={h} value={h}>{h}시</option>)}
        </select>
        <button className="rounded bg-blue-700 px-3 py-1 text-white"
          onClick={async () => setMsg((await enableNotifications(quiet.start, quiet.end).catch(() => false)) ? "알림이 켜졌습니다." : "알림 권한을 받지 못했습니다.")}>
          알림 켜기
        </button>
      </div>
      <p className="mt-2 text-xs text-gray-500">결로 알림은 무음 시간에도 옵니다. 아이폰은 Safari 공유 → “홈 화면에 추가” 후 앱에서 켜야 동작합니다.</p>
      {msg && <p className="mt-1 text-sm">{msg}</p>}
    </section>
  );
}

function DeviceForm({ device }: { device: Device }) {
  const qc = useQueryClient();
  const [f, setF] = useState({
    label: device.label ?? "", location_tag: device.location_tag ?? "",
    t_air: device.calib_t_air, rh: device.calib_rh, t_surf: device.calib_t_surf,
  });
  const save = useMutation({
    mutationFn: async () => {
      await post(`/devices/${device.id}`, { label: f.label, location_tag: f.location_tag }, "PATCH");
      await post(`/devices/${device.id}/calibration`, { t_air: f.t_air, rh: f.rh, t_surf: f.t_surf });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["devices"] }),
  });
  const field = (k: keyof typeof f, label: string, num = false) => (
    <label className="grid gap-0.5 text-xs text-gray-600">
      {label}
      <input className="rounded border p-1 text-sm text-gray-900" type={num ? "number" : "text"} step="0.01" value={f[k]}
        onChange={(e) => setF({ ...f, [k]: num ? +e.target.value : e.target.value })} />
    </label>
  );
  return (
    <section className="rounded-2xl bg-white p-4 shadow-sm">
      <h2 className="mb-2 font-semibold">{device.id}</h2>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
        {field("label", "이름")}
        {field("location_tag", "위치")}
        {field("t_air", "공기온도 오프셋 K", true)}
        {field("rh", "습도 오프셋 %p", true)}
        {field("t_surf", "벽면온도 오프셋 K", true)}
      </div>
      <button className="mt-3 rounded bg-blue-700 px-3 py-1 text-sm text-white" onClick={() => save.mutate()}>
        {save.isPending ? "저장 중…" : save.isSuccess ? "저장됨" : "저장"}
      </button>
    </section>
  );
}
