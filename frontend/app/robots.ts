import type { MetadataRoute } from "next";

import {
  AI_CRAWLER_CRAWL_DELAY_SECONDS,
  AI_CRAWLER_USER_AGENTS,
  CRAWLER_DISALLOW_PATHS,
  getSiteOrigin,
} from "@/lib/site-origin";

function publicCrawlRule(userAgent: string, crawlDelay?: number) {
  return {
    userAgent,
    allow: "/",
    disallow: [...CRAWLER_DISALLOW_PATHS],
    ...(crawlDelay ? { crawlDelay } : {}),
  };
}

export default function robots(): MetadataRoute.Robots {
  const origin = getSiteOrigin();

  return {
    rules: [
      publicCrawlRule("*"),
      ...AI_CRAWLER_USER_AGENTS.map((ua) =>
        publicCrawlRule(ua, AI_CRAWLER_CRAWL_DELAY_SECONDS)
      ),
    ],
    sitemap: `${origin}/sitemap-index.xml`,
  };
}
