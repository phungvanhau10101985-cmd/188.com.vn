import { permanentRedirect, redirect } from 'next/navigation';
import { productPathSlugFromApi } from '@/lib/product-path-slug';
import { resolveOosListingPathForSlug } from '@/lib/product-oos-page';
import {
  canonicalProductPathFromProduct,
  normalizeLegacyProductPath,
  resolveLegacyProductAndListingPath,
} from '@/lib/legacy-product-path';
import { isReservedNonProductSlug } from '@/lib/reserved-non-product-slugs';

/**
 * URL legacy một segment (marketing / index.php), không nằm dưới /products/.
 * Route handler (không phải page) để miss trả HTTP 404 thật.
 * page + notFound() nằm trong Suspense của root layout nên Next đã gửi 200.
 *
 * - Có SP → chuyển sang PDP chuẩn /products/{slug}
 * - Hết hàng / không có SP → listing nhóm (/c/..., /danh-muc/..., tìm kiếm)
 * - Không resolve được → 404, không gộp về trang chủ
 */
const LEGACY_HOMEPAGE_ALIASES = new Set(['index.html', 'index.htm', 'index.php']);

const LEGACY_NON_PRODUCT_REDIRECTS: Record<string, string> = {
  'tim-kiem-sp': '/',
  'san-pham-cung-shop': '/#san-pham-cung-shop',
  'san-pham-cung-shop-id': '/#san-pham-cung-shop',
};

type RouteContext = { params: Promise<{ legacySlug: string }> };

function homeHrefFor(request: Request): string {
  const host = request.headers.get('host')?.split(':')[0]?.toLowerCase() ?? '';
  return host === 'admin.188.com.vn' ? 'https://188.com.vn/' : '/';
}

function missingLegacyResponse(request: Request, head: boolean): Response {
  const homeHref = homeHrefFor(request);
  const headers = {
    'Content-Type': 'text/html; charset=utf-8',
    'X-Robots-Tag': 'noindex, follow',
    'Cache-Control': 'no-store',
  };
  if (head) return new Response(null, { status: 404, headers });
  const href = homeHref.replace(/&/g, '&amp;').replace(/"/g, '&quot;');
  const html = `<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta name="robots" content="noindex, follow"/>
<title>Không tìm thấy trang | 188.COM.VN</title>
</head>
<body style="margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#f9fafb;font-family:system-ui,sans-serif;text-align:center;padding:24px">
  <main>
    <p style="margin:0 0 8px;font-size:64px;font-weight:700;color:#ea580c">404</p>
    <h1 style="margin:0 0 4px;font-size:16px;font-weight:500;color:#1f2937">Không tìm thấy trang</h1>
    <p style="margin:0 0 24px;font-size:14px;color:#6b7280">Đường dẫn không tồn tại hoặc đã được gỡ.</p>
    <a href="${href}" style="color:#ea580c;font-weight:600;text-decoration:underline">Về trang chủ</a>
  </main>
</body>
</html>`;
  return new Response(html, { status: 404, headers });
}

async function handleLegacy(request: Request, context: RouteContext): Promise<Response> {
  const head = request.method === 'HEAD';
  const { legacySlug: raw } = await context.params;
  const rawDecoded = decodeURIComponent((raw || '').trim()).replace(/^\/+/, '');
  const rawKey = rawDecoded.toLowerCase();
  if (LEGACY_HOMEPAGE_ALIASES.has(rawKey)) {
    permanentRedirect('/');
  }
  const legacySlug = normalizeLegacyProductPath(rawDecoded);
  if (!legacySlug) {
    redirect('/');
  }
  const legacyKey = legacySlug.toLowerCase();
  const nonProductRedirect = LEGACY_NON_PRODUCT_REDIRECTS[legacyKey];
  if (nonProductRedirect) {
    redirect(nonProductRedirect);
  }
  if (legacyKey === 'dang-ky' || legacyKey === 'dangky') {
    redirect('/auth/register');
  }
  if (legacyKey === 'dang-nhap' || legacyKey === 'dangnhap') {
    redirect('/auth/login');
  }
  if (isReservedNonProductSlug(legacySlug)) {
    return missingLegacyResponse(request, head);
  }

  const { product, listingPath: prefetchedListingPath } =
    await resolveLegacyProductAndListingPath(legacySlug);
  const canonicalPath = product ? canonicalProductPathFromProduct(product) : null;

  const redirectOosGroupIfAny = async (
    oosSourceSlug: string,
    productForEmbed?: typeof product,
    legacyMarketing = true,
    prefetched?: string | null,
  ) => {
    const listingPath =
      prefetched ||
      (await resolveOosListingPathForSlug(oosSourceSlug, productForEmbed, {
        legacyMarketingPath: legacyMarketing,
      }));
    if (listingPath) {
      redirect(listingPath);
    }
  };

  if (product && canonicalPath) {
    const oosSource =
      productPathSlugFromApi(product.slug, product.product_id) || legacySlug;
    if ((product.available ?? 0) <= 0) {
      await redirectOosGroupIfAny(oosSource, product, false, prefetchedListingPath);
    }
    redirect(canonicalPath);
  }

  await redirectOosGroupIfAny(legacySlug, null, true, prefetchedListingPath);
  return missingLegacyResponse(request, head);
}

export function GET(request: Request, context: RouteContext) {
  return handleLegacy(request, context);
}

export function HEAD(request: Request, context: RouteContext) {
  return handleLegacy(request, context);
}
