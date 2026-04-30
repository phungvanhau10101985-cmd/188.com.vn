'use client';

import { useAuth } from '@/features/auth/hooks/useAuth';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect } from 'react';

export default function AccountLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { isAuthenticated, isLoading } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/auth/login?redirect=' + encodeURIComponent(pathname || '/account'));
    }
  }, [isAuthenticated, isLoading, router, pathname]);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="animate-spin w-10 h-10 border-2 border-blue-600 border-t-transparent rounded-full" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  const nav = [
    { href: '/account', label: 'Tài khoản', icon: '👤' },
    { href: '/account/profile', label: 'Chỉnh sửa hồ sơ', icon: '✏️' },
    { href: '/cart', label: 'Giỏ hàng', icon: '🛒' },
    { href: '/account/orders', label: 'Đơn hàng', icon: '🧾' },
    { href: '/da-xem', label: 'Sản phẩm đã xem', icon: '🕒' },
    { href: '/account/addresses', label: 'Sổ địa chỉ', icon: '📍' },
    { href: '/vi-dien-tu', label: 'Ví điện tử', icon: '💳' },
    { href: '/thanh-vien', label: 'Thành viên thân quen', icon: '👥' },
    { href: '/account/notifications', label: 'Trung tâm thông báo', icon: '🔔' },
    { href: '/tai-khoan-ngan-hang', label: 'Tài khoản ngân hàng', icon: '🏦' },
    { href: '/nhan-tin', label: 'Nhắn tin', icon: '💬' },
    { href: '/favorites', label: 'Sản phẩm yêu thích', icon: '❤️' },
    { href: '/account/change-password', label: 'Đổi mật khẩu', icon: '🔑' },
  ];

  return (
    <div className="min-h-screen bg-gray-50 pt-2 pb-4 md:pt-3 md:pb-6">
      <div className="max-w-7xl mx-auto px-4">
        <div className="flex flex-col md:flex-row gap-4 md:gap-6">
          <aside className="hidden md:block md:w-56 flex-shrink-0">
            <nav className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
              {nav.map((item) => {
                const active = pathname === item.href;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`flex items-center gap-3 px-4 py-3 text-left font-medium transition-colors ${
                      active
                        ? 'bg-blue-50 text-blue-700 border-l-4 border-blue-600'
                        : 'text-gray-700 hover:bg-gray-50 border-l-4 border-transparent'
                    }`}
                  >
                    <span className="w-6 text-center">{item.icon}</span>
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </nav>
          </aside>
          <main className="flex-1 min-w-0">
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}
