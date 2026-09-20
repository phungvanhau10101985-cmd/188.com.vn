import { APP_WEB_ICON_URL } from "@/lib/app-web-icon";
import {
  BUSINESS_ADDRESS,
  BUSINESS_EMAIL,
  BUSINESS_FACEBOOK,
  BUSINESS_HOURS,
  BUSINESS_LEGAL_NAME,
  BUSINESS_PHONE,
  BUSINESS_ZALO,
} from "@/lib/business-info";
import { getSiteOrigin } from "@/lib/site-origin";

const SITE_NAME = "188.COM.VN";

export function buildOrganizationJsonLd(origin: string = getSiteOrigin()): object {
  return {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: SITE_NAME,
    legalName: BUSINESS_LEGAL_NAME,
    url: origin,
    logo: APP_WEB_ICON_URL,
    address: {
      "@type": "PostalAddress",
      streetAddress: BUSINESS_ADDRESS.streetAddress,
      addressLocality: BUSINESS_ADDRESS.addressLocality,
      addressRegion: BUSINESS_ADDRESS.addressRegion,
      addressCountry: BUSINESS_ADDRESS.addressCountry,
    },
    contactPoint: {
      "@type": "ContactPoint",
      telephone: `+84${BUSINESS_PHONE.replace(/^0/, "")}`,
      email: BUSINESS_EMAIL,
      contactType: "customer service",
      areaServed: "VN",
      availableLanguage: ["Vietnamese"],
      hoursAvailable: BUSINESS_HOURS,
    },
    sameAs: [BUSINESS_FACEBOOK, BUSINESS_ZALO],
  };
}

export function buildWebSiteJsonLd(origin: string = getSiteOrigin()): object {
  return {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: SITE_NAME,
    url: origin,
    inLanguage: "vi-VN",
    publisher: {
      "@type": "Organization",
      name: BUSINESS_LEGAL_NAME,
      url: origin,
    },
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

export function buildClusterBreadcrumbJsonLd(args: {
  clusterName: string;
  clusterSlug: string;
  origin?: string;
  level1Name?: string | null;
  level1Url?: string | null;
  level2Name?: string | null;
  level2Url?: string | null;
}): object {
  const origin = args.origin ?? getSiteOrigin();
  const items: Array<{ "@type": string; position: number; name: string; item: string }> = [
    { "@type": "ListItem", position: 1, name: "Trang chủ", item: origin },
  ];
  let position = 2;
  if (args.level1Name && args.level1Url) {
    items.push({
      "@type": "ListItem",
      position: position++,
      name: args.level1Name,
      item: args.level1Url,
    });
  }
  if (args.level2Name && args.level2Url) {
    items.push({
      "@type": "ListItem",
      position: position++,
      name: args.level2Name,
      item: args.level2Url,
    });
  }
  items.push({
    "@type": "ListItem",
    position,
    name: args.clusterName,
    item: `${origin}/c/${args.clusterSlug}`,
  });
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items,
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
