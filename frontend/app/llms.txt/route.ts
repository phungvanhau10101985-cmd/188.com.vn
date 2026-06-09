import { NextResponse } from "next/server";

import { CATEGORY_SEO_SITEMAP_PATH } from "@/lib/category-sitemap";
import { CRAWLER_DISALLOW_PATHS, getSiteOrigin } from "@/lib/site-origin";

export const revalidate = 86400;

function buildLlmsTxt(origin: string): string {
  const disallowList = CRAWLER_DISALLOW_PATHS.map((p) => `  - ${origin}${p}`).join("\n");

  return `# 188.COM.VN
> Thương mại điện tử thời trang nam nữ, giày dép, phụ kiện — tiếng Việt, giao hàng toàn quốc.

## Giới thiệu
188.COM.VN là website mua sắm online tại Việt Nam. Nội dung công khai gồm trang chủ, danh mục sản phẩm, trang chi tiết sản phẩm, landing SEO cluster và trang thông tin/chính sách.

## URL chính
- Trang chủ: ${origin}/
- Danh mục: ${origin}/danh-muc
- Tìm kiếm sản phẩm: ${origin}/?q={tu_khoa}
- Tìm theo ảnh: ${origin}/tim-theo-anh
- Giới thiệu: ${origin}/info/gioi-thieu
- Liên hệ: ${origin}/info/lien-he

## Sitemap
- Sitemap index: ${origin}/sitemap-index.xml
- Sitemap chính (sản phẩm, trang tĩnh): ${origin}/sitemap.xml
- Sitemap danh mục SEO: ${origin}${CATEGORY_SEO_SITEMAP_PATH}
- Sitemap sản phẩm phân trang: ${origin}/sitemap-san-pham/1
- Robots: ${origin}/robots.txt

## Dữ liệu sản phẩm public
- Ưu tiên đọc danh sách URL từ sitemap index và các sitemap sản phẩm.
- Đọc chi tiết sản phẩm từ trang HTML public /products/{slug}; trang có metadata, Open Graph và JSON-LD Product.
- Đọc danh mục từ /danh-muc và landing SEO /c/{slug}; các trang này có CollectionPage và BreadcrumbList.
- Không crawl API /api trực tiếp. API bị chặn trong robots.txt để bảo vệ server khỏi truy vấn hàng loạt; nếu cần feed/catalog khối lượng lớn, vui lòng liên hệ trước.

## Chính sách thu thập
- Được phép index và trích dẫn các trang sản phẩm, danh mục và nội dung thông tin công khai.
- Ưu tiên tuần tự theo sitemap, hạn chế tải song song và tôn trọng crawl-delay trong robots.txt.
- Không thu thập các khu vực sau:
${disallowList}
- Không thu thập thông tin tài khoản, giỏ hàng, checkout hoặc khu admin.

## Structured data
Trang sản phẩm và danh mục có JSON-LD (schema.org: Product, CollectionPage, BreadcrumbList). Trang chủ có Organization và WebSite (SearchAction).

## Liên hệ
${origin}/info/lien-he
`;
}

export async function GET() {
  const origin = getSiteOrigin();
  const body = buildLlmsTxt(origin);
  return new NextResponse(body, {
    status: 200,
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "public, s-maxage=86400, stale-while-revalidate=604800",
    },
  });
}
