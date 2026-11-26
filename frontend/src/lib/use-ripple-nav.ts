"use client";
import { useRouter, usePathname } from "next/navigation";
import { useCallback, useEffect, useRef } from "react";

// 클릭 지점에 수면 파동 링을 띄우고, 지원 브라우저에서는 View Transitions API로
// 새 화면이 그 지점에서부터 번져 드러나게 한다. 둘 다 의존성 없이 네이티브로만 구현.
function spawnWaterRipple(x: number, y: number) {
  const wrap = document.createElement("div");
  wrap.className = "water-ripple";
  wrap.style.left = `${x}px`;
  wrap.style.top = `${y}px`;
  wrap.innerHTML = "<span></span><span></span><span></span>";
  document.body.appendChild(wrap);
  setTimeout(() => wrap.remove(), 1100);
}

export function useRippleNav() {
  const router = useRouter();
  const pathname = usePathname();
  const resolveRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    resolveRef.current?.();
    resolveRef.current = null;
  }, [pathname]);

  return useCallback((href: string, e: React.MouseEvent) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    const targetPath = href.split(/[?#]/)[0] || "/";
    if (targetPath === pathname) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!reduced) spawnWaterRipple(e.clientX, e.clientY);

    const startViewTransition = (document as { startViewTransition?: (cb: () => void | Promise<void>) => void }).startViewTransition;
    if (typeof startViewTransition !== "function" || reduced) return; // Link가 그대로 이동 처리

    e.preventDefault();
    document.documentElement.style.setProperty("--ripple-x", `${e.clientX}px`);
    document.documentElement.style.setProperty("--ripple-y", `${e.clientY}px`);
    const fallback = setTimeout(() => resolveRef.current?.(), 800);
    startViewTransition.call(document, () => new Promise<void>((resolve) => {
      resolveRef.current = () => { clearTimeout(fallback); resolve(); };
      router.push(href);
    }));
  }, [router, pathname]);
}
