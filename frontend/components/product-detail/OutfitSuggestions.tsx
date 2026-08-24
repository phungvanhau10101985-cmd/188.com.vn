'use client';

import { useEffect, useMemo, useState } from 'react';
import Image from 'next/image';
import ProductPdpLink from '@/components/ProductPdpLink';
import LoadingLink from '@/components/ui/LoadingLink';
import type { PdpOutfitResponse, PdpOutfitSlot, Product } from '@/types/api';
import { trackEvent } from '@/lib/analytics';
import { formatPrice, getProductMainImage } from '@/lib/utils';
import { productPdpHref } from '@/lib/product-path-slug';
import { searchParamsToEncodedQueryString } from '@/lib/product-related-tabs';
import { cdnUrl } from '@/lib/cdn-url';
import { applyBirthdayDiscount } from '@/lib/birthday-discount';
import { useBirthdayDiscount } from '@/lib/use-birthday-discount';
import { BirthdayPromoImageBadge, BirthdayPromoPriceCakeIcon } from '@/components/BirthdayPromoProductMarkers';
import ProductCardClearanceMeta from '@/components/ProductCardClearanceMeta';
import {
  loadPdpOutfitSuggestions,
  prefetchPdpOutfitSuggestions,
  shouldTrackOutfitBlockView,
} from '@/lib/pdp-request-dedupe';

const FETCH_LIMIT = 12;

export type PdpStripLayout = 'mobile' | 'desktop';

function stripInitialVisible(len: number, layout: PdpStripLayout): number {
  return Math.min(layout === 'desktop' ? 5 : 2, len);
}

function stripStep(layout: PdpStripLayout): number {
  return layout === 'desktop' ? 5 : 2;
}

function listingHref(params?: Record<string, string>): string | null {
  if (!params) return null;
  const p = new URLSearchParams();
  const category = (params.category || '').trim();
  const style = (params.style || '').trim();
  const q = (params.q || '').trim();
  if (category) p.set('category', category);
  if (style) p.set('style', style);
  if (q) p.set('q', q);
  if (![...p.keys()].length) return null;
  return `/?${searchParamsToEncodedQueryString(p)}`;
}

function OutfitCard({
  product,
  reason,
  slotId,
  anchorId,
  imageSizes,
}: {
  product: Product;
  reason?: string;
  slotId: string;
  anchorId: number;
  imageSizes: string;
}) {
  const href = productPdpHref(product.slug, product.product_id) ?? `/products/${product.id}`;
  const birthdayDiscount = useBirthdayDiscount();
  const displayPrice = birthdayDiscount.active
    ? applyBirthdayDiscount(product.price || 0, birthdayDiscount.percent)
    : product.price || 0;

  return (
    <ProductPdpLink
      href={href}
      className="group block bg-white rounded-lg border border-gray-200 overflow-hidden hover:shadow-md transition-all"
      onClick={() =>
        trackEvent('outfit_item_click', {
          anchor_id: anchorId,
          slot: slotId,
          product_id: product.id,
        })
      }
    >
      <div className="aspect-square bg-gray-100 overflow-hidden relative">
        <Image
          src={getProductMainImage(product)}
          alt={product.name}
          fill
          sizes={imageSizes}
          loading="lazy"
          className="object-cover group-hover:scale-110 transition-transform duration-300"
          onError={(e) => {
            (e.currentTarget as HTMLImageElement).src = cdnUrl('/images/placeholder.jpg');
          }}
        />
        <BirthdayPromoImageBadge active={birthdayDiscount.active} percent={birthdayDiscount.percent} />
      </div>
      <div className="p-2">
        <h4 className="font-medium text-gray-900 line-clamp-2 text-xs leading-tight mb-1 group-hover:text-[#ea580c] transition-colors">
          {product.name}
        </h4>
        {reason ? (
          <p className="mb-1 inline-block max-w-full truncate rounded bg-orange-50 px-1.5 py-0.5 text-[10px] font-medium text-orange-700">
            {reason}
          </p>
        ) : null}
        <div className="flex flex-wrap items-baseline gap-x-1 gap-y-0">
          <span className="text-sm font-bold text-[#ea580c]">{formatPrice(displayPrice)}</span>
          <BirthdayPromoPriceCakeIcon active={birthdayDiscount.active} percent={birthdayDiscount.percent} />
          {birthdayDiscount.active && displayPrice < (product.price || 0) ? (
            <span className="text-xs text-gray-500 line-through decoration-1 decoration-gray-400">
              {formatPrice(product.price)}
            </span>
          ) : product.original_price && product.original_price > product.price ? (
            <span className="text-xs text-gray-500 line-through decoration-1 decoration-gray-400">
              {formatPrice(product.original_price)}
            </span>
          ) : null}
        </div>
        <ProductCardClearanceMeta product={product} compact className="mt-1" />
      </div>
    </ProductPdpLink>
  );
}

type OutfitSuggestionsProps = {
  product: Product;
  className?: string;
  /** Khớp khung PDP: mobile luôn 2 ô / desktop luôn 5 ô — không đoán theo window. */
  layout?: PdpStripLayout;
};

export default function OutfitSuggestions({
  product,
  className = '',
  layout = 'mobile',
}: OutfitSuggestionsProps) {
  const gridClass = layout === 'desktop' ? 'grid grid-cols-5 gap-4' : 'grid grid-cols-2 gap-4';
  const imageSizes = layout === 'desktop' ? '20vw' : '50vw';
  const actionsRowClass =
    layout === 'desktop'
      ? 'mt-4 flex w-full items-center justify-center gap-4'
      : 'mt-4 flex w-full items-center justify-between gap-4';
  const [data, setData] = useState<PdpOutfitResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [activeSlot, setActiveSlot] = useState<string | null>(null);
  const [visibleCount, setVisibleCount] = useState(() => (layout === 'desktop' ? 5 : 2));

  useEffect(() => {
    if (!product?.id) return;
    let cancelled = false;
    setLoading(true);
    setError(false);
    loadPdpOutfitSuggestions(product.id, FETCH_LIMIT, reloadKey > 0)
      .then((res) => {
        if (cancelled) return;
        setData(res);
        const first = res.applicable ? res.slots[0]?.id ?? null : null;
        setActiveSlot(first);
        if (
          res.applicable &&
          res.slots.length &&
          shouldTrackOutfitBlockView(product.id, first)
        ) {
          trackEvent('outfit_block_view', {
            anchor_id: product.id,
            slot: first,
            slot_count: res.slots.length,
          });
        }
      })
      .catch(() => {
        if (!cancelled) {
          setData({ applicable: false, reason: 'error', slots: [] });
          setError(true);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [product.id, reloadKey]);

  const slots = data?.applicable ? data.slots ?? [] : [];
  const current: PdpOutfitSlot | undefined = useMemo(
    () => slots.find((s) => s.id === activeSlot) ?? slots[0],
    [slots, activeSlot]
  );

  useEffect(() => {
    if (!current) return;
    setVisibleCount(stripInitialVisible(current.items.length, layout));
  }, [current?.id, current?.items.length, layout]);

  if (!loading && !error && (!data?.applicable || slots.length === 0)) {
    return null;
  }

  const moreHref = listingHref(current?.listing_params);
  const visibleItems = current?.items.slice(0, visibleCount) ?? [];
  const canLoadMore = !!current && visibleCount < current.items.length;
  const canShowAll = !!moreHref || canLoadMore;

  return (
    <section className={`border-t border-gray-200 pt-5 ${className}`} aria-labelledby="outfit-suggestions-heading">
      <h3 id="outfit-suggestions-heading" className="text-base font-bold text-gray-900 mb-0.5">
        {data?.anchor?.title || 'Phối với món này'}
      </h3>
      <p className="text-xs text-gray-500 mb-3">Món khác loại để mặc cùng</p>

      {error ? (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
          Không tải được gợi ý phối.{' '}
          <button
            type="button"
            onClick={() => setReloadKey((k) => k + 1)}
            className="underline font-medium"
          >
            Thử lại
          </button>
        </div>
      ) : null}

      {loading ? (
        <>
          <div className={gridClass}>
            {[...Array(layout === 'desktop' ? 5 : 2)].map((_, i) => (
              <div key={i} className="animate-pulse">
                <div className="aspect-square bg-gray-200 rounded-lg mb-2" />
                <div className="h-4 bg-gray-200 rounded mb-1" />
                <div className="h-4 bg-gray-200 rounded w-3/4" />
              </div>
            ))}
          </div>
          <div className={actionsRowClass}>
            <div className="h-9 w-24 rounded bg-gray-100 animate-pulse" />
            <div className="h-9 w-28 rounded bg-gray-200 animate-pulse" />
          </div>
        </>
      ) : null}

      {!loading && !error && current ? (
        <>
          <div className="mb-3 flex flex-wrap gap-1.5" role="tablist" aria-label="Nhóm phối">
            {slots.map((slot) => {
              const selected = slot.id === current.id;
              return (
                <button
                  key={slot.id}
                  type="button"
                  role="tab"
                  aria-selected={selected}
                  className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                    selected
                      ? 'bg-[#ea580c] text-white'
                      : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  }`}
                  onClick={() => {
                    setActiveSlot(slot.id);
                    trackEvent('outfit_slot_change', {
                      anchor_id: product.id,
                      slot: slot.id,
                    });
                  }}
                >
                  {slot.label}
                </button>
              );
            })}
          </div>
          <div className={gridClass}>
            {visibleItems.map((item) => (
              <OutfitCard
                key={item.product.id}
                product={item.product}
                reason={item.reasons?.[0]}
                slotId={current.id}
                anchorId={product.id}
                imageSizes={imageSizes}
              />
            ))}
          </div>
          {canShowAll ? (
            <div className={actionsRowClass}>
              {canLoadMore ? (
                <button
                  type="button"
                  onClick={() =>
                    setVisibleCount((prev) =>
                      Math.min(prev + stripStep(layout), current.items.length),
                    )
                  }
                  className="inline-flex shrink-0 items-center justify-center gap-2 text-sm text-gray-700 hover:text-[#ea580c]"
                >
                  <span className="inline-flex items-center justify-center w-7 h-7 rounded-full border border-gray-300">
                    ↻
                  </span>
                  Xem thêm
                </button>
              ) : layout === 'mobile' ? (
                <span />
              ) : null}
              {moreHref ? (
                <LoadingLink
                  href={moreHref}
                  className="inline-flex shrink-0 items-center justify-center px-4 py-2 bg-[#ea580c] text-white rounded-lg text-sm font-medium hover:bg-orange-600"
                >
                  Xem tất cả
                </LoadingLink>
              ) : canLoadMore ? (
                <button
                  type="button"
                  onClick={() => setVisibleCount(current.items.length)}
                  className="inline-flex shrink-0 items-center justify-center px-4 py-2 bg-[#ea580c] text-white rounded-lg text-sm font-medium hover:bg-orange-600"
                >
                  Xem tất cả
                </button>
              ) : null}
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}

export function prefetchOutfitSuggestionsForPdp(productId: number): void {
  prefetchPdpOutfitSuggestions(productId, FETCH_LIMIT);
}
