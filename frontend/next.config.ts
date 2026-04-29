// frontend/next.config - CLEAN FIXED VERSION
/** @type {import('next').NextConfig} */
const nextConfig = {
  // Trình duyệt mặc định GET /favicon.ico — không có file .ico thì trả về favicon.png (200).
  async rewrites() {
    return [{ source: "/favicon.ico", destination: "/favicon.png" }];
  },
  experimental: {
    // Sau Nginx: Server Actions cần Origin hợp lệ — tránh "Missing origin header"
    serverActions: {
      allowedOrigins: ['188.com.vn', 'www.188.com.vn', 'localhost:3001'],
    },
  },
  images: {
    remotePatterns: [
      { protocol: 'https', hostname: '**' },
      { protocol: 'http', hostname: '**' },
    ],
    unoptimized: process.env.NODE_ENV === 'development',
  },
  typescript: { ignoreBuildErrors: false },
  webpack: (config: any) => {
    const path = require('path');
    config.resolve.alias = {
      ...config.resolve.alias,
      'antd/lib': path.resolve(process.cwd(), 'node_modules/antd/es'),
    };
    return config;
  },
};

module.exports = nextConfig;
