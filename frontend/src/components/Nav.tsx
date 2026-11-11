"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "./Icon";
import { useExperience } from "./Experience";
const NAV = [
  { href: "/", label: "실시간 현황", short: "홈", icon: "home" },
  { href: "/report/", label: "측정 리포트", short: "리포트", icon: "report" },
  { href: "/settings/", label: "기기 · 알림 설정", short: "설정", icon: "settings" },
];
export const Logo = () => <span className="brand-icon"><Icon name="drop" className="h-6 w-6" /></span>;
function useActive() {
  const path = usePathname();
  return (href: string) => href === "/" ? path === "/" || path.startsWith("/device") : path.startsWith(href.replace(/\/$/, ""));
}
export function Sidebar() {
  const active = useActive();
  const { href } = useExperience();
  return <aside className="app-sidebar print:hidden">
    <Link href={href("/")} className="brand"><Logo /><span><strong>벽면 곰팡이 예보</strong><small>내 방을 위한 작은 안심</small></span></Link>
    <p className="nav-caption">MY SPACE</p>
    <nav aria-label="주 메뉴" className="side-links">{NAV.map(n => <Link key={n.href} href={href(n.href)} aria-current={active(n.href) ? "page" : undefined} className={active(n.href) ? "active" : ""}><Icon name={n.icon} /><span>{n.label}</span>{active(n.href) && <span className="nav-dot" />}</Link>)}</nav>
    <div className="sidebar-note"><Icon name="shield" /><strong>보이지 않는 습기까지</strong><p>벽면의 변화를 살펴보고<br />환기가 필요한 순간을 알려드려요.</p><Link href={href("/settings/")}>알림 설정하기 <span>↗</span></Link></div>
    <div className="sidebar-footer"><span className="tiny-dot" /> 원룸 환경 모니터링 <small>TECHNO · TEAM 03</small></div>
  </aside>;
}
export function BottomNav() {
  const active = useActive();
  const { href } = useExperience();
  return <nav aria-label="모바일 주 메뉴" className="bottom-nav print:hidden">{NAV.map(n => <Link key={n.href} href={href(n.href)} aria-current={active(n.href) ? "page" : undefined} className={active(n.href) ? "active" : ""}><Icon name={n.icon} /><span>{n.short}</span></Link>)}</nav>;
}
export function MobileHeader() {
  const { href } = useExperience();
  return <header className="mobile-header print:hidden"><Link href={href("/")} className="brand"><Logo /><strong>벽면 곰팡이 예보</strong></Link><Link href={href("/settings/")} aria-label="알림 설정"><Icon name="bell" /></Link></header>;
}
