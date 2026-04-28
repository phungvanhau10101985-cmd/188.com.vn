'use client';

import { useAuth } from '@/features/auth/hooks/useAuth';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import { apiClient } from '@/lib/api-client';

interface OrderLite {
  id: number;
  status: string;
}

const ORDER_TABS = [
  { key: 'all', label: 'Tất cả', statuses: null as string[] | null },
  { key: 'waiting_deposit', label: 'Chờ đặt cọc', statuses: ['waiting_deposit'] },
  { key: 'waiting_receive', label: 'Chờ nhận hàng', statuses: ['deposit_paid', 'confirmed', 'processing', 'shipping'] },
  { key: 'delivered', label: 'Đã nhận hàng', statuses: ['delivered'] },
  { key: 'completed', label: 'Đã đánh giá', statuses: ['completed'] },
  { key: 'cancelled', label: 'Đã hủy', statuses: ['cancelled'] },
];

function matchTab(order: OrderLite, tab: (typeof ORDER_TABS)[0]): boolean {
  if (tab.key === 'all') return true;
  if (!tab.statuses) return false;
  return tab.statuses.includes(order.status);
}

export default function AccountLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { isAuthenticated, isLoading, logout, switchAccount } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [orders, setOrders] = useState<OrderLite[]>([]);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/auth/login?redirect=' + encodeURIComponent(pathname || '/account'));
    }
  }, [isAuthenticated, isLoading, router, pathname]);

  useEffect(() => {
    if (isAuthenticated) {
      apiClient
        .getOrders({ limit: 200 })
        .then((data) => setOrders(Array.isArray(data) ? data : []))
        .catch(() => setOrders([]));
    }
  }, [isAuthenticated]);

  const tabWithCounts = useMemo(() => {
    return ORDER_TABS.map((t) => {
      const count = t.key === 'all' ? orders.length : orders.filter((o) => matchTab(o, t)).length;
      return { ...t, count };
    });
  }, [orders]);

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
              <div className="border-t border-gray-200 p-3 space-y-2 bg-gray-50/90">
                <button
                  type="button"
                  className="w-full rounded-lg border border-blue-200 bg-white px-3 py-2.5 text-sm font-medium text-blue-700 hover:bg-blue-50 transition-colors"
                  onClick={() => switchAccount(pathname || '/account')}
                  aria-label="Chuyển sang đăng nhập tài khoản khác"
                >
                  Chuyển tài khoản khác
                </button>
                <button
                  type="button"
                  className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2.5 text-sm font-medium text-gray-800 hover:bg-gray-100 transition-colors"
                  onClick={() => logout()}
                  aria-label="Đăng xuất khỏi tài khoản"
                >
                  Đăng xuất
                </button>
              </div>
            </nav>
          </aside>
          <main className="flex-1 min-w-0">
            <div className="md:hidden flex flex-col sm:flex-row gap-2 sm:gap-3 mb-3">
              <button
                type="button"
                className="flex-1 rounded-xl border border-blue-200 bg-white px-4 py-3 text-sm font-medium text-blue-700 shadow-sm hover:bg-blue-50 transition-colors"
                onClick={() => switchAccount(pathname || '/account')}
                aria-label="Chuyển sang đăng nhập tài khoản khác"
              >
                Chuyển tài khoản khác
              </button>
              <button
                type="button"
                className="flex-1 rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm font-medium text-gray-800 shadow-sm hover:bg-gray-50 transition-colors"
                onClick={() => logout()}
                aria-label="Đăng xuất khỏi tài khoản"
              >
                Đăng xuất
              </button>
            </div>
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}
