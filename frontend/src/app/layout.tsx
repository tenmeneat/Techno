import type { Metadata, Viewport } from "next";
import Link from "next/link";
import { Providers } from "@/components/Providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "벽면 곰팡이 예보",
  description: "원룸 결로·곰팡이 예측 대시보드",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/icon.svg", apple: "/icon.svg" },
};
export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#1d4ed8" };

const NAV = [["/", "홈"], ["/diagnostics", "진단"], ["/report", "리포트"], ["/settings", "설정"]] as const;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body className="mx-auto min-h-screen max-w-3xl bg-gray-50 text-gray-900">
        <Providers>
          <nav className="sticky top-0 z-10 flex gap-4 border-b bg-white px-4 py-3 text-sm font-medium print:hidden">
            {NAV.map(([href, label]) => (
              <Link key={href} href={href} className="hover:text-blue-700">{label}</Link>
            ))}
          </nav>
          <main className="p-4">{children}</main>
        </Providers>
      </body>
    </html>
  );
}
