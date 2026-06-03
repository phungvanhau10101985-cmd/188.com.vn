'use client';

import { useMemo } from 'react';
import Image from 'next/image';
import type { Product } from '@/types/api';
import { formatPrice } from '@/lib/utils';
import { getOptimizedImage } from '@/lib/image-utils';
import {
  clearanceVariantCountOnCard,
  getClearanceCardDisplayLines,
  productShowsClearanceOnCard,
  resolveClearanceCardHeroPercent,
} from '@/lib/warehouse-clearance';

type ProductCardClearanceMetaProps = {
  product: Product;
  /** Thẻ nhỏ (lưới trang chủ) — chữ nhỏ hơn. */
  compact?: boolean;
  className?: string;
};

/** Khối «Thanh lý xả kho» + thumb màu + Màu/Size + giá sale trên thẻ SP. */
export default function ProductCardClearanceMeta({
  product,
  compact = false,
  className = '',
}: ProductCardClearanceMetaProps) {
  const lines = useMemo(() => getClearanceCardDisplayLines(product, 2), [product]);
  const totalVariants = useMemo(() => clearanceVariantCountOnCard(product), [product]);
  const bestDiscountPct = useMemo(() => resolveClearanceCardHeroPercent(product), [product]);
  const extraCount = Math.max(0, totalVariants - lines.length);

  if (!productShowsClearanceOnCard(product)) return null;

  const headerClass = compact ? 'text-[11px]' : 'text-xs';
  const pctBadgeClass = compact ? 'text-sm px-1.5 py-0.5' : 'text-base px-2 py-0.5';
  const metaClass = compact ? 'text-[11px]' : 'text-xs';
  const priceClass = compact ? 'text-sm' : 'text-base';
  const strikeClass = compact ? 'text-[10px]' : 'text-xs';
  const thumbSize = compact ? 'h-11 w-11' : 'h-12 w-12';

  return (
    <div
      className={`rounded-md border-2 border-amber-300/90 bg-gradient-to-b from-amber-50 to-orange-50/90 px-2.5 py-2 space-y-1.5 shadow-sm ${className}`}
      aria-label="Hàng thanh lý xả kho"
    >
      <div className="flex flex-wrap items-center justify-between gap-1.5">
        <p className={`${headerClass} font-bold uppercase tracking-wide text-amber-950`}>
          Sale thanh lý xả kho
        </p>
        {bestDiscountPct > 0 ? (
          <span
            className={`${pctBadgeClass} shrink-0 rounded-md bg-red-600 font-black tabular-nums text-white shadow-sm`}
          >
            -{bestDiscountPct}%
          </span>
        ) : null}
      </div>
      {lines.map((line, idx) => {
        const thumbSrc = line.thumbUrl
          ? getOptimizedImage(line.thumbUrl, { width: 96, height: 96, quality: 80, fallbackStrategy: 'local' })
          : null;
        return (
          <div
            key={`${line.color}-${line.size ?? ''}-${idx}`}
            className="flex items-start gap-2"
          >
            {thumbSrc ? (
              <div
                className={`relative ${thumbSize} shrink-0 overflow-hidden rounded-md border border-amber-200/80 bg-white`}
              >
                <Image
                  src={thumbSrc}
                  alt={line.color !== '—' ? `Màu ${line.color}` : 'Ảnh màu thanh lý'}
                  fill
                  sizes="48px"
                  className="object-cover"
                />
              </div>
            ) : null}
            <div className={`min-w-0 flex-1 ${metaClass} space-y-1`}>
              <p className="leading-snug text-gray-800">
                <span className="font-medium text-gray-500">Màu: </span>
                <span className="font-semibold text-gray-900">{line.color}</span>
                {line.size ? (
                  <>
                    <span className="mx-1 text-amber-700/60" aria-hidden>
                      ·
                    </span>
                    <span className="inline-flex items-center rounded bg-amber-900/90 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white sm:text-[11px]">
                      {line.size}
                    </span>
                  </>
                ) : null}
              </p>
              <p className="flex flex-wrap items-baseline gap-x-1.5 gap-y-0 leading-snug">
                <span className="font-medium text-gray-500">Giá sale: </span>
                <span className={`font-bold tabular-nums text-[#ea580c] ${priceClass}`}>
                  {formatPrice(line.displayPrice)}
                </span>
                {line.hasDiscount && line.originalPrice != null && line.originalPrice > line.displayPrice ? (
                  <span className={`text-gray-500 line-through decoration-gray-400 ${strikeClass}`}>
                    {formatPrice(line.originalPrice)}
                  </span>
                ) : null}
              </p>
            </div>
          </div>
        );
      })}
      {extraCount > 0 ? (
        <p className={`${metaClass} font-medium text-amber-800`}>+{extraCount} biến thể khác</p>
      ) : null}
    </div>
  );
}
