'use client';

import { useAuth } from '@/features/auth/hooks/useAuth';
import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { apiClient } from '@/lib/api-client';
import { useToast } from '@/components/ToastProvider';
import AccountSessionActions from '@/components/account/AccountSessionActions';

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
      {/* Mobile layout — chỉ md:hidden; desktop giữ khối hidden md:block bên dưới */}
      <div className="md:hidden bg-white">
        <div className="px-4 pb-3 pt-1 border-b border-gray-100">
          <h1 className="text-base font-bold leading-tight text-gray-900">{user?.full_name || 'Tài khoản'}</h1>
          {user?.phone ? (
            <p className="mt-0.5 text-xs tabular-nums text-gray-500">{user.phone}</p>
          ) : null}
          <Link
            href="/account/profile"
            className="mt-2 inline-flex min-h-[40px] items-center text-xs font-semibold text-[#ea580c] active:opacity-80"
          >
            Chỉnh sửa thông tin cá nhân →
          </Link>
        </div>

        {/* Tabs đơn hàng — cuộn ngang, tránh lưới 6 cột quá chật */}
        <div className="border-b border-gray-100 bg-gray-50/80 px-2 py-2">
          <p className="mb-1.5 px-1 text-[10px] font-semibold uppercase tracking-wide text-gray-500">Đơn hàng</p>
          <div
            className="flex snap-x snap-mandatory gap-2 overflow-x-auto pb-1 scrollbar-hide -mx-1 px-1"
            role="navigation"
            aria-label="Lối tắt trạng thái đơn hàng"
          >
            {tabWithCounts.map((t) => (
              <Link
                key={t.key}
                href={t.key === 'all' ? '/account/orders' : `/account/orders?tab=${encodeURIComponent(t.key)}`}
                className="flex min-h-[44px] shrink-0 snap-start items-center gap-1.5 rounded-xl border border-gray-200/90 bg-white px-3 py-2 text-left shadow-sm ring-1 ring-black/[0.03] active:scale-[0.98] transition-transform"
              >
                <span className="max-w-[6.5rem] text-xs font-medium leading-tight text-gray-900">{t.label}</span>
                <span className="inline-flex min-w-[1.25rem] items-center justify-center rounded-full bg-[#ea580c] px-1.5 py-0.5 text-[10px] font-bold leading-none text-white">
                  {t.count}
                </span>
              </Link>
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
          <Link href="/account/notifications" className="flex items-center justify-between px-4 py-2.5 text-sm text-gray-900">
            <span>🔔 Trung tâm thông báo</span>
            <span className="text-gray-400">›</span>
          </Link>
          <Link href="/account/install-app" className="flex items-center justify-between px-4 py-2.5 text-sm text-gray-900">
            <span>📲 Cài đặt app</span>
            <span className="text-gray-400">›</span>
          </Link>
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

        <div className="px-4 py-4 border-t border-gray-200 bg-[#fafafa]">
          <AccountSessionActions returnPath="/account" />
        </div>
      </div>

      <div className="hidden md:block">
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
            <h2 className="text-xl font-bold text-gray-900">Thông tin tài khoản</h2>
            <Link
              href="/account/profile"
              className="inline-flex items-center rounded-lg bg-[#ea580c] px-4 py-2 text-sm font-semibold text-white hover:bg-[#c2410c] transition-colors"
            >
              Chỉnh sửa hồ sơ
            </Link>
          </div>
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

          <div className="mt-6 pt-6 border-t border-gray-100">
            <AccountSessionActions returnPath="/account" />
          </div>
        </div>
      </div>
    </>
  );
}
