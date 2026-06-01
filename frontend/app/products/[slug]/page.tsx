import { redirect } from 'next/navigation';
import { getProductBySlugForSSR } from '@/lib/product-seo';
import {
  productOosGroupRedirectPath,
  resolveProductOosGroupRedirectSlug,
} from '@/lib/product-oos-redirect';
import ProductDetailClient from './ProductDetailClient';
import ErrorState from './components/ErrorState/ErrorState';

type Props = { params: Promise<{ slug: string }> };

export default async function ProductDetailPage({ params }: Props) {
  const { slug } = await params;
  const product = await getProductBySlugForSSR(slug);

  if (!product) {
    return <ErrorState error="Không tìm thấy sản phẩm" />;
  }

  if ((product.available ?? 0) <= 0) {
    const groupSlug = await resolveProductOosGroupRedirectSlug(slug);
    if (groupSlug) {
      redirect(productOosGroupRedirectPath(groupSlug));
    }
  }

  return <ProductDetailClient initialProduct={product} slug={slug} />;
}
