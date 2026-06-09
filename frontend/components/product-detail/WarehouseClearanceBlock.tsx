'use client';

import { useLayoutEffect, useMemo, useState } from 'react';
import Image from 'next/image';
import type { Product, WarehouseClearanceVariant } from '@/types/api';
import { formatPrice } from '@/lib/utils';
import { getOptimizedImage } from '@/lib/image-utils';
import {
  clearanceLineDiscountPercent,
  getClearanceCardBestDiscountPercent,
  resolveWarehouseVariantPricing,
  warehouseVariantAriaLabel,
  warehouseVariantAsProduct,
  warehouseVariantColorLabel,
  warehouseVariantSizeLabel,
  warehouseVariantsInStock,
} from '@/lib/warehouse-clearance';
import Button from '@/components/ui/Button';

type WarehouseClearanceBlockProps = {
  product: Product;
  onAddToCart: (product: Product, quantity: number, selectedSize?: string, selectedColor?: string) => void;
  onBuyNow: (product: Product, quantity: number, selectedSize?: string, selectedColor?: string) => void;
  isCartLoading?: boolean;
  /** Chọn loại trừ với biến thể order phía trên — null = chưa chọn dòng kho. */
  selectedVariantId?: number | null;
  onSelectVariant?: (id: number | null) => void;
};

function variantDisplayPercent(
  pricing: ReturnType<typeof resolveWarehouseVariantPricing>,
  fallbackPct: number,
): number {
  if (pricing.hasDiscount && pricing.originalPrice > pricing.displayPrice) {
    return clearanceLineDiscountPercent(
      pricing.displayPrice,
      pricing.originalPrice,
      pricing.percent,
    );
  }
  return Math.max(0, pricing.percent || fallbackPct);
}

function WarehouseVariantMeta({ variant }: { variant: WarehouseClearanceVariant }) {
  const color = warehouseVariantColorLabel(variant);
  const size = warehouseVariantSizeLabel(variant);
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <p className="text-sm leading-snug text-gray-900 sm:text-base">
        <span className="font-medium text-gray-500">Màu: </span>
        <span className="font-semibold">{color}</span>
      </p>
      {size ? (
        <p className="text-sm leading-snug text-gray-900 sm:text-base">
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
  const [uiCartLoading, setUiCartLoading] = useState(false);
  useLayoutEffect(() => {
    setUiCartLoading(isCartLoading);
  }, [isCartLoading]);

  const fallbackClearancePct = product.warehouse_clearance?.discount_percent ?? 0;
  const bestDiscountPct = useMemo(
    () => getClearanceCardBestDiscountPercent(product),
    [product],
  );
  const headerPct = bestDiscountPct > 0 ? bestDiscountPct : fallbackClearancePct;

  const selected =
    selectedId != null ? variants.find((v) => v.id === selectedId) ?? null : null;
  const selectedPricing = selected
    ? resolveWarehouseVariantPricing(selected, fallbackClearancePct)
    : null;
  const selectedPct =
    selectedPricing != null
      ? variantDisplayPercent(selectedPricing, fallbackClearancePct)
      : 0;
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
      className="rounded-2xl border-2 border-orange-300 bg-gradient-to-br from-orange-50 via-amber-50 to-orange-100/90 p-4 shadow-md ring-1 ring-orange-200/70 sm:p-5"
      aria-label="Hàng thanh lý trong kho"
    >
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-orange-200/80 pb-3">
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-base font-extrabold tracking-tight text-orange-950 sm:text-lg">
              Thanh lý trong kho
            </p>
            {headerPct > 0 ? (
              <span className="inline-flex min-w-[3.25rem] items-center justify-center rounded-lg bg-red-600 px-2.5 py-1 text-sm font-extrabold text-white shadow-sm ring-2 ring-red-400/30">
                -{headerPct}%
              </span>
            ) : null}
          </div>
          <p className="text-xs font-medium text-orange-900/90 sm:text-sm">
            Hàng duyệt hoàn — giá riêng, không cộng sale ngày trùng tháng.
            {variants.length > 1 ? (
              <span className="ml-1 font-semibold text-orange-950">
                ({variants.length} dòng còn hàng)
              </span>
            ) : null}
          </p>
          {product.source_oos ? (
            <p className="text-xs font-semibold text-amber-900 sm:text-sm">
              Nguồn order tạm hết — vẫn mua được hàng thanh lý bên dưới.
            </p>
          ) : null}
        </div>
      </div>

      <div className="space-y-3 pt-3" role="listbox" aria-label="Chọn màu size kho thanh lý">
        {variants.map((v) => {
          const active = selected?.id === v.id;
          const pricing = resolveWarehouseVariantPricing(v, fallbackClearancePct);
          const pct = variantDisplayPercent(pricing, fallbackClearancePct);
          const thumb = variantThumbUrl(v);
          const lowStock = v.available <= 3;
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
              className={`w-full text-left rounded-xl border-2 px-3 py-3 transition-all sm:px-4 sm:py-3.5 ${
                active
                  ? 'border-[#ea580c] bg-white shadow-md ring-2 ring-[#ea580c]/25'
                  : 'border-orange-200/90 bg-white/90 hover:border-orange-400 hover:shadow-sm'
              }`}
            >
              <div className="flex items-start gap-3 sm:gap-4">
                {thumb ? (
                  <div className="relative h-20 w-20 flex-shrink-0 overflow-hidden rounded-lg border-2 border-orange-100 bg-white shadow-sm sm:h-24 sm:w-24">
                    <Image
                      src={getOptimizedImage(thumb, { width: 160, height: 160, hideProductPng: true })}
                      alt={warehouseVariantAriaLabel(v)}
                      width={96}
                      height={96}
                      className="h-full w-full object-cover"
                    />
                    {pct > 0 ? (
                      <span className="absolute left-1 top-1 rounded-md bg-red-600 px-1.5 py-0.5 text-[10px] font-extrabold text-white shadow sm:text-xs">
                        -{pct}%
                      </span>
                    ) : null}
                  </div>
                ) : pct > 0 ? (
                  <span className="flex-shrink-0 rounded-lg bg-red-600 px-2.5 py-2 text-sm font-extrabold text-white shadow-sm">
                    -{pct}%
                  </span>
                ) : null}
                <div className="min-w-0 flex-1">
                  <WarehouseVariantMeta variant={v} />
                  <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
                    {pricing.hasDiscount && pct > 0 && !thumb ? (
                      <span className="rounded-lg bg-red-600 px-2.5 py-1.5 text-base font-extrabold text-white shadow-sm">
                        -{pct}%
                      </span>
                    ) : null}
                    <span className="text-xl font-extrabold text-[#ea580c] sm:text-2xl">
                      {formatPrice(pricing.displayPrice)}
                    </span>
                    {pricing.hasDiscount ? (
                      <span className="text-sm text-gray-500 line-through decoration-2 sm:text-base">
                        {formatPrice(pricing.originalPrice)}
                      </span>
                    ) : null}
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5">
                    {pricing.savingsAmount > 0 ? (
                      <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-bold text-emerald-800 ring-1 ring-emerald-200 sm:text-sm">
                        Tiết kiệm {formatPrice(pricing.savingsAmount)}
                      </span>
                    ) : null}
                    <span
                      className={`text-xs font-semibold sm:text-sm ${
                        lowStock ? 'text-red-700' : 'text-gray-600'
                      }`}
                    >
                      {lowStock ? `Chỉ còn ${v.available}` : `Còn ${v.available}`}
                    </span>
                  </div>
                </div>
              </div>
            </button>
          );
        })}
      </div>

      {selected && selectedPricing ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-orange-200 bg-white/95 px-3 py-2.5 sm:px-4">
          <p className="text-xs font-medium text-gray-600 sm:text-sm">Tổng thanh lý đã chọn</p>
          <div className="flex flex-wrap items-center gap-2">
            {selectedPct > 0 ? (
              <span className="rounded-lg bg-red-600 px-2 py-1 text-sm font-extrabold text-white">
                -{selectedPct}%
              </span>
            ) : null}
            <span className="text-lg font-extrabold text-[#ea580c] sm:text-xl">
              {formatPrice(selectedPricing.displayPrice * quantity)}
            </span>
            {selectedPricing.savingsAmount > 0 ? (
              <span className="text-xs font-semibold text-emerald-700 sm:text-sm">
                Tiết kiệm {formatPrice(selectedPricing.savingsAmount * quantity)}
              </span>
            ) : null}
          </div>
        </div>
      ) : (
        <p className="text-center text-xs font-medium text-orange-900/80 sm:text-sm">
          Chọn một dòng thanh lý ở trên để mua
        </p>
      )}

      <div className="flex items-center gap-3">
        <span className="text-sm font-semibold text-gray-800">Số lượng</span>
        <div className="flex items-center gap-2 rounded-lg border border-orange-200 bg-white p-0.5">
          <button
            type="button"
            disabled={!selected || quantity <= 1 || uiCartLoading}
            onClick={() => setQuantity((q) => Math.max(1, q - 1))}
            className="flex h-9 w-9 items-center justify-center rounded-md text-base font-semibold hover:bg-orange-50 disabled:opacity-50"
            aria-label="Giảm số lượng"
          >
            −
          </button>
          <span className="min-w-[2rem] text-center text-base font-bold tabular-nums">{quantity}</span>
          <button
            type="button"
            disabled={!selected || quantity >= maxQty || uiCartLoading}
            onClick={() => setQuantity((q) => Math.min(maxQty, q + 1))}
            className="flex h-9 w-9 items-center justify-center rounded-md text-base font-semibold hover:bg-orange-50 disabled:opacity-50"
            aria-label="Tăng số lượng"
          >
            +
          </button>
        </div>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row">
        <Button
          type="button"
          variant="secondary"
          disabled={!selected || uiCartLoading}
          loading={uiCartLoading}
          onClick={handleAdd}
          className="flex-1 rounded-xl border-2 border-gray-600 bg-gray-700 py-3 text-sm font-bold text-white shadow-sm hover:bg-gray-800 sm:text-base"
        >
          Thêm giỏ (thanh lý)
        </Button>
        <Button
          type="button"
          variant="primary"
          disabled={!selected || uiCartLoading}
          loading={uiCartLoading}
          onClick={handleBuy}
          className="flex-1 rounded-xl bg-gradient-to-r from-[#ea580c] to-orange-600 py-3 text-sm font-bold text-white shadow-md hover:from-[#c2410c] hover:to-orange-700 sm:text-base border-transparent"
        >
          Mua ngay (thanh lý)
        </Button>
      </div>
    </section>
  );
}
