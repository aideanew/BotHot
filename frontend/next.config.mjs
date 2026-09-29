/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        // C-CHG-1：前端同源代理后端 API。
        // 本地 dev 默认 http://localhost:3300；容器内由 A 传 BACKEND_ORIGIN=http://backend:3300
        source: "/api/v1/:path*",
        destination: `${process.env.BACKEND_ORIGIN ?? "http://localhost:3300"}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
