'use client';

import Link from 'next/link';
import type { PromotionVoucherItem } from '@/lib/api-client';

function formatCurrency(amount: number) {
  return new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(amount);
}

function expiryLabel(voucher: PromotionVoucherItem): string | null {
  if (!voucher.show_days_remaining) return null;
  if (voucher.days_remaining == null) {
    return voucher.eligible_within_days ? `${voucher.eligible_within_days} ngày kể từ đăng ký` : null;
  }
  if (voucher.days_remaining <= 0) return 'Hết hạn';
  if (voucher.days_remaining === 1) return 'Còn 1 ngày';
  return `Còn ${voucher.days_remaining} ngày`;
}

type CartVoucherPickerProps = {
  vouchers: PromotionVoucherItem[];
  loading?: boolean;
  appliedCode: string | null;
  applying?: boolean;
  disabled?: boolean;
  onSelect: (voucher: PromotionVoucherItem) => void;
  onClear: () => void;
};

export default function CartVoucherPicker({
  vouchers,
  loading = false,
  appliedCode,
  applying = false,
  disabled = false,
  onSelect,
  onClear,
}: CartVoucherPickerProps) {
  if (loading) {
    return (
      <div className="mb-3 rounded-xl border border-gray-200 bg-white px-4 py-6 text-center text-sm text-gray-500">
        Đang tải mã khuyến mãi...
      </div>
    );
  }

  if (vouchers.length === 0) {
    return (
      <div className="mb-3 rounded-xl border border-dashed border-gray-200 bg-white px-4 py-5 text-sm text-gray-500">
        Bạn chưa có mã trong ví. Shop sẽ tặng qua thông báo khi có ưu đãi riêng.{' '}
        <Link href="/account/khuyen-mai" className="text-[#ea580c] font-medium hover:underline">
          Xem ví khuyến mãi
        </Link>
      </div>
    );
  }

  const eligibleCount = vouchers.filter((v) => v.eligible).length;

  return (
    <div className="mb-3">
      <div className="flex items-center justify-between gap-2 mb-2">
        <p className="text-xs font-medium text-gray-600 uppercase tracking-wide">Chọn mã giảm giá</p>
        {appliedCode ? (
          <button
            type="button"
            onClick={onClear}
            disabled={applying}
            className="text-xs font-medium text-gray-500 hover:text-gray-800 underline"
          >
            Bỏ chọn mã
          </button>
        ) : null}
      </div>

      <div className="space-y-2" role="radiogroup" aria-label="Chọn mã giảm giá">
        {vouchers.map((voucher) => {
          const selected = appliedCode === voucher.code;
          const canSelect = voucher.eligible && !disabled && !applying;
          const expiry = expiryLabel(voucher);

          return (
            <button
              key={voucher.code}
              type="button"
              role="radio"
              aria-checked={selected}
              disabled={!canSelect && !selected}
              onClick={() => {
                if (selected) {
                  onClear();
                  return;
                }
                if (canSelect) onSelect(voucher);
              }}
              className={`w-full text-left rounded-xl border px-3 py-3 transition-colors ${
                selected
                  ? 'border-[#ea580c] bg-orange-50/80 ring-1 ring-[#ea580c]/30'
                  : voucher.eligible
                    ? 'border-gray-200 bg-white hover:border-[#ea580c]/40 hover:bg-orange-50/30'
                    : 'border-gray-100 bg-gray-50 opacity-70 cursor-not-allowed'
              }`}
            >
              <div className="flex items-start gap-3">
                <span
                  className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${
                    selected
                      ? 'border-[#ea580c] bg-[#ea580c]'
                      : voucher.eligible
                        ? 'border-gray-300 bg-white'
                        : 'border-gray-200 bg-gray-100'
                  }`}
                  aria-hidden
                >
                  {selected ? <span className="h-1.5 w-1.5 rounded-full bg-white" /> : null}
                </span>

                <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span className="font-mono text-sm font-bold text-gray-900">{voucher.code}</span>
                      {voucher.is_new ? (
                        <span className="rounded-full bg-rose-100 px-1.5 py-0.5 text-[10px] font-bold uppercase text-rose-700">
                          Mới
                        </span>
                      ) : null}
                    <span className="text-xs font-semibold text-[#ea580c]">
                      -{voucher.discount_percent}%
                    </span>
                    {expiry ? (
                      <span
                        className={`text-[11px] font-medium ${
                          voucher.eligible ? 'text-emerald-700' : 'text-gray-500'
                        }`}
                      >
                        {expiry}
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-0.5 text-sm font-medium text-gray-800">{voucher.name}</p>
                  {voucher.description ? (
                    <p className="mt-0.5 text-xs text-gray-500 line-clamp-2">{voucher.description}</p>
                  ) : null}
                  <p className="mt-1 text-[11px] text-gray-500">
                    Tối đa {formatCurrency(voucher.max_discount_amount)}
                    {voucher.eligible && voucher.estimated_discount != null && voucher.estimated_discount > 0
                      ? ` · Tiết kiệm ${formatCurrency(voucher.estimated_discount)}`
                      : ''}
                  </p>
                  {!voucher.eligible && voucher.reason ? (
                    <p className="mt-1 text-[11px] text-amber-700">{voucher.reason}</p>
                  ) : null}
                </div>
              </div>
            </button>
          );
        })}
      </div>

      {eligibleCount === 0 ? (
        <p className="mt-2 text-xs text-gray-500">
          Hiện không có mã dùng được cho đơn này.{' '}
          <Link href="/account/khuyen-mai" className="text-[#ea580c] hover:underline">
            Xem chi tiết
          </Link>
        </p>
      ) : applying ? (
        <p className="mt-2 text-xs text-gray-500">Đang áp dụng mã...</p>
      ) : null}
    </div>
  );
}
