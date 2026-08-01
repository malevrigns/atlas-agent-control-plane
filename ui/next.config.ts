import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination:
          process.env.API_PROXY_URL ?? "http://localhost:8000/api/:path*",
      },
    ];
  },
};

export default nextConfig;
