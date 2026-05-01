import type { Metadata } from 'next';

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL?.trim() ||
  process.env.NEXT_PUBLIC_DOMAIN?.trim() ||
  'https://188.com.vn';

function absoluteOrigin(raw: string): string {
  const t = raw.replace(/\/$/, '');
  if (!t) return 'https://188.com.vn';
  if (/^https?:\/\//i.test(t)) return t;
  return `https://${t.replace(/^\/+/, '')}`;
}

const origin = absoluteOrigin(SITE_URL);

/** Metadata riêng — trang client vẫn có <title> / OG / canonical tốt trên mobile (Safari share, tab). */
export const metadata: Metadata = {
  title: 'Tìm theo ảnh',
  description:
    'Tải ảnh hoặc dán link HTTPS — tìm sản phẩm tương tự trên 188.COM.VN (NanoAI). Giao diện gọn, thao tác nhanh trên điện thoại.',
  alternates: {
    canonical: `${origin}/tim-theo-anh`,
  },
  openGraph: {
    type: 'website',
    locale: 'vi_VN',
    siteName: '188.COM.VN',
    url: `${origin}/tim-theo-anh`,
    title: 'Tìm theo ảnh | 188.COM.VN',
    description:
      'Tìm sản phẩm bằng hình: chụp, chọn file hoặc dán URL ảnh. Hỗ trợ tìm nhanh khi dùng Safari / Chrome trên mobile.',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Tìm theo ảnh | 188.COM.VN',
    description: 'Tìm sản phẩm bằng ảnh trên 188.COM.VN.',
  },
  robots: { index: true, follow: true },
  appleWebApp: {
    capable: true,
    title: '188 — Tìm ảnh',
  },
  formatDetection: {
    telephone: false,
    email: false,
    address: false,
  },
};

export default function TimTheoAnhLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
