"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { Icon } from "./Icon";

export type ExperienceMode = "welcome" | "demo" | "live";
const STORAGE_KEY = "wall-forecast-mode";
const ExperienceContext = createContext<{
  mode: ExperienceMode;
  ready: boolean;
  setMode: (mode: ExperienceMode) => void;
  href: (path: string) => string;
} | null>(null);

export function experienceHref(path: string, mode: ExperienceMode) {
  const [base, query] = path.split("?");
  const params = new URLSearchParams(query);
  params.delete("demo"); params.delete("mode");
  if (mode === "demo") params.set("demo", "1");
  if (mode === "live") params.set("mode", "live");
  return `${base}${params.size ? `?${params}` : ""}`;
}

export function ExperienceProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [mode, updateMode] = useState<ExperienceMode>("welcome");
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const sync = () => {
      const params = new URLSearchParams(window.location.search);
      let stored: string | null = null;
      try { stored = sessionStorage.getItem(STORAGE_KEY); } catch { /* Private browsing may disable storage. */ }
      const next: ExperienceMode = params.get("demo") === "1" ? "demo" : params.get("mode") === "live" ? "live" : stored === "demo" || stored === "live" ? stored : "welcome";
      updateMode(next);
      try { if (next !== "welcome") sessionStorage.setItem(STORAGE_KEY, next); } catch { /* The URL still carries the selected mode. */ }
      setReady(true);
    };
    sync();
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, [pathname]);
  const setMode = useCallback((next: ExperienceMode) => {
    updateMode(next);
    try { next === "welcome" ? sessionStorage.removeItem(STORAGE_KEY) : sessionStorage.setItem(STORAGE_KEY, next); } catch { /* Keep the in-memory selection. */ }
    window.history.replaceState(null, "", experienceHref(window.location.pathname + window.location.search, next));
    window.scrollTo(0, 0);
  }, []);
  const href = (path: string) => experienceHref(path, mode);
  return <ExperienceContext.Provider value={{ mode, ready, setMode, href }}>{children}</ExperienceContext.Provider>;
}

export function useExperience() {
  const value = useContext(ExperienceContext);
  if (!value) throw new Error("ExperienceProvider is required");
  return value;
}

export function ExperienceChoice() {
  const { setMode } = useExperience();
  return <section className="experience-entry">
    <div className="entry-intro"><span className="entry-eyebrow"><Icon name="shield" /> 내 공간을 위한 작은 안심</span><h1>내 방의 작은 변화를<br /><em>안심으로 바꿔요.</em></h1><p>실내 온도와 습도, 벽면의 상태까지.<br />지금 내 방에 필요한 행동을 한눈에 확인하세요.</p></div>
    <div className="entry-options">
      <button className="entry-choice glass-panel" onClick={() => setMode("demo")}><span className="entry-icon"><Icon name="home" className="h-7 w-7" /></span><span className="entry-choice-label">먼저 둘러보고 싶다면</span><strong>샘플로 체험하기</strong><span className="entry-choice-description">기기 없이 대시보드와 날짜별 리포트,<br />PDF 저장까지 미리 살펴보세요.</span><span className="entry-choice-action">바로 체험하기 <Icon name="arrow" /></span></button>
      <button className="entry-choice glass-panel" onClick={() => setMode("live")}><span className="entry-icon live"><Icon name="wall" className="h-7 w-7" /></span><span className="entry-choice-label">측정 기기가 준비되어 있다면</span><strong>내 기기 연결하기</strong><span className="entry-choice-description">연결된 측정 서버에서 내 공간의<br />실제 온습도와 벽면 상태를 확인해요.</span><span className="entry-choice-action">실제 기록 확인하기 <Icon name="arrow" /></span></button>
    </div>
    <p className="entry-note"><Icon name="shield" /> 샘플 데이터와 실제 측정 기록은 구분해서 표시해요.</p>
  </section>;
}
