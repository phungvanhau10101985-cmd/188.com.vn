// frontend/next.config.js - CLEAN WORKING VERSION
/** @type {import('next').NextConfig} */
const path = require('path');
const nextConfig = {
  images: {
    remotePatterns: [
      { protocol: 'https', hostname: '**' },
      { protocol: 'http', hostname: '**' },
    ],
    unoptimized: process.env.NODE_ENV === 'development',
  },
  experimental: {
    scrollRestoration: true,
  },
  transpilePackages: ['antd', '@ant-design/icons'],
  webpack: (config) => {
    config.resolve.alias = {
      ...config.resolve.alias,
      'antd/lib': path.resolve(process.cwd(), 'node_modules/antd/es'),
    };
    return config;
  },
}

module.exports = nextConfig