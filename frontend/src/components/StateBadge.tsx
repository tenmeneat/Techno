import type { StateName } from "@/lib/api";
import { STATE } from "@/lib/format";

export function StateBadge({ state }: { state: StateName }) {
  const s = STATE[state];
  return <span className={`rounded-full px-2.5 py-0.5 text-sm font-semibold ${s.cls}`}>{s.label}</span>;
}
