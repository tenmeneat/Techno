import type { NextConfig } from "next";

// 정적 파일로 빌드(out/)해서 FastAPI가 같은 출처로 서빙한다. Capacitor 래핑도 이 산출물을 쓴다.
const config: NextConfig = { output: "export", trailingSlash: true };

export default config;
