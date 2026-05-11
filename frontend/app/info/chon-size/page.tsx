import Link from 'next/link';
import InfoPageLayout from '@/components/info/InfoPageLayout';
import {
  ALL_CAT2_GUIDE_KEYS,
  ALL_SIZE_GUIDE_SLUGS,
  SIZE_GUIDE_CAT2_TITLES,
  titleForSizeGuideSlug,
} from '@/lib/category-size-guide-meta';

export const metadata = {
  title: 'Chọn size theo nhóm hàng | 188.com.vn',
  description:
    'Danh sách hướng dẫn đo và chọn kích cỡ theo từng nhóm danh mục và một số nhóm con cụ thể tại 188.com.vn.',
};

export default function InfoChonSizeIndexPage() {
  return (
    <InfoPageLayout title="Chọn size theo nhóm hàng">
      <p className="text-sm text-zinc-600 mb-6">
        Chọn nhóm hàng dưới đây để xem bảng tham khảo đo (cm) và gợi ý chọn cỡ. Trên từng trang sản phẩm, luôn ưu tiên mô tả và bảng biến thể do shop đăng.
      </p>
      <h2 className="text-base font-semibold text-zinc-900 mb-3">Nhóm cấp 1</h2>
      <ul className="grid gap-2 sm:grid-cols-2 list-none p-0 m-0 mb-10">
        {ALL_SIZE_GUIDE_SLUGS.map((slug) => (
          <li key={slug}>
            <Link
              href={`/info/chon-size/${slug}`}
              className="block rounded-xl border border-zinc-200 bg-zinc-50/80 px-4 py-3 text-sm font-medium text-zinc-800 hover:border-orange-200 hover:bg-orange-50/80 transition-colors"
            >
              {titleForSizeGuideSlug(slug)}
            </Link>
          </li>
        ))}
      </ul>
      <h2 className="text-base font-semibold text-zinc-900 mb-2">Nhóm con có bảng riêng</h2>
      <p className="text-xs text-zinc-500 mb-3">
        Áp dụng khi taxonomy có đủ hai cấp tương ứng; popup PDP hiển thị nội dung các trang dưới nếu khớp taxonomy.
      </p>
      <ul className="grid gap-2 sm:grid-cols-2 list-none p-0 m-0">
        {ALL_CAT2_GUIDE_KEYS.map((key) => (
          <li key={key}>
            <Link
              href={`/info/chon-size/${key}`}
              className="block rounded-xl border border-orange-100 bg-orange-50/60 px-4 py-3 text-sm font-medium text-zinc-800 hover:border-orange-200 hover:bg-orange-50 transition-colors"
            >
              {SIZE_GUIDE_CAT2_TITLES[key]}
            </Link>
          </li>
        ))}
      </ul>
    </InfoPageLayout>
  );
}
