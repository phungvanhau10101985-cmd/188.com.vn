import type { Metadata } from "next";
import { getCategorySeoData, buildCategoryBreadcrumbJsonLd, buildCategoryCollectionJsonLd } from "@/lib/category-seo";
import { absolutePublicAssetUrl } from "@/lib/cdn-url";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || process.env.NEXT_PUBLIC_DOMAIN || "https://188.com.vn";
const DEFAULT_OG_IMAGE = absolutePublicAssetUrl("/images/og-default.jpg");

type Props = {
  params: Promise<{ slug?: string[] }>;
  children: React.ReactNode;
};

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const [level1, level2, level3] = slug || [];
  if (!level1) {
    return {
      title: "Danh mục sản phẩm",
      description: "Khám phá danh mục sản phẩm thời trang nam tại 188.com.vn.",
      robots: { index: true, follow: true },
    };
  }

  // Lấy dữ liệu SEO đầy đủ cho chính trang danh mục này (SEO tất cả các trang danh mục)
  const info = await getCategorySeoData(level1, level2, level3);
  if (!info) {
    return {
      title: "Danh mục không tồn tại",
      robots: { index: false, follow: true },
    };
  }

  const pathSegments = [level1];
  if (level2) pathSegments.push(level2);
  if (level3) pathSegments.push(level3);
  const pathStr = pathSegments.join("/");
  // Canonical động: base URL không có query (?sort=, ?page=) để tránh duplicate content
  const canonical = `${SITE_URL}/danh-muc/${pathStr}`;

  // Title: CHỈ trả về phần thay %s. Root layout có template "%s | 188.COM.VN" → không thêm brand
  const title = `${info.full_name} - ${info.product_count}+ mẫu`;

  // Sử dụng mô tả AI nếu có, fallback về mô tả mặc định
  const description = info.seo_description ||
    `${info.full_name} - ${info.product_count} sản phẩm. Mua sắm tại 188.com.vn - Xem là thích.`.slice(0, 160);

  // Tạo danh sách ảnh cho og:image (tối đa 4 ảnh)
  const ogImages = info.images && info.images.length > 0
    ? info.images.map((url, index) => ({
        url,
        width: 800,
        height: 800,
        alt: `${info.full_name} - Ảnh ${index + 1}`,
      }))
    : [{ url: DEFAULT_OG_IMAGE, width: 1200, height: 630, alt: info.full_name }];

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
      images: info.images && info.images.length > 0 ? [info.images[0]] : [DEFAULT_OG_IMAGE],
    },
    robots: {
      index: true,
      follow: true,
      googleBot: {
        index: true,
        follow: true,
        "max-image-preview": "large",
        "max-snippet": -1,
      },
    },
  };
}

export default async function CategoryLayout({ params, children }: Props) {
  const { slug } = await params;
  const [level1, level2, level3] = slug || [];
  if (!level1) {
    return <>{children}</>;
  }

  // Xuất JSON-LD cho mọi trang danh mục (không còn khái niệm canonical duy nhất)
  const info = await getCategorySeoData(level1, level2, level3);
  if (!info) {
    return <>{children}</>;
  }

  const pathSegments = [level1];
  if (level2) pathSegments.push(level2);
  if (level3) pathSegments.push(level3);
  const pathStr = pathSegments.join("/");
  
  // Sử dụng mô tả AI cho JSON-LD nếu có
  const seoDescription = info.seo_description || 
    `${info.full_name} - ${info.product_count} sản phẩm tại 188.com.vn`;
  
  const breadcrumbJsonLd = buildCategoryBreadcrumbJsonLd(
    info.breadcrumb_names,
    pathSegments
  );
  const collectionJsonLd = buildCategoryCollectionJsonLd(
    info.full_name,
    pathStr,
    info.product_count,
    seoDescription
  );

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(breadcrumbJsonLd) }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(collectionJsonLd) }}
      />
      {children}
    </>
  );
}
