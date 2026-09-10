import type { Metadata } from 'next';
import { getSiteOrigin } from '@/lib/site-origin';
import { MOBILE_SEARCH_HREF } from '@/lib/mobile-search-path';

const origin = getSiteOrigin();

export const metadata: Metadata = {
  title: 'Tìm kiếm',
  description: 'Tìm sản phẩm trên 188.COM.VN — gõ từ khóa, xem gợi ý hoặc tìm theo ảnh.',
  alternates: {
    canonical: `${origin}${MOBILE_SEARCH_HREF}`,
  },
  robots: { index: false, follow: true },
  openGraph: {
    type: 'website',
    locale: 'vi_VN',
    siteName: '188.COM.VN',
    url: `${origin}${MOBILE_SEARCH_HREF}`,
    title: 'Tìm kiếm | 188.COM.VN',
    description: 'Tìm sản phẩm trên 188.COM.VN.',
  },
};

export default function TimKiemLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
