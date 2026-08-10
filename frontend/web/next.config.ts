import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // 关闭开发工具浮层：它自带的 Theme/Position 设置只作用于浮层本身，
  // 容易被误认为是应用的主题开关。
  devIndicators: false,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination:
          process.env.API_PROXY_URL ?? "http://localhost:8000/api/:path*",
      },
      // 本地开发没有 Nginx 网关时，把 Sandbox REST 请求代理到本机容器。
      // （VNC 的 WebSocket 无法经 Next 代理，由 NEXT_PUBLIC_VNC_WS_BASE 直连。）
      {
        source: "/sandbox-api/:path*",
        destination:
          process.env.SANDBOX_PROXY_URL ??
          "http://localhost:8100/api/:path*",
      },
    ];
  },
};

export default nextConfig;
