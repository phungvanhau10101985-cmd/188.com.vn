'use client';

import { useEffect, useMemo, useState } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import ProductPdpLink from '@/components/ProductPdpLink';
import type { PdpOutfitResponse, PdpOutfitSlot, Product } from '@/types/api';
import { apiClient } from '@/lib/api-client';
import { trackEvent } from '@/lib/analytics';
import { formatPrice, getProductMainImage } from '@/lib/utils';
import { productPdpHref } from '@/lib/product-path-slug';
import { searchParamsToEncodedQueryString } from '@/lib/product-related-tabs';
import { cdnUrl } from '@/lib/cdn-url';
import { applyBirthdayDiscount } from '@/lib/birthday-discount';
import { useBirthdayDiscount } from '@/lib/use-birthday-discount';
import { BirthdayPromoImageBadge, BirthdayPromoPriceCakeIcon } from '@/components/BirthdayPromoProductMarkers';
import ProductCardClearanceMeta from '@/components/ProductCardClearanceMeta';

const GRID_CLASS = 'grid grid-cols-2 lg:grid-cols-5 gap-4';
const IMAGE_SIZES = '(max-width: 1023px) 50vw, (min-width: 1024px) 20vw';

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
}: {
  product: Product;
  reason?: string;
  slotId: string;
  anchorId: number;
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
          sizes={IMAGE_SIZES}
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
};

export default function OutfitSuggestions({ product, className = '' }: OutfitSuggestionsProps) {
  const [data, setData] = useState<PdpOutfitResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [activeSlot, setActiveSlot] = useState<string | null>(null);

  useEffect(() => {
    if (!product?.id) return;
    let cancelled = false;
    setLoading(true);
    setError(false);
    apiClient
      .getPdpOutfitSuggestions(product.id, { limit: 6 })
      .then((res) => {
        if (cancelled) return;
        setData(res);
        const first = res.applicable ? res.slots[0]?.id ?? null : null;
        setActiveSlot(first);
        if (res.applicable && res.slots.length) {
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

  if (!loading && !error && (!data?.applicable || slots.length === 0)) {
    return null;
  }

  const moreHref = listingHref(current?.listing_params);

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
        <div className={GRID_CLASS}>
          {[...Array(4)].map((_, i) => (
            <div key={i} className="animate-pulse">
              <div className="aspect-square bg-gray-200 rounded-lg mb-2" />
              <div className="h-4 bg-gray-200 rounded mb-1" />
              <div className="h-4 bg-gray-200 rounded w-3/4" />
            </div>
          ))}
        </div>
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
          <div className={GRID_CLASS}>
            {current.items.slice(0, 6).map((item) => (
              <OutfitCard
                key={item.product.id}
                product={item.product}
                reason={item.reasons?.[0]}
                slotId={current.id}
                anchorId={product.id}
              />
            ))}
          </div>
          {moreHref ? (
            <div className="mt-3">
              <Link href={moreHref} className="text-xs font-medium text-[#ea580c] hover:underline">
                Xem thêm {current.label.toLowerCase()}
              </Link>
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}

export function prefetchOutfitSuggestionsForPdp(productId: number): void {
  if (!productId) return;
  void apiClient.getPdpOutfitSuggestions(productId, { limit: 6 });
}
