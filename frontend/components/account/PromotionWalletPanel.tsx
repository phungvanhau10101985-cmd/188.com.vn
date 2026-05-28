'use client';

import { apiClient, type PromotionVoucherItem } from '@/lib/api-client';
import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';

function formatCurrency(amount: number) {
  return new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(amount);
}

function expiryLabel(voucher: PromotionVoucherItem): string {
  if (!voucher.show_days_remaining) return 'Không giới hạn';
  if (voucher.days_remaining == null) return 'Đang cập nhật';
  if (voucher.days_remaining <= 0) return 'Hết hạn';
  if (voucher.days_remaining === 1) return 'Còn 1 ngày';
  return `Còn ${voucher.days_remaining} ngày`;
}

function sourceLabel(source?: string | null): string {
  switch (source) {
    case 'signup':
      return 'Quà chào mừng';
    case 'first_delivered':
      return 'Cảm ơn bạn đã mua';
    case 'comeback':
      return 'Quà quay lại';
    case 'admin':
      return 'Quà từ shop';
    case 'welcome_backfill':
      return 'Quà chào mừng';
    case 'cart_abandon':
      return 'Nhắc giỏ hàng';
    default:
      return 'Quà riêng';
  }
}

type PromotionWalletPanelProps = {
  /** Hiển thị trong layout tài khoản (không full-page hero) */
  embedded?: boolean;
};

export default function PromotionWalletPanel({ embedded = false }: PromotionWalletPanelProps) {
  const [vouchers, setVouchers] = useState<PromotionVoucherItem[]>([]);
  const [loadingData, setLoadingData] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copiedCode, setCopiedCode] = useState<string | null>(null);

  const loadWallet = useCallback(async () => {
    setLoadingData(true);
    setError(null);
    try {
      const res = await apiClient.getWelcomePromoProgram();
      setVouchers(res.items ?? []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Không tải được ví khuyến mãi');
    } finally {
      setLoadingData(false);
    }
  }, []);

  useEffect(() => {
    void loadWallet();
  }, [loadWallet]);

  const handleCopy = async (code: string) => {
    try {
      await navigator.clipboard.writeText(code);
      setCopiedCode(code);
      setTimeout(() => setCopiedCode(null), 2000);
    } catch {
      /* ignore */
    }
  };

  if (loadingData) {
    return (
      <div className={`flex items-center justify-center ${embedded ? 'py-16' : 'min-h-[40vh]'}`}>
        <div className="animate-spin w-10 h-10 border-4 border-[#ea580c] border-t-transparent rounded-full" />
      </div>
    );
  }

  const activeCount = vouchers.filter((v) => v.eligible).length;

  return (
    <div className={embedded ? '' : 'min-h-screen bg-gray-50 pb-12'}>
      {embedded ? (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 md:p-6 mb-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700">Ví quà riêng</p>
          <h1 className="mt-1 text-xl md:text-2xl font-bold text-gray-900">Khuyến mãi của bạn</h1>
          <p className="mt-2 text-sm text-gray-600">
            {activeCount > 0
              ? `Bạn có ${activeCount} mã có thể dùng ngay — chọn mã khi thanh toán trong giỏ hàng.`
              : 'Mã quà sẽ xuất hiện khi shop tặng bạn (đăng ký, nhận hàng, dịp đặc biệt).'}
          </p>
        </div>
      ) : (
        <div className="bg-gradient-to-r from-emerald-600 to-teal-600 text-white pt-10 pb-20 px-4">
          <div className="max-w-3xl mx-auto">
            <p className="text-emerald-100 text-sm font-medium mb-2">Ví quà riêng của bạn</p>
            <h1 className="text-2xl md:text-3xl font-bold">Khuyến mãi</h1>
            <p className="mt-2 text-emerald-50 text-sm md:text-base">
              {activeCount > 0
                ? `Bạn có ${activeCount} mã có thể dùng ngay`
                : 'Mã quà sẽ xuất hiện khi shop tặng bạn — theo dõi thông báo nhé'}
            </p>
          </div>
        </div>
      )}

      <div className={embedded ? 'space-y-4' : 'max-w-3xl mx-auto px-4 -mt-12 space-y-4'}>
        {error ? (
          <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}{' '}
            <button type="button" onClick={() => void loadWallet()} className="underline font-medium">
              Thử lại
            </button>
          </div>
        ) : null}

        {vouchers.length === 0 ? (
          <div className="bg-white rounded-2xl shadow-lg border border-gray-100 p-8 text-center">
            <p className="text-4xl mb-3" aria-hidden>
              🎁
            </p>
            <h2 className="text-lg font-semibold text-gray-900">Chưa có mã trong ví</h2>
            <p className="mt-2 text-sm text-gray-600 max-w-md mx-auto">
              Shop sẽ tặng mã qua thông báo khi bạn đăng ký, nhận hàng hoặc các dịp đặc biệt. Mã chỉ dành
              riêng cho bạn — không hiển thị công khai.
            </p>
            <Link
              href="/"
              className="inline-flex mt-6 items-center justify-center rounded-xl bg-[#ea580c] px-6 py-3 text-sm font-semibold text-white hover:bg-[#c2410c]"
            >
              Tiếp tục mua sắm
            </Link>
          </div>
        ) : (
          vouchers.map((voucher) => (
            <div
              key={`${voucher.grant_id ?? voucher.code}`}
              className={`bg-white rounded-2xl shadow-lg border overflow-hidden ${
                voucher.eligible ? 'border-emerald-200' : 'border-gray-100 opacity-80'
              }`}
            >
              <div className="p-5 md:p-6">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      {voucher.is_new ? (
                        <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-bold uppercase text-rose-700">
                          Mới
                        </span>
                      ) : null}
                      <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-800">
                        {sourceLabel(voucher.source)}
                      </span>
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                          voucher.eligible ? 'bg-emerald-100 text-emerald-800' : 'bg-gray-100 text-gray-600'
                        }`}
                      >
                        {voucher.eligible ? 'Dùng được' : 'Không dùng được'}
                      </span>
                    </div>
                    <h2 className="mt-2 text-lg font-bold text-gray-900">{voucher.name}</h2>
                    <p className="mt-1 text-sm text-gray-600">{voucher.description}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-3xl font-bold text-[#ea580c]">-{voucher.discount_percent}%</p>
                    <p className="text-xs text-gray-500">Tối đa {formatCurrency(voucher.max_discount_amount)}</p>
                  </div>
                </div>

                <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="rounded-xl bg-gray-50 px-4 py-3">
                    <p className="text-xs text-gray-500 uppercase">Mã của bạn</p>
                    <div className="mt-1 flex items-center justify-between gap-2">
                      <span className="font-mono text-lg font-bold">{voucher.code}</span>
                      <button
                        type="button"
                        onClick={() => void handleCopy(voucher.code)}
                        className="text-sm font-medium text-[#ea580c]"
                      >
                        {copiedCode === voucher.code ? 'Đã copy' : 'Copy'}
                      </button>
                    </div>
                  </div>
                  <div className="rounded-xl bg-gray-50 px-4 py-3">
                    <p className="text-xs text-gray-500 uppercase">Thời hạn</p>
                    <p
                      className={`mt-1 font-bold ${
                        voucher.eligible ? 'text-emerald-700' : 'text-gray-600'
                      }`}
                    >
                      {expiryLabel(voucher)}
                    </p>
                  </div>
                </div>

                {!voucher.eligible && voucher.reason ? (
                  <p className="mt-3 text-sm text-amber-800 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
                    {voucher.reason}
                  </p>
                ) : null}

                {voucher.eligible ? (
                  <Link
                    href="/cart"
                    className="inline-flex mt-4 w-full sm:w-auto items-center justify-center rounded-xl bg-[#ea580c] px-6 py-3 text-sm font-semibold text-white hover:bg-[#c2410c]"
                  >
                    Chọn mã tại giỏ hàng
                  </Link>
                ) : null}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
