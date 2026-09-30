// 타입은 백엔드 OpenAPI에서 생성된다 (§11.1). 스펙이 바뀌면 `npm run gen:api`.
import type { components } from "./openapi";

type S = components["schemas"];
export type Device = S["Device"];
export type Current = S["Current"];
export type ProbeReading = S["ProbeReading"];
export type Event = S["Event"];
export type Diagnostic = S["Diagnostic"];
export type Report = S["Report"];
export type StateName = Device["state"];

export type LiveMessage =
  | ({ type: "reading" } & Current)
  | { type: "state"; device_id: string; state: StateName; at: string };

// 배포 시 비움 = 같은 출처(FastAPI가 프런트를 서빙). 로컬 `npm run dev`는 .env.local에서 http://localhost:8000
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";
const TOKEN = process.env.NEXT_PUBLIC_API_TOKEN ?? "";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}/api/v1${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(TOKEN && { Authorization: `Bearer ${TOKEN}` }),
      ...init?.headers,
    },
  });
  if (!res.ok) throw new Error(`${res.status} ${path}`);
  return res.status === 204 ? (undefined as T) : res.json();
}

export const post = <T>(path: string, body: unknown, method = "POST") =>
  api<T>(path, { method, body: JSON.stringify(body) });

export const wsUrl = (deviceId = "*") =>
  `${(API_URL || location.origin).replace(/^http/, "ws")}/ws/live?device_id=${encodeURIComponent(deviceId)}&token=${TOKEN}`;

// 대시보드 기간 → 요청 버킷 (§10.3). 원본 30초 샘플은 요청하지 않는다
export const RANGES = {
  "24h": { hours: 24, bucket: "1m" },
  "7d": { hours: 24 * 7, bucket: "1h" },
  "30d": { hours: 24 * 30, bucket: "1h" },
} as const;
export type RangeKey = keyof typeof RANGES;

export function rangeParams(range: RangeKey) {
  const to = Date.now();
  const from = to - RANGES[range].hours * 3600_000;
  return { from, to, qs: `from=${new Date(from).toISOString()}&to=${new Date(to).toISOString()}` };
}
