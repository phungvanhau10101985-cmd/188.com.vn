import { NextResponse } from "next/server";

import { CATEGORY_SEO_SITEMAP_PATH } from "@/lib/category-sitemap";
import { CRAWLER_DISALLOW_PATHS, getSiteOrigin } from "@/lib/site-origin";

export const revalidate = 86400;

function buildLlmsTxt(origin: string): string {
  const disallowList = CRAWLER_DISALLOW_PATHS.map((p) => `  - ${origin}${p}`).join("\n");

  return `# 188.COM.VN
> Thương mại điện tử thời trang nam nữ, giày dép, phụ kiện — tiếng Việt, giao hàng toàn quốc.

## Giới thiệu
188.COM.VN là website mua sắm online tại Việt Nam. Nội dung công khai gồm trang chủ, danh mục sản phẩm, trang chi tiết sản phẩm, landing SEO cluster, ladipage (bộ sưu tập / landing bán hàng) và trang thông tin/chính sách.

## URL chính
- Trang chủ: ${origin}/
- Danh mục: ${origin}/danh-muc
- Ladipage (bộ sưu tập / landing): ${origin}/lp/{slug}
- Tìm kiếm sản phẩm: ${origin}/?q={tu_khoa}
- Tìm theo ảnh: ${origin}/tim-theo-anh
- Giới thiệu: ${origin}/info/gioi-thieu
- Liên hệ: ${origin}/info/lien-he

## Ladipage (landing bán hàng / nội dung cho AI)
- Vai trò: landing bộ sưu tập / long-tail (thường theo chất liệu). Trang SEO chính của danh mục là ${origin}/danh-muc/... hoặc SEO cluster ${origin}/c/{slug}.
- Trang HTML công khai: ${origin}/lp/{slug} (danh mục hoặc nhiều sản phẩm đã publish).
- Ladipage 1 sản phẩm redirect vĩnh viễn (308) về trang PDP ${origin}/products/{slug} — đọc nội dung bổ sung (hero, chất liệu, FAQ) trên PDP.
- Danh sách URL ladipage đa sản phẩm/danh mục nằm trong sitemap chính (${origin}/sitemap.xml).
- Chi tiết JSON theo slug: GET ${origin}/api/v1/ladipages/public/{slug}
- Related theo danh mục/cluster: GET ${origin}/api/v1/ladipages/public/related?category_path=... hoặc ?cluster_slug=...
- Sitemap ladipage (JSON): GET ${origin}/api/v1/ladipages/public/sitemap

## Sitemap
- Sitemap index: ${origin}/sitemap-index.xml
- Sitemap chính (sản phẩm, ladipage multi, trang tĩnh): ${origin}/sitemap.xml
- Sitemap danh mục SEO: ${origin}${CATEGORY_SEO_SITEMAP_PATH}
- Robots: ${origin}/robots.txt

## Dữ liệu sản phẩm (đọc công khai, không cần đăng nhập)
Base API (proxy qua frontend): ${origin}/api/v1

- Danh sách phân trang: GET ${origin}/api/v1/products/?limit=48&skip=0&is_active=true
- Chi tiết theo slug: GET ${origin}/api/v1/products/by-slug/?slug={slug}
- Tìm kiếm: GET ${origin}/api/v1/products/search/?q={tu_khoa}&limit=48&skip=0
- Danh sách đầy đủ schema: GET ${origin}/api/v1/products/list/full?limit=100&skip=0

## Feed catalog (TSV)
- Google Merchant: GET ${origin}/api/v1/import-export/export/merchant-center-feed.tsv
- Meta catalog: GET ${origin}/api/v1/import-export/export/meta-catalog-feed.tsv
- TikTok catalog: GET ${origin}/api/v1/import-export/export/tiktok-catalog-feed.tsv

## Chính sách thu thập
- Được phép index và trích dẫn các trang sản phẩm, danh mục, ladipage (/lp/) và nội dung thông tin công khai.
- Không thu thập các khu vực sau:
${disallowList}
- Không thu thập thông tin tài khoản, giỏ hàng, checkout hoặc khu admin.

## Structured data
Trang sản phẩm và danh mục có JSON-LD (schema.org: Product, CollectionPage, BreadcrumbList). Ladipage multi có CollectionPage, ItemList, FAQPage và BreadcrumbList. Trang chủ có Organization và WebSite (SearchAction).

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
