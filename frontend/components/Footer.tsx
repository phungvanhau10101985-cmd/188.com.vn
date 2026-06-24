'use client';

import Link from 'next/link';
import Image from 'next/image';
import dynamic from 'next/dynamic';
import {
  BOCT_REGISTRATION_URL,
  BUSINESS_ADDRESS,
  BUSINESS_EMAIL,
  BUSINESS_LEGAL_NAME,
  BUSINESS_PHONE_DISPLAY,
  BUSINESS_REGISTRATION,
} from '@/lib/business-info';

const FooterNewsletterSubscribe = dynamic(
  () => import('@/components/FooterNewsletterSubscribe'),
  {
    ssr: false,
    loading: () => (
      <div className="space-y-2">
        <h5 className="text-xs font-semibold uppercase tracking-wider text-gray-900">Đăng ký nhận tin</h5>
        <p className="text-xs text-gray-600">Nhận ưu đãi và tin sale qua email — không spam.</p>
        <div className="flex gap-2" aria-hidden="true">
          <div className="flex-1 min-h-[44px] rounded-xl border border-gray-200 bg-gray-50" />
          <div className="min-h-[44px] min-w-[72px] rounded-xl bg-orange-200/80" />
        </div>
      </div>
    ),
  },
);

export default function Footer() {
  const supportLinks = [
    { href: '/info/lien-he', label: 'Thông tin liên hệ' },
    { href: '/info/chinh-sach-giao-hang', label: 'Chính sách giao hàng' },
    { href: '/info/doi-tra-hoan-tien', label: 'Đổi trả & Hoàn tiền' },
  ];
  const policyLinks = [
    { href: '/info/chinh-sach-bao-mat', label: 'Chính sách bảo mật' },
    { href: '/info/dieu-khoan-su-dung', label: 'Điều khoản sử dụng' },
    { href: '/info/huong-dan-mua-hang', label: 'Hướng dẫn mua hàng' },
  ];

  const fullAddress = `${BUSINESS_ADDRESS.streetAddress}, ${BUSINESS_ADDRESS.addressLocality}, ${BUSINESS_ADDRESS.addressRegion}`;

  return (
    <footer className="bg-white text-gray-900 pb-20 md:pb-0">
      <div className="max-w-7xl mx-auto px-4 py-8 md:py-14">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8 md:gap-10">
          {/* Brand */}
          <div className="space-y-5">
            <Link
              href="/"
              aria-label="188.com.vn — Trang chủ"
              className="flex items-center gap-3"
            >
              <Image
                src="https://188comvn.b-cdn.net/logo188.png"
                data-allow-png
                alt="188.com.vn - Xem là thích click là mê"
                width={160}
                height={48}
                className="h-12 w-auto object-contain"
              />
              <div>
                <h3 className="text-lg font-bold tracking-tight text-gray-900">188.com.vn</h3>
                <p className="text-gray-600 text-xs font-medium uppercase tracking-wider">
                  Xem là thích · Click là mê
                </p>
              </div>
            </Link>
            <p className="text-gray-700 text-sm leading-relaxed max-w-xs">
              Nhà bán lẻ thời trang nam nữ trực tuyến — sản phẩm đúng mô tả, giá minh bạch, giao hàng toàn quốc.
            </p>
            <p className="text-gray-600 text-xs leading-relaxed max-w-xs">
              {BUSINESS_LEGAL_NAME} · Mã HKD {BUSINESS_REGISTRATION}
            </p>
          </div>

          {/* Hỗ trợ khách hàng */}
          <div className="space-y-4">
            <h4 className="text-sm font-semibold uppercase tracking-wider text-gray-900">Hỗ trợ khách hàng</h4>
            <div className="space-y-2.5 text-sm text-gray-700">
              {supportLinks.map(({ href, label }) => (
                <Link key={href} href={href} className="block text-gray-700 hover:text-gray-900 transition-colors">{label}</Link>
              ))}
              <Link href="/info/gioi-thieu" className="block text-gray-700 hover:text-gray-900 transition-colors">Giới thiệu</Link>
            </div>
            <a
              href={BOCT_REGISTRATION_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[#ea580c] text-white font-medium shadow-md hover:bg-orange-600 hover:shadow-lg transition-all focus:outline-none focus:ring-2 focus:ring-orange-400 focus:ring-offset-2 text-sm mt-4"
            >
              <span aria-hidden>✓</span>
              Đã đăng ký Bộ Công Thương
            </a>
          </div>

          {/* Chính sách */}
          <div className="space-y-4">
            <h4 className="text-sm font-semibold uppercase tracking-wider text-gray-900">Chính sách</h4>
            <div className="space-y-2.5 text-sm text-gray-700">
              {policyLinks.map(({ href, label }) => (
                <Link key={href} href={href} className="block text-gray-700 hover:text-gray-900 transition-colors">{label}</Link>
              ))}
              <Link href="/info/nguon-goc-thuong-hieu" className="block text-gray-700 hover:text-gray-900 transition-colors">Nguồn gốc & Thương hiệu</Link>
              <Link href="/info/chinh-sach-danh-gia" className="block text-gray-700 hover:text-gray-900 transition-colors">Chính sách đánh giá</Link>
              <Link href="/info/uy-tin" className="block text-gray-700 hover:text-gray-900 transition-colors">188.com.vn có uy tín?</Link>
              <Link href="/info/thong-tin-don-vi" className="block text-gray-700 hover:text-gray-900 transition-colors">Thông tin đơn vị</Link>
            </div>
          </div>

          {/* Contact & Newsletter */}
          <div className="space-y-5">
            <h4 className="text-sm font-semibold uppercase tracking-wider text-gray-900">Liên hệ</h4>
            <div className="space-y-2.5 text-sm text-gray-700">
              <div className="flex flex-wrap gap-x-2 gap-y-1 items-center"><span aria-hidden className="shrink-0">📍</span><span className="break-words min-w-[44px] py-1">{fullAddress}</span></div>
              <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
                <span aria-hidden className="shrink-0">📞</span>
                <a href="tel:0968659836" className="inline-flex min-h-[44px] items-center text-gray-800 hover:text-gray-900 underline-offset-2 transition-colors">{BUSINESS_PHONE_DISPLAY}</a>
              </div>
              <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
                <span aria-hidden className="shrink-0">✉️</span>
                <a href={`mailto:${BUSINESS_EMAIL}`} className="inline-flex min-h-[44px] items-center text-gray-800 hover:text-gray-900 underline-offset-2 transition-colors">{BUSINESS_EMAIL}</a>
              </div>
              <div className="flex items-center gap-2 py-1"><span aria-hidden>🕒</span><span>8:00 – 16:30 (T2–T7)</span></div>
            </div>
            <FooterNewsletterSubscribe />
          </div>
        </div>
      </div>

      <div className="border-t border-gray-200">
        <div className="max-w-7xl mx-auto px-4 py-4 md:py-5">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div className="text-gray-600 text-sm">
              © 2018 – nay 188.com.vn · {BUSINESS_LEGAL_NAME}. Bảo lưu mọi quyền.
            </div>
            <div className="flex flex-wrap items-center gap-4 text-sm text-gray-600">
              <span>Thanh toán: COD · Chuyển khoản · QR SePay</span>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
