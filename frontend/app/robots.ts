import type { MetadataRoute } from "next";

import {
  AI_CRAWLER_USER_AGENTS,
  CRAWLER_DISALLOW_PATHS,
  getSiteOrigin,
} from "@/lib/site-origin";

function publicCrawlRule(userAgent: string) {
  return {
    userAgent,
    allow: "/",
    disallow: [...CRAWLER_DISALLOW_PATHS],
  };
}

export default function robots(): MetadataRoute.Robots {
  const origin = getSiteOrigin();

  return {
    rules: [
      publicCrawlRule("*"),
      ...AI_CRAWLER_USER_AGENTS.map((ua) => publicCrawlRule(ua)),
    ],
    sitemap: `${origin}/sitemap-index.xml`,
  };
}
