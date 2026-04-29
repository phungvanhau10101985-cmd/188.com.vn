// frontend/next.config - CLEAN FIXED VERSION
/** @type {import('next').NextConfig} */
const nextConfig = {
  // Trình duyệt mặc định GET /favicon.ico — không có file .ico thì trả về favicon.png (200).
  async rewrites() {
    return [{ source: "/favicon.ico", destination: "/favicon.png" }];
  },
  /** Cho phép iframe YouTube (fullscreen, autoplay trong iframe). Không đặt CSP cứng ở đây để tránh vỡ GA/GTM/FB từ admin embed-codes. */
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          {
            key: "Permissions-Policy",
            value:
              'accelerometer=(self), autoplay=(self "https://www.youtube.com" "https://www.youtube-nocookie.com"), camera=(), clipboard-write=(self), encrypted-media=(self), fullscreen=(self "https://www.youtube.com" "https://www.youtube-nocookie.com"), gyroscope=(self), picture-in-picture=(self), geolocation=(), microphone=()',
          },
        ],
      },
    ];
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
