import { redirect } from 'next/navigation';
import {
  loadProductForOosPage,
  resolveOosListingPathForSlug,
} from '@/lib/product-oos-page';
import ProductDetailClient from './ProductDetailClient';
import ErrorState from './components/ErrorState/ErrorState';

type Props = { params: Promise<{ slug: string }> };

export default async function ProductDetailPage({ params }: Props) {
  const { slug } = await params;
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

  if ((product.available ?? 0) <= 0) {
    await redirectOosGroupIfAny();
  }

  return <ProductDetailClient initialProduct={product} slug={slug} />;
}
