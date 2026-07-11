import { notFound, redirect } from 'next/navigation';
import {
  loadProductForOosPage,
  resolveOosListingPathForSlug,
} from '@/lib/product-oos-page';
import { productPathSlugFromApi } from '@/lib/product-path-slug';
import { normalizeProductRouteSlug } from '@/lib/product-route-slug';
import { isReservedNonProductSlug } from '@/lib/reserved-non-product-slugs';
import ProductDetailClient from './ProductDetailClient';
import ErrorState from './components/ErrorState/ErrorState';

type Props = {
  params: Promise<{ slug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

function buildQuerySuffix(sp: Record<string, string | string[] | undefined>): string {
  const q = new URLSearchParams();
  for (const [key, raw] of Object.entries(sp || {})) {
    if (raw == null) continue;
    if (Array.isArray(raw)) {
      raw.forEach((v) => {
        if (v != null && String(v).trim()) q.append(key, String(v));
      });
    } else if (String(raw).trim()) {
      q.set(key, String(raw));
    }
  }
  const s = q.toString();
  return s ? `?${s}` : '';
}

export default async function ProductDetailPage({ params, searchParams }: Props) {
  const { slug: rawSlug } = await params;
  const sp = await searchParams;
  const querySuffix = buildQuerySuffix(sp);
  const slug = normalizeProductRouteSlug(rawSlug);
  if (isReservedNonProductSlug(slug)) {
    notFound();
  }
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
    redirect(`/products/${encodeURIComponent(safeSeg)}${querySuffix}`);
  }

  if ((product.available ?? 0) <= 0) {
    await redirectOosGroupIfAny();
  }

  return <ProductDetailClient key={slug} initialProduct={product} slug={slug} />;
}
