/** Origin tuyệt đối cho SEO, robots, llms.txt, sitemap — luôn có scheme https:// */
export function getSiteOrigin(): string {
  const raw =
    process.env.NEXT_PUBLIC_SITE_URL?.trim() ||
    process.env.NEXT_PUBLIC_DOMAIN?.trim() ||
    (process.env.NODE_ENV === "development"
      ? "http://localhost:3001"
      : "https://188.com.vn");
  if (!raw) return "https://188.com.vn";
  if (/^https?:\/\//i.test(raw)) return raw.replace(/\/+$/, "");
  return `https://${raw.replace(/^\/+/, "").replace(/\/+$/, "")}`;
}

/** Đường dẫn không cho crawler/AI bot thu thập (khớp robots.ts). */
export const CRAWLER_DISALLOW_PATHS = [
  "/admin/",
  "/account/",
  "/api/",
  "/auth/",
  "/checkout/",
  "/cart",
  "/luot-video-cung-shop",
] as const;

/** User-agent AI phổ biến — cho phép crawl nội dung public giống rule mặc định. */
export const AI_CRAWLER_USER_AGENTS = [
  "GPTBot",
  "ChatGPT-User",
  "OAI-SearchBot",
  "ClaudeBot",
  "anthropic-ai",
  "PerplexityBot",
  "Google-Extended",
] as const;
