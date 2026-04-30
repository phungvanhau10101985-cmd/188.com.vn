import type { Metadata } from "next";

import { getSeoClusterDetail } from "@/lib/seo-cluster";

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL ||
  process.env.NEXT_PUBLIC_DOMAIN ||
  "https://188.com.vn";

type Props = {
  params: { slug: string };
  children: React.ReactNode;
};

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = params;
  const cluster = await getSeoClusterDetail(slug);
  if (!cluster) {
    return {
      title: "Trang không tồn tại",
      robots: { index: false, follow: true },
    };
  }
  const canonical = `${SITE_URL}/c/${cluster.slug}`;
  const isIndex = cluster.index_policy !== "noindex";
  const title = `${cluster.name} - ${cluster.product_count}+ sản phẩm`;
  const description = `${cluster.name} - tổng hợp sản phẩm chính hãng, giá tốt, giao nhanh tại 188.com.vn.`;
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

export default function ClusterLayout({ children }: Props) {
  return <>{children}</>;
}
