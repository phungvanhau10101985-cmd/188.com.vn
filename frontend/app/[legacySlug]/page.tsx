import { redirect } from 'next/navigation';
import ErrorState from '@/app/products/[slug]/components/ErrorState/ErrorState';
import { productPathSlugFromApi } from '@/lib/product-path-slug';
import { resolveOosListingPathForSlug } from '@/lib/product-oos-page';
import {
  canonicalProductPathFromProduct,
  normalizeLegacyProductPath,
  resolveLegacyProductAndListingPath,
} from '@/lib/legacy-product-path';

type Props = {
  params: Promise<{ legacySlug: string }>;
};

/**
 * URL legacy một segment (marketing / index.php), không nằm dưới /products/.
 * - Có SP → chuyển sang PDP chuẩn /products/{slug}
 * - Hết hàng / không có SP → listing nhóm (/c/..., /danh-muc/..., tìm kiếm)
 */
export default async function LegacyMarketingProductPage({ params }: Props) {
  const { legacySlug: raw } = await params;
  const legacySlug = normalizeLegacyProductPath(decodeURIComponent((raw || '').trim()));
  if (!legacySlug) {
    redirect('/');
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
  return <ErrorState error="Không tìm thấy sản phẩm" slug={legacySlug} />;
}
