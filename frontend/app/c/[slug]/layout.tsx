import type { Metadata } from "next";

import { serializeJsonLdForScript } from "@/lib/json-ld-script";
import { getSiteOrigin } from "@/lib/site-origin";
import {
  buildClusterBreadcrumbJsonLd,
  buildClusterCollectionJsonLd,
} from "@/lib/site-json-ld";
import { getSeoClusterDetail } from "@/lib/seo-cluster";

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
  const isIndex = cluster.index_policy !== "noindex";
  const title = `${cluster.name} - ${cluster.product_count}+ sản phẩm`;
  const description = `${cluster.name} - tổng hợp sản phẩm chất lượng, giá tốt, giao nhanh tại 188.com.vn.`;
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
      description,
    },
    twitter: { card: "summary_large_image", title, description },
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
  if (!cluster || cluster.index_policy === "noindex") {
    return <>{children}</>;
  }

  const siteOrigin = getSiteOrigin();
  const description = `${cluster.name} - tổng hợp ${cluster.product_count}+ sản phẩm chất lượng tại 188.com.vn.`;
  const breadcrumbJsonLd = buildClusterBreadcrumbJsonLd(
    cluster.name,
    cluster.slug,
    siteOrigin
  );
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
