'use client';

import { useMemo, useState } from 'react';
import type { Product, WarehouseClearanceVariant } from '@/types/api';
import { formatPrice } from '@/lib/utils';
import { warehouseVariantAsProduct, warehouseVariantsInStock } from '@/lib/warehouse-clearance';

type WarehouseClearanceBlockProps = {
  product: Product;
  onAddToCart: (product: Product, quantity: number, selectedSize?: string, selectedColor?: string) => void;
  onBuyNow: (product: Product, quantity: number, selectedSize?: string, selectedColor?: string) => void;
  isCartLoading?: boolean;
};

function variantLabel(v: WarehouseClearanceVariant): string {
  const parts = [v.color, v.size].filter(Boolean);
  return parts.length > 0 ? parts.join(' · ') : v.product_id;
}

export default function WarehouseClearanceBlock({
  product,
  onAddToCart,
  onBuyNow,
  isCartLoading = false,
}: WarehouseClearanceBlockProps) {
  const variants = useMemo(() => warehouseVariantsInStock(product), [product]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [quantity, setQuantity] = useState(1);

  const selected = variants.find((v) => v.id === selectedId) ?? variants[0] ?? null;
  const clearancePct = product.warehouse_clearance?.discount_percent ?? selected?.clearance_percent ?? 0;
  const maxQty = Math.max(1, selected?.available ?? 1);

  if (variants.length === 0) return null;

  const handleAdd = () => {
    if (!selected) return;
    const line = warehouseVariantAsProduct(product, selected);
    onAddToCart(line, quantity, selected.size ?? undefined, selected.color ?? undefined);
  };

  const handleBuy = () => {
    if (!selected) return;
    const line = warehouseVariantAsProduct(product, selected);
    onBuyNow(line, quantity, selected.size ?? undefined, selected.color ?? undefined);
  };

  return (
    <section
      className="rounded-xl border border-amber-200 bg-amber-50/60 p-4 space-y-3"
      aria-label="Hàng thanh lý trong kho"
    >
      <div>
        <p className="text-sm font-semibold text-amber-950">Thanh lý trong kho</p>
        <p className="text-xs text-amber-900/80 mt-0.5">
          Hàng duyệt hoàn — giá riêng
          {clearancePct > 0 ? ` (giảm ${clearancePct}%)` : ''}. Không cộng sale ngày trùng tháng.
        </p>
        {product.source_oos ? (
          <p className="text-xs font-medium text-amber-800 mt-1">
            Nguồn order tạm hết — bạn vẫn có thể mua các dòng kho bên dưới.
          </p>
        ) : null}
      </div>

      <div className="space-y-2" role="listbox" aria-label="Chọn màu size kho thanh lý">
        {variants.map((v) => {
          const active = selected?.id === v.id;
          const pct = v.clearance_percent > 0 ? v.clearance_percent : clearancePct;
          return (
            <button
              key={v.id}
              type="button"
              role="option"
              aria-selected={active}
              onClick={() => {
                setSelectedId(v.id);
                setQuantity(1);
              }}
              className={`w-full text-left rounded-lg border px-3 py-2.5 transition-colors ${
                active
                  ? 'border-[#ea580c] bg-white ring-1 ring-[#ea580c]/30'
                  : 'border-amber-100 bg-white/80 hover:border-amber-300'
              }`}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-sm font-medium text-gray-900">{variantLabel(v)}</span>
                {pct > 0 ? (
                  <span className="text-[11px] font-semibold text-red-600 bg-red-50 px-2 py-0.5 rounded-full">
                    -{pct}%
                  </span>
                ) : null}
              </div>
              <div className="mt-1 flex flex-wrap items-baseline gap-2">
                <span className="text-base font-bold text-[#ea580c]">{formatPrice(v.display_price)}</span>
                {v.savings_amount > 0 ? (
                  <span className="text-xs text-gray-500 line-through">{formatPrice(v.original_price)}</span>
                ) : null}
                <span className="text-[11px] text-gray-600">Còn {v.available}</span>
              </div>
            </button>
          );
        })}
      </div>

      <div className="flex items-center gap-3">
        <span className="text-sm text-gray-700">Số lượng</span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={quantity <= 1 || isCartLoading}
            onClick={() => setQuantity((q) => Math.max(1, q - 1))}
            className="w-8 h-8 border border-gray-300 rounded bg-white text-sm disabled:opacity-50"
          >
            −
          </button>
          <span className="w-8 text-center text-sm font-semibold">{quantity}</span>
          <button
            type="button"
            disabled={quantity >= maxQty || isCartLoading}
            onClick={() => setQuantity((q) => Math.min(maxQty, q + 1))}
            className="w-8 h-8 border border-gray-300 rounded bg-white text-sm disabled:opacity-50"
          >
            +
          </button>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row gap-2">
        <button
          type="button"
          disabled={!selected || isCartLoading}
          onClick={handleAdd}
          className="flex-1 rounded-lg bg-gray-600 text-white py-2.5 text-sm font-semibold hover:bg-gray-700 disabled:opacity-50"
        >
          {isCartLoading ? 'Đang thêm…' : 'Thêm giỏ (thanh lý)'}
        </button>
        <button
          type="button"
          disabled={!selected || isCartLoading}
          onClick={handleBuy}
          className="flex-1 rounded-lg bg-[#ea580c] text-white py-2.5 text-sm font-semibold hover:bg-[#c2410c] disabled:opacity-50"
        >
          {isCartLoading ? 'Đang xử lý…' : 'Mua ngay (thanh lý)'}
        </button>
      </div>
    </section>
  );
}
