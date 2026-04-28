// frontend/next.config - CLEAN FIXED VERSION
/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    // Sau Nginx: Server Actions cần Origin hợp lệ — tránh "Missing origin header"
    serverActions: {
      allowedOrigins: ['188.com.vn', 'www.188.com.vn', 'localhost:3000'],
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
