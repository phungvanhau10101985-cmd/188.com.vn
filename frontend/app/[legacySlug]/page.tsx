import { redirect } from 'next/navigation';
import ErrorState from '@/app/products/[slug]/components/ErrorState/ErrorState';
import { resolveProductGroupListingPath } from '@/lib/product-oos-redirect';
import { productPathSlugFromApi } from '@/lib/product-path-slug';
import {
  canonicalProductPathFromProduct,
  resolveProductFromLegacyPath,
} from '@/lib/legacy-product-path';

type Props = {
  params: Promise<{ legacySlug: string }>;
};

/**
 * URL marketing một segment (Google / quảng cáo), không nằm dưới /products/.
 * - Có SP → chuyển sang PDP chuẩn /products/{slug}
 * - Hết hàng / không có SP → listing nhóm (/c/..., /danh-muc/..., tìm kiếm)
 */
export default async function LegacyMarketingProductPage({ params }: Props) {
  const { legacySlug: raw } = await params;
  const legacySlug = decodeURIComponent((raw || '').trim());
  if (!legacySlug) {
    redirect('/');
  }

  const product = await resolveProductFromLegacyPath(legacySlug);
  const canonicalPath = product ? canonicalProductPathFromProduct(product) : null;

  const redirectOosGroupIfAny = async (oosSourceSlug: string, legacyMarketing = true) => {
    const listingPath = await resolveProductGroupListingPath(oosSourceSlug, {
      legacyMarketingPath: legacyMarketing,
    });
    if (listingPath) {
      redirect(listingPath);
    }
  };

  if (product && canonicalPath) {
    const oosSource =
      productPathSlugFromApi(product.slug, product.product_id) || legacySlug;
    if ((product.available ?? 0) <= 0) {
      await redirectOosGroupIfAny(oosSource, false);
    }
    redirect(canonicalPath);
  }

  await redirectOosGroupIfAny(legacySlug, true);
  return <ErrorState error="Không tìm thấy sản phẩm" slug={legacySlug} />;
}
