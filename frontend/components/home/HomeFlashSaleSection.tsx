'use client';

import { useEffect } from 'react';
import { SimpleProductCard } from '@/components/ProductCard';
import HomeSectionErrorBoundary from '@/components/home/HomeSectionErrorBoundary';
import { formatCountdownParts } from '@/lib/site-sale';
import { useFlashSale } from '@/lib/use-flash-sale';
import { useClientMounted } from '@/lib/use-client-mounted';
import { useCountdownNowMs } from '@/lib/use-countdown-now-ms';
import type { Product } from '@/types/api';

type Props = {
  onFavorite: (productId: number, e: React.MouseEvent) => void | Promise<void>;
  favoriteIds: Set<number>;
  onProductsChange?: (products: Product[]) => void;
};

function formatHeaderCountdown(parts: {
  hours: number;
  minutes: number;
  seconds: number;
  days: number;
}): string {
  const h = parts.days * 24 + parts.hours;
  const mm = String(parts.minutes).padStart(2, '0');
  const ss = String(parts.seconds).padStart(2, '0');
  if (h <= 0) return `${mm}:${ss}`;
  return `${String(h).padStart(2, '0')}:${mm}:${ss}`;
}

export default function HomeFlashSaleSection({
  onFavorite,
  favoriteIds,
  onProductsChange,
}: Props) {
  const { products, countdownTo, loading, error, reload } = useFlashSale();
  const clientMounted = useClientMounted();
  const nowMs = useCountdownNowMs(Boolean(countdownTo));

  useEffect(() => {
    onProductsChange?.(products);
  }, [products, onProductsChange]);

  const countdown = clientMounted
    ? formatCountdownParts(countdownTo, nowMs)
    : null;
  const countdownLive =
    countdown && !countdown.expired ? formatHeaderCountdown(countdown) : null;

  if (!loading && !error && products.length === 0) {
    return null;
  }

  return (
    <HomeSectionErrorBoundary>
      <section className="mb-8" aria-labelledby="home-flash-sale-heading">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2
              id="home-flash-sale-heading"
              className="text-base font-bold text-gray-900 border-b-2 border-[#ea580c] pb-1 w-fit"
            >
              FLASH SALE
            </h2>
            <p className="mt-1 text-xs text-gray-600">
              Deal 10 phút theo shop vừa xem. Hết lượt mất giảm — chốt giỏ ngay.
            </p>
          </div>
          {countdownLive ? (
            <p
              className="rounded-full bg-red-600 px-3 py-1 text-xs font-semibold text-white tabular-nums"
              role="timer"
              aria-live="polite"
            >
              Kết thúc lượt sau {countdownLive}
            </p>
          ) : null}
        </div>

        {error ? (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
            {error}{' '}
            <button type="button" onClick={() => void reload()} className="underline font-medium">
              Thử lại
            </button>
          </div>
        ) : loading ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-6 gap-4">
            {[...Array(8)].map((_, i) => (
              <div
                key={i}
                className="bg-white rounded-xl border border-gray-100 overflow-hidden animate-pulse"
                aria-hidden
              >
                <div className="aspect-square bg-gray-100" />
                <div className="p-3 space-y-2">
                  <div className="h-3 bg-gray-100 rounded w-3/4" />
                  <div className="h-4 bg-gray-100 rounded w-2/5" />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-6 gap-4">
            {products.map((product, index) => (
              <SimpleProductCard
                key={product.id}
                product={product}
                onFavorite={onFavorite}
                isFavorited={favoriteIds.has(product.id)}
                priority={index < 2}
              />
            ))}
          </div>
        )}
      </section>
    </HomeSectionErrorBoundary>
  );
}
