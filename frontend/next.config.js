// frontend/next.config - CLEAN FIXED VERSION
const path = require("path");

/** @type {import('next').NextConfig} */
const nextConfig = {
  distDir: process.env.NEXT_DIST_DIR || ".next",
  /** VPS: layout SSR có thể chậm khi API/DB bận — tránh fail build sau 60s mặc định. */
  staticPageGenerationTimeout: 180,
  // Trình duyệt mặc định GET /favicon.ico — không có file .ico thì trả về favicon.png (200).
  async rewrites() {
    return [
      { source: "/favicon.ico", destination: "/favicon.png" },
      // /api/v1/* do app/api/v1/[[...path]]/route.ts proxy (retry ECONNRESET, timeout 120s+).
      // Không rewrite thẳng → tránh lỗi "Failed to proxy … socket hang up" khi uvicorn bận sau import.
    ];
  },
  /** Cho phép iframe YouTube (fullscreen, autoplay trong iframe). Không đặt CSP cứng ở đây để tránh vỡ GA/GTM/FB từ admin embed-codes. */
  async headers() {
    const videoFeedRobots = [
      {
        key: "X-Robots-Tag",
        value: "noindex, nofollow, noarchive, noimageindex",
      },
    ];
    const longCache = [
      {
        key: "Cache-Control",
        value: "public, max-age=31536000, immutable",
      },
    ];
    return [
      {
        source: "/_next/static/:path*",
        headers: longCache,
      },
      {
        source: "/favicon.png",
        headers: longCache,
      },
      {
        source: "/luot-video-cung-shop",
        headers: videoFeedRobots,
      },
      {
        source: "/luot-video-cung-shop/:path*",
        headers: videoFeedRobots,
      },
      {
        source: "/:path*",
        headers: [
          /** YouTube embed (lỗi 153) cần Referer hợp lệ — tránh same-origin / no-referrer từ proxy */
          {
            key: "Referrer-Policy",
            value: "strict-origin-when-cross-origin",
          },
          {
            key: "Permissions-Policy",
            value:
              'accelerometer=(self), autoplay=(self "https://www.youtube.com" "https://www.youtube-nocookie.com"), camera=(), clipboard-write=(self), encrypted-media=(self), fullscreen=(self "https://www.youtube.com" "https://www.youtube-nocookie.com"), gyroscope=(self), picture-in-picture=(self), geolocation=(), microphone=()',
          },
        ],
      },
    ];
  },
  transpilePackages: ["antd", "@ant-design/icons"],
  experimental: {
    scrollRestoration: true,
    // Sau Nginx: Server Actions cần Origin hợp lệ — tránh "Missing origin header"
    serverActions: {
      allowedOrigins: ["188.com.vn", "www.188.com.vn", "localhost:3001"],
    },
  },
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "**" },
      { protocol: "http", hostname: "**" },
    ],
    // Luôn dùng URL ảnh gốc (không qua /_next/image → không ép WebP/AVIF, không q=75).
    // Đổi lại: không resize phía Next — ảnh nặng hơn nếu URL là file lớn ( Bunny / alicdn …).
    unoptimized: true,
  },
  typescript: { ignoreBuildErrors: false },
  /** Next.js 16: build mặc định dùng Turbopack — cần `next build --webpack` (xem package.json) vì alias antd ở dưới. */
  webpack: (config) => {
    const root = process.cwd();
    config.resolve.alias = {
      ...config.resolve.alias,
      // Antd compat: lib → es (tree-shaking + tránh build chậm).
      "antd/lib": path.resolve(root, "node_modules/antd/es"),
    };
    // KHÔNG alias 'react' / 'react-dom' về node_modules ở đây —
    // Next 14.2.18 client runtime gọi React.use() (chỉ có trong bản React canary mà Next bundle sẵn ở
    // next/dist/compiled/react). Nếu ép alias về node_modules/react@18.2.0 → React.use undefined →
    // "(0,s.use) is not a function" + Minified React error #423 lúc hydrate.
    return config;
  },
};

module.exports = nextConfig;
