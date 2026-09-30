import type { StateName } from "./api";

export const STATE: Record<StateName, { label: string; cls: string; color: string }> = {
  SAFE: { label: "안전", cls: "bg-emerald-100 text-emerald-800", color: "#10b981" },
  WATCH: { label: "주의", cls: "bg-yellow-100 text-yellow-800", color: "#eab308" },
  ALERT: { label: "곰팡이 위험", cls: "bg-orange-100 text-orange-800", color: "#f97316" },
  CONDENSING: { label: "결로 발생", cls: "bg-red-100 text-red-800", color: "#dc2626" },
  STALE: { label: "연결 확인", cls: "bg-gray-200 text-gray-700", color: "#9ca3af" },
};

// §4.4 표현 기준. '하자', '임대인 책임' 같은 문구는 쓰지 않는다
export function fRsiLabel(f: number | null | undefined) {
  if (f == null) return "산출 조건 미달";
  if (f >= 0.85) return "단열 상태 양호";
  if (f >= 0.75) return "보통";
  if (f >= 0.7) return "경계 — 설계기준 부근";
  return "국제 관행 기준 미달 — 환기만으로는 해결되지 않는 구조적 요인 가능성";
}

export const F_RSI_MIN = 0.7;

export const fmt = (v: number | null | undefined, digits = 1) => (v == null ? "—" : v.toFixed(digits));
export const hhmm = (t: number | string) =>
  new Date(t).toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
