import type { Metadata, Viewport } from "next";
import { BottomNav, MobileHeader, Sidebar } from "@/components/Nav";
import { Providers } from "@/components/Providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "벽면 곰팡이 예보",
  description: "원룸 결로·곰팡이 예측 대시보드",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/icon.svg", apple: "/icon.svg" },
};
export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#0f172a", viewportFit: "cover" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body className="min-h-screen text-slate-900 antialiased">
        <Providers>
          <div className="flex min-h-screen">
            <Sidebar />
            <div className="min-w-0 flex-1 pb-20 md:pb-0">
              <MobileHeader />
              <main id="main-content" className="app-main">{children}</main>
            </div>
          </div>
          <BottomNav />
        </Providers>
      </body>
    </html>
  );
}
