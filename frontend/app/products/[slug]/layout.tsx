import type { Metadata } from "next";
import {
  getProductBySlugForSeo,
  buildProductJsonLd,
  stripHtml,
  truncateDescriptionAtSentence,
} from "@/lib/product-seo";
import { displayableBrandOrOrigin, displayableBrandWithDefault } from "@/lib/utils";

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL ||
  process.env.NEXT_PUBLIC_DOMAIN ||
  "https://188.com.vn";

function absoluteImage(img: string | undefined): string {
  if (!img) return "";
  if (img.startsWith("http")) return img;
  if (img.startsWith("//")) return "https:" + img;
  if (img.startsWith("/")) return SITE_URL + img;
  return SITE_URL + "/" + img;
}

type Props = { params: { slug: string }; children: React.ReactNode };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = params;
  const product = await getProductBySlugForSeo(slug);
  if (!product) {
    return {
      title: "Sản phẩm không tồn tại",
      robots: { index: false, follow: true },
    };
  }

  const brandForSeo = displayableBrandWithDefault(product.brand_name);
  const brandForTitle = displayableBrandOrOrigin(product.brand_name); // Chỉ thêm brand vào title khi có thật (tránh lặp "... - 188.com.vn | 188.COM.VN")
  const title =
    product.meta_title ||
    `${product.name}${brandForTitle ? ` - ${brandForTitle}` : ""}`;
  const rawDesc =
    product.meta_description ||
    product.description ||
    `${product.name}. ${brandForSeo ? `Thương hiệu ${brandForSeo}. ` : ""}Giá ${new Intl.NumberFormat("vi-VN").format(product.price)} ₫. Mua sắm tại 188.com.vn - Xem là thích.`;
  const description = truncateDescriptionAtSentence(rawDesc, 160);
  const canonical = `${SITE_URL}/products/${product.slug}`;
  const image = absoluteImage(product.main_image) || absoluteImage(product.images?.[0]);

  return {
    title,
    description,
    keywords: product.meta_keywords || undefined,
    alternates: {
      canonical,
    },
    openGraph: {
      type: "website",
      locale: "vi_VN",
      url: canonical,
      siteName: "188.COM.VN",
      title,
      description: description.slice(0, 200).trim(),
      images: image
        ? [
            {
              url: image,
              width: 800,
              height: 800,
              alt: product.name,
            },
          ]
        : undefined,
    },
    twitter: {
      card: "summary_large_image",
      title,
      description: description.slice(0, 200).trim(),
      images: image ? [image] : undefined,
    },
    robots: {
      index: true,
      follow: true,
      googleBot: {
        index: true,
        follow: true,
        "max-image-preview": "large",
        "max-snippet": -1,
        "max-video-preview": -1,
      },
    },
    other: {
      "product:price:amount": String(product.price),
      "product:price:currency": "VND",
      "product:availability": (product.available ?? 0) > 0 ? "in stock" : "out of stock",
      "product:brand": brandForSeo,
    },
  };
}

function buildBreadcrumbJsonLd(product: { 
  name: string; 
  slug: string;
  category?: string;
  subcategory?: string;
  sub_subcategory?: string;
  raw_category?: string;
  raw_subcategory?: string;
}) {
  const breadcrumbItems = [
    { "@type": "ListItem", position: 1, name: "Trang chủ", item: SITE_URL },
  ];

  let position = 2;
  
  // Thêm danh mục cấp 1 nếu có - Sử dụng raw_category nếu có
  const categoryLevel1 = product.raw_category || product.category;
  if (categoryLevel1) {
    breadcrumbItems.push({
      "@type": "ListItem",
      position: position++,
      name: categoryLevel1,
      item: `${SITE_URL}/danh-muc/${categoryLevel1.toLowerCase().replace(/\s+/g, '-')}`,
    });
  }

  // Thêm danh mục cấp 2 nếu có - Sử dụng raw_subcategory nếu có
  const categoryLevel2 = product.raw_subcategory || product.subcategory;
  if (categoryLevel2 && categoryLevel1) {
    breadcrumbItems.push({
      "@type": "ListItem",
      position: position++,
      name: categoryLevel2,
      item: `${SITE_URL}/danh-muc/${categoryLevel1.toLowerCase().replace(/\s+/g, '-')}/${categoryLevel2.toLowerCase().replace(/\s+/g, '-')}`,
    });
  }

  // Thêm danh mục cấp 3 nếu có
  if (product.sub_subcategory && categoryLevel1 && categoryLevel2) {
    breadcrumbItems.push({
      "@type": "ListItem",
      position: position++,
      name: product.sub_subcategory,
      item: `${SITE_URL}/danh-muc/${categoryLevel1.toLowerCase().replace(/\s+/g, '-')}/${categoryLevel2.toLowerCase().replace(/\s+/g, '-')}/${product.sub_subcategory.toLowerCase().replace(/\s+/g, '-')}`,
    });
  }

  // Thêm tên sản phẩm
  breadcrumbItems.push({
    "@type": "ListItem",
    position: position,
    name: product.name,
    item: `${SITE_URL}/products/${product.slug}`,
  });

  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: breadcrumbItems,
  };
}

export default async function ProductLayout({ params, children }: Props) {
  const { slug } = params;
  const product = await getProductBySlugForSeo(slug);
  const productJsonLd = product ? buildProductJsonLd(product) : null;
  const breadcrumbJsonLd = product ? buildBreadcrumbJsonLd(product) : null;

  return (
    <>
      {productJsonLd && (
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(productJsonLd) }}
        />
      )}
      {breadcrumbJsonLd && (
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(breadcrumbJsonLd) }}
        />
      )}
      {children}
    </>
  );
}
