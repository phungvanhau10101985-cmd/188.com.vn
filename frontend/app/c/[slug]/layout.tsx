import type { Metadata } from "next";

import { serializeJsonLdForScript } from "@/lib/json-ld-script";
import { getSiteOrigin } from "@/lib/site-origin";
import {
  buildClusterBreadcrumbJsonLd,
  buildClusterCollectionJsonLd,
} from "@/lib/site-json-ld";
import { getSeoClusterDetail } from "@/lib/seo-cluster";
import { isSeoClusterIndexable, categoryLevel1Href, categoryLevel2Href } from "@/lib/category-listing-href";
import { getListingFreshnessMonthLabel } from "@/lib/listing-freshness-label";
import { absolutePublicAssetUrl } from "@/lib/cdn-url";

const DEFAULT_OG_IMAGE = absolutePublicAssetUrl("/images/og-default.jpg");

type Props = {
  params: Promise<{ slug: string }>;
  children: React.ReactNode;
};

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const cluster = await getSeoClusterDetail(slug);
  const siteOrigin = getSiteOrigin();
  if (!cluster) {
    return {
      title: "Trang không tồn tại",
      robots: { index: false, follow: true },
    };
  }
  const canonical = `${siteOrigin}/c/${cluster.slug}`;
  const isIndex = isSeoClusterIndexable(cluster);
  const month = getListingFreshnessMonthLabel();
  const title = `${cluster.name} — ${month} | ${cluster.product_count}+ mẫu`;
  const description = (
    cluster.seo_description ||
    `${cluster.name} - ${cluster.product_count} sản phẩm. Mua sắm tại 188.com.vn - Xem là thích click là mê.`
  ).slice(0, 160);
  const ogImages =
    cluster.images && cluster.images.length > 0
      ? cluster.images.slice(0, 4).map((url, index) => ({
          url,
          width: 800,
          height: 800,
          alt: `${cluster.name} - Ảnh ${index + 1}`,
        }))
      : [{ url: DEFAULT_OG_IMAGE, width: 1200, height: 630, alt: cluster.name }];

  return {
    title,
    description,
    alternates: { canonical },
    openGraph: {
      type: "website",
      locale: "vi_VN",
      url: canonical,
      siteName: "188.COM.VN",
      title,
      description: description.slice(0, 200),
      images: ogImages,
    },
    twitter: {
      card: "summary_large_image",
      title,
      description: description.slice(0, 200),
      images: cluster.images && cluster.images.length > 0 ? [cluster.images[0]] : [DEFAULT_OG_IMAGE],
    },
    robots: {
      index: isIndex,
      follow: true,
      googleBot: {
        index: isIndex,
        follow: true,
        "max-image-preview": "large",
        "max-snippet": -1,
      },
    },
  };
}

export default async function ClusterLayout({ params, children }: Props) {
  const { slug } = await params;
  const cluster = await getSeoClusterDetail(slug);
  if (!cluster || !isSeoClusterIndexable(cluster)) {
    return <>{children}</>;
  }

  const siteOrigin = getSiteOrigin();
  const description =
    cluster.seo_description ||
    `${cluster.name} - tổng hợp ${cluster.product_count}+ sản phẩm chất lượng tại 188.com.vn.`;
  const l1Href = cluster.level1?.slug
    ? `${siteOrigin}${categoryLevel1Href(cluster.level1.slug)}`
    : undefined;
  const l2Href =
    cluster.level1?.slug && cluster.level2?.slug
      ? `${siteOrigin}${categoryLevel2Href(cluster.level1.slug, cluster.level2.slug)}`
      : undefined;
  const breadcrumbJsonLd = buildClusterBreadcrumbJsonLd({
    clusterName: cluster.name,
    clusterSlug: cluster.slug,
    origin: siteOrigin,
    level1Name: cluster.level1?.name,
    level1Url: l1Href,
    level2Name: cluster.level2?.name,
    level2Url: l2Href,
  });
  const collectionJsonLd = buildClusterCollectionJsonLd(
    cluster.name,
    cluster.slug,
    cluster.product_count,
    description,
    siteOrigin
  );

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: serializeJsonLdForScript(breadcrumbJsonLd),
        }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: serializeJsonLdForScript(collectionJsonLd),
        }}
      />
      {children}
    </>
  );
}
