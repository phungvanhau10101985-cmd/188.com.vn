import { notFound } from 'next/navigation';
import InfoPageLayout from '@/components/info/InfoPageLayout';
import SizeGuideBody from '@/components/category-size-guide/SizeGuideBody';
import {
  allChonSizeStaticSlugParams,
  isValidChonSizeSlugParam,
  titleForSizeGuideSegments,
} from '@/lib/category-size-guide-meta';

export function generateStaticParams() {
  return allChonSizeStaticSlugParams();
}

type Props = { params: Promise<{ slug: string[] }> };

export async function generateMetadata({ params }: Props) {
  const { slug } = await params;
  if (!isValidChonSizeSlugParam(slug)) {
    return { title: 'Chọn size | 188.com.vn' };
  }
  return {
    title: `${titleForSizeGuideSegments(slug)} — Chọn size | 188.com.vn`,
    description:
      'Hướng dẫn đo và chọn cỡ áo quần, giày dép và các nhóm hàng trên 188.com.vn. Thông tin tham khảo; luôn ưu tiên mô tả từng sản phẩm.',
  };
}

export default async function InfoChonSizeCatchAllPage({ params }: Props) {
  const { slug } = await params;
  if (!isValidChonSizeSlugParam(slug)) {
    notFound();
  }

  const title = `${titleForSizeGuideSegments(slug)} — Chọn size`;
  const cat1 = slug[0];
  const cat2 = slug.length >= 2 ? slug[1] : undefined;

  return (
    <InfoPageLayout title={title}>
      <SizeGuideBody categoryLevel1Slug={cat1} categoryLevel2Slug={cat2} />
    </InfoPageLayout>
  );
}
