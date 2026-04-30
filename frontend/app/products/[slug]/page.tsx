import { getProductBySlugForSSR } from '@/lib/product-seo';
import ProductDetailClient from './ProductDetailClient';
import ErrorState from './components/ErrorState/ErrorState';

type Props = { params: { slug: string } };

export default async function ProductDetailPage({ params }: Props) {
  const { slug } = params;
  const product = await getProductBySlugForSSR(slug);

  if (!product) {
    return <ErrorState error="Không tìm thấy sản phẩm" />;
  }

  return <ProductDetailClient initialProduct={product} slug={slug} />;
}
