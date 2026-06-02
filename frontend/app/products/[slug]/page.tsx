import { redirect } from 'next/navigation';
import {
  loadProductForOosPage,
  resolveOosListingPathForSlug,
} from '@/lib/product-oos-page';
import { productPathSlugFromApi } from '@/lib/product-path-slug';
import { normalizeProductRouteSlug } from '@/lib/product-route-slug';
import ProductDetailClient from './ProductDetailClient';
import ErrorState from './components/ErrorState/ErrorState';

type Props = { params: Promise<{ slug: string }> };

export default async function ProductDetailPage({ params }: Props) {
  const { slug: rawSlug } = await params;
  const slug = normalizeProductRouteSlug(rawSlug);
  const product = await loadProductForOosPage(slug);

  const redirectOosGroupIfAny = async () => {
    const listingPath = await resolveOosListingPathForSlug(slug, product);
    if (listingPath) {
      redirect(listingPath);
    }
  };

  if (!product) {
    await redirectOosGroupIfAny();
    return <ErrorState error="Không tìm thấy sản phẩm" slug={slug} />;
  }

  const canonicalSlug = productPathSlugFromApi(product.slug, product.product_id);
  if (canonicalSlug && canonicalSlug !== slug) {
    const safeSeg = canonicalSlug.replace(/\//g, '-');
    redirect(`/products/${encodeURIComponent(safeSeg)}`);
  }

  if ((product.available ?? 0) <= 0) {
    await redirectOosGroupIfAny();
  }

  return <ProductDetailClient initialProduct={product} slug={slug} />;
}
