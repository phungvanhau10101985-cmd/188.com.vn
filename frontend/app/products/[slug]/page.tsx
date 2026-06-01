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

  const redirectOosGroupIfAny = async () => {
    const groupSlug = await resolveProductOosGroupRedirectSlug(slug);
    if (groupSlug) {
      redirect(productOosGroupRedirectPath(groupSlug));
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
