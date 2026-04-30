'use client';

import { useAuth } from '@/features/auth/hooks/useAuth';

type Props = {
  /** Sau khi đăng nhập lại, quay về trang này. */
  returnPath?: string;
};

/**
 * Đăng xuất / đổi tài khoản — đặt trên trang Tài khoản & Hồ sơ, không dùng layout chung
 * (tránh chiếm chỗ trên trang thanh toán cọc, đơn hàng, v.v.).
 */
export default function AccountSessionActions({ returnPath = '/account' }: Props) {
  const { logout, switchAccount } = useAuth();

  return (
    <div className="rounded-xl border border-gray-100 bg-gray-50/90 p-3 space-y-2">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">Phiên đăng nhập</p>
      <div className="flex flex-col sm:flex-row gap-2 sm:gap-3">
        <button
          type="button"
          className="flex-1 rounded-xl border border-blue-200 bg-white px-4 py-3 text-sm font-medium text-blue-700 shadow-sm hover:bg-blue-50 transition-colors"
          onClick={() => switchAccount(returnPath)}
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
    </div>
  );
}
