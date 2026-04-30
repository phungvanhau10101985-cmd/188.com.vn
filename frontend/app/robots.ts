import type { MetadataRoute } from "next";

/** URL tuyệt đối — PSI/Lighthouse báo robots.txt lỗi nếu Sitemap không phải https://... đầy đủ */
function normalizeSiteOrigin(): string {
  const raw =
    process.env.NEXT_PUBLIC_SITE_URL?.trim() ||
    process.env.NEXT_PUBLIC_DOMAIN?.trim() ||
    "https://188.com.vn";
  if (!raw) return "https://188.com.vn";
  if (/^https?:\/\//i.test(raw)) return raw.replace(/\/+$/, "");
  return `https://${raw.replace(/^\/+/, "").replace(/\/+$/, "")}`;
}

export default function robots(): MetadataRoute.Robots {
  const origin = normalizeSiteOrigin();

  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: [
          "/admin/",
          "/account/",
          "/api/",
          "/auth/",
          "/checkout/",
          "/cart",
        ],
      },
    ],
    sitemap: `${origin}/sitemap.xml`,
  };
}
