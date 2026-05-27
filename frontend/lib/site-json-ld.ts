import { APP_WEB_ICON_URL } from "@/lib/app-web-icon";
import { getSiteOrigin } from "@/lib/site-origin";

const SITE_NAME = "188.COM.VN";

export function buildOrganizationJsonLd(origin: string = getSiteOrigin()): object {
  return {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: SITE_NAME,
    url: origin,
    logo: APP_WEB_ICON_URL,
  };
}

export function buildWebSiteJsonLd(origin: string = getSiteOrigin()): object {
  return {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: SITE_NAME,
    url: origin,
    inLanguage: "vi-VN",
    potentialAction: {
      "@type": "SearchAction",
      target: {
        "@type": "EntryPoint",
        urlTemplate: `${origin}/?q={search_term_string}`,
      },
      "query-input": "required name=search_term_string",
    },
  };
}

export function buildClusterBreadcrumbJsonLd(
  clusterName: string,
  clusterSlug: string,
  origin: string = getSiteOrigin()
): object {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Trang chủ", item: origin },
      {
        "@type": "ListItem",
        position: 2,
        name: clusterName,
        item: `${origin}/c/${clusterSlug}`,
      },
    ],
  };
}

export function buildClusterCollectionJsonLd(
  name: string,
  slug: string,
  productCount: number,
  description: string,
  origin: string = getSiteOrigin()
): object {
  return {
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    name,
    description: description.slice(0, 500),
    url: `${origin}/c/${slug}`,
    numberOfItems: productCount,
    isPartOf: { "@type": "WebSite", name: SITE_NAME, url: origin },
  };
}
