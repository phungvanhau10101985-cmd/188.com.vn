// frontend/next.config - CLEAN FIXED VERSION
const path = require("path");

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
    unoptimized: process.env.NODE_ENV === "development",
  },
  typescript: { ignoreBuildErrors: false },
  webpack: (config, { isServer }) => {
    const root = process.cwd();
    config.resolve.alias = {
      ...config.resolve.alias,
      "antd/lib": path.resolve(root, "node_modules/antd/es"),
    };
    // Chỉ ép singleton React trên bundle client — ép trên server có thể phá resolve react-server/RSC của Next.
    if (!isServer) {
      config.resolve.alias.react = path.resolve(root, "node_modules/react");
      config.resolve.alias["react-dom"] = path.resolve(root, "node_modules/react-dom");
    }
    return config;
  },
};

module.exports = nextConfig;
