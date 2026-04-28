'use client';

import { useAuth } from '@/features/auth/hooks/useAuth';
import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { apiClient } from '@/lib/api-client';
import { useToast } from '@/components/ToastProvider';

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

export default function AccountPage() {
  const { user, isAuthenticated } = useAuth();
  const { pushToast } = useToast();
  const [orders, setOrders] = useState<OrderLite[]>([]);

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

  const notReady = () => pushToast({ title: 'Tính năng đang phát triển', variant: 'info', durationMs: 2000 });

  return (
    <>
      {/* Mobile layout */}
      <div className="md:hidden bg-white">
        <div className="px-4 py-3 border-b border-gray-200">
          <h1 className="text-lg font-bold text-gray-900">{user?.full_name || 'Tài khoản'}</h1>
          <Link href="/account" className="text-xs text-blue-600 font-medium">
            Chỉnh sửa thông tin cá nhân
          </Link>
        </div>

        {/* Tabs quản lý đơn hàng */}
        <div className="px-2 py-1.5 border-b border-gray-200">
          <div className="grid grid-cols-6 gap-1 mb-1">
            {tabWithCounts.map((t) => (
              <Link
                key={t.key}
                href={t.key === 'all' ? '/account/orders' : `/account/orders?tab=${encodeURIComponent(t.key)}`}
                className="text-[11px] font-medium border-b-2 border-transparent text-gray-600 text-center leading-tight hover:text-gray-900 min-h-[28px] pt-2"
              >
                {t.label}
              </Link>
            ))}
          </div>
          <div className="grid grid-cols-6 gap-1">
            {tabWithCounts.map((t) => (
              <div key={t.key} className="flex justify-center">
                <span className="inline-flex items-center justify-center min-w-[18px] h-4 px-1 rounded-full bg-orange-500 text-white text-[10px] font-bold">
                  {t.count}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Menu list */}
        <div className="divide-y divide-gray-200">
          <Link href="/cart" className="flex items-center justify-between px-4 py-2.5 text-sm text-gray-900">
            <span>🛒 Giỏ hàng</span>
            <span className="text-gray-400">›</span>
          </Link>
          <Link href="/account/orders" className="flex items-center justify-between px-4 py-2.5 text-sm text-gray-900">
            <span>🧾 Đơn hàng</span>
            <span className="text-gray-400">›</span>
          </Link>
          <Link href="/da-xem" className="flex items-center justify-between px-4 py-2.5 text-sm text-gray-900">
            <span>🕒 Sản phẩm đã xem</span>
            <span className="text-gray-400">›</span>
          </Link>
          <Link href="/account/addresses" className="flex items-center justify-between px-4 py-2.5 text-sm text-gray-900">
            <span>📍 Sổ địa chỉ</span>
            <span className="text-gray-400">›</span>
          </Link>
          <button onClick={notReady} className="w-full flex items-center justify-between px-4 py-2.5 text-sm text-gray-900">
            <span>💳 Ví điện tử</span>
            <span className="text-gray-400">›</span>
          </button>
          <button onClick={notReady} className="w-full flex items-center justify-between px-4 py-2.5 text-sm text-gray-900">
            <span>👥 Thành viên thân quen</span>
            <span className="text-gray-400">›</span>
          </button>
          <button onClick={notReady} className="w-full flex items-center justify-between px-4 py-2.5 text-sm text-gray-900">
            <span>🔔 Trung tâm thông báo</span>
            <span className="text-gray-400">›</span>
          </button>
          <button onClick={notReady} className="w-full flex items-center justify-between px-4 py-2.5 text-sm text-gray-900">
            <span>🏦 Tài khoản ngân hàng</span>
            <span className="text-gray-400">›</span>
          </button>
          <button onClick={notReady} className="w-full flex items-center justify-between px-4 py-2.5 text-sm text-gray-900">
            <span>💬 Nhắn tin</span>
            <span className="text-gray-400">›</span>
          </button>
          <Link href="/favorites" className="flex items-center justify-between px-4 py-2.5 text-sm text-gray-900">
            <span>❤️ Sản phẩm yêu thích</span>
            <span className="text-gray-400">›</span>
          </Link>
          <button onClick={notReady} className="w-full flex items-center justify-between px-4 py-2.5 text-sm text-gray-900">
            <span>🔑 Đổi mật khẩu</span>
            <span className="text-gray-400">›</span>
          </button>
        </div>
      </div>

      <div className="hidden md:block">
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
          <h2 className="text-xl font-bold text-gray-900 mb-4">Thông tin tài khoản</h2>
          <dl className="space-y-3">
            <div>
              <dt className="text-sm text-gray-500">Họ tên</dt>
              <dd className="font-medium text-gray-900">{user?.full_name ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-sm text-gray-500">Số điện thoại</dt>
              <dd className="font-medium text-gray-900">{user?.phone ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-sm text-gray-500">Email</dt>
              <dd className="font-medium text-gray-900">{user?.email ?? '—'}</dd>
            </div>
          </dl>
          <div className="mt-6">
            <Link
              href="/account/addresses"
              className="inline-flex items-center text-blue-600 font-medium hover:text-blue-700"
            >
              Quản lý sổ địa chỉ →
            </Link>
          </div>
        </div>
      </div>
    </>
  );
}
