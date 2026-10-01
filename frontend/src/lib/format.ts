import type { StateName } from "./api";

// 상태색은 status 팔레트 고정값(good/warning/serious/critical). 색만으로 전달하지 않도록 항상 라벨과 함께 쓴다
export const STATE: Record<StateName, { label: string; color: string; soft: string; text: string; advice: string }> = {
  SAFE: {
    label: "안전", color: "#0ca30c", soft: "bg-green-50 ring-green-600/20", text: "text-green-800",
    advice: "곰팡이가 자라기 어려운 상태입니다.",
  },
  WATCH: {
    label: "주의", color: "#fab219", soft: "bg-amber-50 ring-amber-500/30", text: "text-amber-800",
    advice: "벽면 습도가 오르고 있습니다. 환기를 준비하세요.",
  },
  ALERT: {
    label: "곰팡이 위험", color: "#ec835a", soft: "bg-orange-50 ring-orange-500/30", text: "text-orange-800",
    advice: "벽면이 곰팡이가 자라는 습도입니다. 지금 환기하세요.",
  },
  CONDENSING: {
    label: "결로 발생", color: "#d03b3b", soft: "bg-red-50 ring-red-600/30", text: "text-red-800",
    advice: "벽면에 물이 맺히고 있습니다. 즉시 환기하고 물기를 닦아주세요.",
  },
  STALE: {
    label: "연결 확인", color: "#9ca3af", soft: "bg-slate-100 ring-slate-400/30", text: "text-slate-700",
    advice: "5분 넘게 데이터가 오지 않습니다. 기기 전원과 Wi‑Fi를 확인하세요.",
  },
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
export const clock = (t: number | string) =>
  new Date(t).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });

/** §4.3 리포트 대표값: 산출된 날 중 최근 7일의 중앙값 */
export function fRsiMedian7(days: { f_rsi: number | null }[]) {
  const v = days.filter((x) => x.f_rsi != null).slice(-7).map((x) => x.f_rsi as number).sort((a, b) => a - b);
  return v.length ? v[Math.floor(v.length / 2)] : null;
}
