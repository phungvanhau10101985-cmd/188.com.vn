import type { Metadata } from 'next';
import NanoAiEmbedRouteMode from '@/components/NanoAiEmbedRouteMode';

export const metadata: Metadata = {
  title: 'Lướt video cùng shop',
  description:
    'Video sản phẩm gợi ý theo shop Trung Quốc bạn vừa xem (shop_name_chinese / cột AM), ưu tiên cùng danh mục cấp 2.',
  robots: { index: false, follow: true },
};

export default function LuotVideoCungShopLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <NanoAiEmbedRouteMode primary="try_on" tryOnLabel="Thử đồ" />
      {children}
    </>
  );
}
