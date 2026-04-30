'use client';

import Link from 'next/link';
import Image from 'next/image';

// frontend/components/Footer.tsx - Đồng bộ thương hiệu 188, có chân trang mobile
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
                alt="188.com.vn - XEM LÀ THÍCH"
                width={160}
                height={48}
                className="h-12 w-auto object-contain"
              />
              <div>
                <h3 className="text-lg font-bold tracking-tight text-gray-900">188.com.vn</h3>
                <p className="text-gray-600 text-xs font-medium uppercase tracking-wider">Xem là thích</p>
              </div>
            </Link>
            <p className="text-gray-700 text-sm leading-relaxed max-w-xs">
              Thời trang nam chất lượng cao, giá hợp lý. Cam kết chính hãng, giao hàng toàn quốc.
            </p>
            <div className="flex gap-3" role="group" aria-label="Mạng xã hội (đang hoàn thiện liên kết)">
              <button
                type="button"
                disabled
                className="min-h-[44px] min-w-[44px] rounded-lg bg-gray-100 text-gray-500 flex items-center justify-center text-sm cursor-not-allowed opacity-70"
                aria-label="Facebook — sắp cập nhật link"
              >
                📘
              </button>
              <button
                type="button"
                disabled
                className="min-h-[44px] min-w-[44px] rounded-lg bg-gray-100 text-gray-500 flex items-center justify-center text-sm cursor-not-allowed opacity-70"
                aria-label="Instagram — sắp cập nhật link"
              >
                📷
              </button>
              <button
                type="button"
                disabled
                className="min-h-[44px] min-w-[44px] rounded-lg bg-gray-100 text-gray-500 flex items-center justify-center text-sm cursor-not-allowed opacity-70"
                aria-label="Twitter — sắp cập nhật link"
              >
                🐦
              </button>
            </div>
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
              href="https://online.gov.vn/Home/WebDetails/137314"
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
              <div className="flex flex-wrap gap-x-2 gap-y-1 items-center"><span aria-hidden className="shrink-0">📍</span><span className="break-words min-w-[44px] py-1">Xóm Buối, Thôn Vật Lại 3, Xã Vật Lại, Ba Vì, Hà Nội</span></div>
              <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
                <span aria-hidden className="shrink-0">📞</span>
                <a href="tel:0968659836" className="inline-flex min-h-[44px] items-center text-gray-800 hover:text-gray-900 underline-offset-2 transition-colors">0968 659 836</a>
              </div>
              <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
                <span aria-hidden className="shrink-0">✉️</span>
                <a href="mailto:hotro@188.com.vn" className="inline-flex min-h-[44px] items-center text-gray-800 hover:text-gray-900 underline-offset-2 transition-colors">hotro@188.com.vn</a>
              </div>
              <div className="flex items-center gap-2 py-1"><span aria-hidden>🕒</span><span>8:00 – 16:30</span></div>
            </div>
            <div className="space-y-2">
              <h5 className="text-xs font-semibold uppercase tracking-wider text-gray-900">Đăng ký nhận tin</h5>
              <div className="flex gap-2">
                <input
                  type="email"
                  placeholder="Email của bạn"
                  className="flex-1 px-3 py-2.5 bg-gray-50 border border-gray-200 rounded-xl text-sm text-gray-900 placeholder-gray-600 focus:outline-none focus:border-orange-500 focus:ring-1 focus:ring-orange-500"
                />
                <button
                  type="submit"
                  className="bg-[#ea580c] text-white hover:bg-orange-600 min-h-[44px] min-w-[72px] px-4 py-2.5 rounded-xl text-sm font-medium transition-colors shadow-sm"
                >
                  Gửi
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="border-t border-gray-200">
        <div className="max-w-7xl mx-auto px-4 py-4 md:py-5">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div className="text-gray-600 text-sm">
              © {new Date().getFullYear()} 188.com.vn. Bảo lưu mọi quyền.
            </div>
            <div className="flex flex-wrap items-center gap-4 text-sm text-gray-600">
              <span>Thanh toán: 💳 🏦 📱</span>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
