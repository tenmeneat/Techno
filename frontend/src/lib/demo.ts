import type { Current, Device, ProbeReading, StateName } from "./api";

// Only used after the user explicitly selects the sample view. Never placed in API caches.
export function sampleRoom(state: StateName, now: number) {
  const humidity = { SAFE: 64, WATCH: 76, ALERT: 87, CONDENSING: 101, STALE: 64 }[state];
  const dew = 12.7;
  const surface = 243.12 * (Math.log(100 / humidity) + 17.62 * dew / (243.12 + dew)) / (17.62 - Math.log(100 / humidity) - 17.62 * dew / (243.12 + dew));
  const series: ProbeReading[] = Array.from({ length: 97 }, (_, i) => ({
    time: new Date(now - (96 - i) * 900_000).toISOString(), probe_id: "sample-wall",
    t_air: 22.4, rh: 54, t_dew: dew, t80: 16.1,
    t_surf: surface + (Math.sin(i / 9) - Math.sin(96 / 9)) * 0.8 + (96 - i) * 0.008,
    rh_surf: humidity,
  }));
  const device: Device = { id: "sample-room", home_id: "sample", label: "나의 방", location_tag: "북향 외벽 · 창가", online: state !== "STALE", last_seen: new Date(now).toISOString(), state, fw: "sample", calib_t_air: 0, calib_rh: 0, calib_t_surf: 0 };
  const current: Current = { device_id: device.id, state, probes: [series[96]], forecast: null };
  return { device, current, series };
}
