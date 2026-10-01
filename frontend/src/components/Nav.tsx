"use client";
// 데스크톱: 왼쪽 사이드바 / 모바일: 하단 탭바
import Link from "next/link";
import { usePathname } from "next/navigation";

const ICON: Record<string, string> = {
  home: "M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
  diag: "M4 20V10m6 10V4m6 16v-7m4 7H2",
  report: "M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h6",
  settings: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zm7.4-3a7.4 7.4 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7 7 0 0 0-2-1.2L14.5 3h-4l-.4 2.6a7 7 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6a7.4 7.4 0 0 0 0 2.4l-2 1.6 2 3.4 2.4-1a7 7 0 0 0 2 1.2l.4 2.6h4l.4-2.6a7 7 0 0 0 2-1.2l2.4 1 2-3.4-2-1.6c.1-.4.1-.8.1-1.2z",
};
const NAV = [
  { href: "/", label: "실시간 현황", short: "홈", icon: "home" },
  { href: "/diagnostics/", label: "단열 진단", short: "진단", icon: "diag" },
  { href: "/report/", label: "리포트", short: "리포트", icon: "report" },
  { href: "/settings/", label: "기기 · 알림 설정", short: "설정", icon: "settings" },
];

const Icon = ({ name, className = "h-5 w-5" }: { name: string; className?: string }) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
    <path d={ICON[name]} />
  </svg>
);

export const Logo = () => (
  <svg viewBox="0 0 64 64" className="h-8 w-8 shrink-0" aria-hidden>
    <rect width="64" height="64" rx="14" fill="#2a78d6" />
    <path d="M32 12c-8 11-14 19-14 27a14 14 0 0 0 28 0c0-8-6-16-14-27z" fill="#fff" />
  </svg>
);

function useActive() {
  const path = usePathname();
  return (href: string) => (href === "/" ? path === "/" || path.startsWith("/device") : path.startsWith(href.replace(/\/$/, "")));
}

export function Sidebar() {
  const active = useActive();
  return (
    <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col bg-slate-900 px-4 py-6 text-slate-300 md:flex print:hidden">
      <div className="mb-8 flex items-center gap-3 px-2">
        <Logo />
        <div>
          <div className="font-bold text-white">벽면 곰팡이 예보</div>
          <div className="text-xs text-slate-400">결로 · 곰팡이 모니터링</div>
        </div>
      </div>
      <nav className="grid gap-1">
        {NAV.map((n) => (
          <Link key={n.href} href={n.href}
            className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition ${active(n.href) ? "bg-white/10 text-white" : "hover:bg-white/5 hover:text-white"}`}>
            <Icon name={n.icon} />
            {n.label}
          </Link>
        ))}
      </nav>
      <div className="mt-auto rounded-lg bg-white/5 p-3 text-xs leading-relaxed text-slate-400">
        판정 기준: 벽면 상대습도 80% (ISO 13788)
        <br />
        측정값은 상대 비교용입니다.
      </div>
    </aside>
  );
}

export function BottomNav() {
  const active = useActive();
  return (
    <nav className="fixed inset-x-0 bottom-0 z-20 grid grid-cols-4 border-t border-slate-200 bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden print:hidden">
      {NAV.map((n) => (
        <Link key={n.href} href={n.href}
          className={`flex flex-col items-center gap-0.5 py-2 text-[11px] font-medium ${active(n.href) ? "text-blue-700" : "text-slate-500"}`}>
          <Icon name={n.icon} className="h-6 w-6" />
          {n.short}
        </Link>
      ))}
    </nav>
  );
}

export function MobileHeader() {
  return (
    <header className="sticky top-0 z-20 flex items-center gap-2 border-b border-slate-200 bg-white/95 px-4 py-3 backdrop-blur md:hidden print:hidden">
      <Logo />
      <span className="font-bold">벽면 곰팡이 예보</span>
    </header>
  );
}
