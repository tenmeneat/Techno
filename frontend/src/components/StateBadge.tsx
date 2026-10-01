import type { StateName } from "@/lib/api";
import { STATE } from "@/lib/format";

export function StateBadge({ state, large = false }: { state: StateName; large?: boolean }) {
  const s = STATE[state];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full font-semibold ring-1 ring-inset ${s.soft} ${s.text} ${large ? "px-3.5 py-1.5 text-base" : "px-2.5 py-0.5 text-sm"}`}>
      <span className={`rounded-full ${large ? "h-2.5 w-2.5" : "h-2 w-2"}`} style={{ background: s.color }} aria-hidden />
      {s.label}
    </span>
  );
}
