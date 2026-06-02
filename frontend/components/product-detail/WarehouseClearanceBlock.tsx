'use client';

import { useLayoutEffect, useMemo, useState } from 'react';
import Image from 'next/image';
import type { Product, WarehouseClearanceVariant } from '@/types/api';
import { formatPrice } from '@/lib/utils';
import { getOptimizedImage } from '@/lib/image-utils';
import {
  resolveWarehouseVariantPricing,
  warehouseVariantAriaLabel,
  warehouseVariantAsProduct,
  warehouseVariantColorLabel,
  warehouseVariantSizeLabel,
  warehouseVariantsInStock,
} from '@/lib/warehouse-clearance';

type WarehouseClearanceBlockProps = {
  product: Product;
  onAddToCart: (product: Product, quantity: number, selectedSize?: string, selectedColor?: string) => void;
  onBuyNow: (product: Product, quantity: number, selectedSize?: string, selectedColor?: string) => void;
  isCartLoading?: boolean;
  /** Chọn loại trừ với biến thể order phía trên — null = chưa chọn dòng kho. */
  selectedVariantId?: number | null;
  onSelectVariant?: (id: number | null) => void;
};

function WarehouseVariantMeta({ variant }: { variant: WarehouseClearanceVariant }) {
  const color = warehouseVariantColorLabel(variant);
  const size = warehouseVariantSizeLabel(variant);
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <p className="text-sm leading-snug text-gray-900">
        <span className="font-medium text-gray-500">Màu: </span>
        <span className="font-semibold">{color}</span>
      </p>
      {size ? (
        <p className="text-sm leading-snug text-gray-900">
          <span className="font-medium text-gray-500">Size: </span>
          <span className="font-semibold">{size}</span>
        </p>
      ) : null}
    </div>
  );
}

function variantThumbUrl(v: WarehouseClearanceVariant): string | null {
  const raw = (v.color_image || v.main_image || '').trim();
  return raw || null;
}

export default function WarehouseClearanceBlock({
  product,
  onAddToCart,
  onBuyNow,
  isCartLoading = false,
  selectedVariantId: selectedVariantIdProp,
  onSelectVariant,
}: WarehouseClearanceBlockProps) {
  const variants = useMemo(() => warehouseVariantsInStock(product), [product]);
  const isControlled = onSelectVariant != null;
  const [internalId, setInternalId] = useState<number | null>(null);
  const selectedId = isControlled ? (selectedVariantIdProp ?? null) : internalId;
  const setSelectedId = (id: number | null) => {
    if (isControlled) onSelectVariant?.(id);
    else setInternalId(id);
  };

  const [quantity, setQuantity] = useState(1);
  /** Tránh hydration mismatch: SSR isLoading=true, client soft-nav có thể false. */
  const [uiCartLoading, setUiCartLoading] = useState(false);
  useLayoutEffect(() => {
    setUiCartLoading(isCartLoading);
  }, [isCartLoading]);

  const selected =
    selectedId != null ? variants.find((v) => v.id === selectedId) ?? null : null;
  const fallbackClearancePct = product.warehouse_clearance?.discount_percent ?? 0;
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
          {fallbackClearancePct > 0 ? ` (giảm ${fallbackClearancePct}%)` : ''}. Không cộng sale ngày trùng tháng.
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
          const pricing = resolveWarehouseVariantPricing(v, fallbackClearancePct);
          const thumb = variantThumbUrl(v);
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
              <div className="flex items-start gap-3">
                {thumb ? (
                  <div className="relative h-14 w-14 flex-shrink-0 overflow-hidden rounded-md border border-amber-100 bg-white">
                    <Image
                      src={getOptimizedImage(thumb, { width: 112, height: 112, hideProductPng: true })}
                      alt={warehouseVariantAriaLabel(v)}
                      width={56}
                      height={56}
                      className="h-full w-full object-cover"
                    />
                  </div>
                ) : null}
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <WarehouseVariantMeta variant={v} />
                    {pricing.hasDiscount ? (
                      <span className="text-[11px] font-semibold text-red-600 bg-red-50 px-2 py-0.5 rounded-full">
                        -{pricing.percent}%
                      </span>
                    ) : null}
                  </div>
                  <div className="mt-1 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                    <span className="text-base font-bold text-[#ea580c]">
                      {formatPrice(pricing.displayPrice)}
                    </span>
                    {pricing.hasDiscount ? (
                      <span className="text-xs text-gray-500 line-through">
                        {formatPrice(pricing.originalPrice)}
                      </span>
                    ) : null}
                    {pricing.savingsAmount > 0 ? (
                      <span className="text-[11px] font-semibold text-emerald-700">
                        Tiết kiệm {formatPrice(pricing.savingsAmount)}
                      </span>
                    ) : null}
                    <span className="text-[11px] text-gray-600">Còn {v.available}</span>
                  </div>
                </div>
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
            disabled={!selected || quantity <= 1 || uiCartLoading}
            onClick={() => setQuantity((q) => Math.max(1, q - 1))}
            className="w-8 h-8 border border-gray-300 rounded bg-white text-sm disabled:opacity-50"
          >
            −
          </button>
          <span className="w-8 text-center text-sm font-semibold">{quantity}</span>
          <button
            type="button"
            disabled={!selected || quantity >= maxQty || uiCartLoading}
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
          disabled={!selected || uiCartLoading}
          onClick={handleAdd}
          className="flex-1 rounded-lg bg-gray-600 text-white py-2.5 text-sm font-semibold hover:bg-gray-700 disabled:opacity-50"
        >
          {uiCartLoading ? 'Đang thêm…' : 'Thêm giỏ (thanh lý)'}
        </button>
        <button
          type="button"
          disabled={!selected || uiCartLoading}
          onClick={handleBuy}
          className="flex-1 rounded-lg bg-[#ea580c] text-white py-2.5 text-sm font-semibold hover:bg-[#c2410c] disabled:opacity-50"
        >
          {uiCartLoading ? 'Đang xử lý…' : 'Mua ngay (thanh lý)'}
        </button>
      </div>
    </section>
  );
}
