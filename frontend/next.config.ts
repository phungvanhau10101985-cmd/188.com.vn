// frontend/next.config - CLEAN FIXED VERSION
/** @type {import('next').NextConfig} */
const nextConfig = {
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
