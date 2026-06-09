'use client';

import { useState, useEffect, useCallback } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { apiClient } from '@/lib/api-client';
import { getOptimizedImage } from '@/lib/image-utils';
import { useFavorites } from '@/features/favorites/hooks/useFavorites';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { useToast } from '@/components/ToastProvider';
import Button from '@/components/ui/Button';
import LoadingLink from '@/components/ui/LoadingLink';
import { trackEvent } from '@/lib/analytics';
import { productPathSlugFromApi } from '@/lib/product-path-slug';
import ProductCardClearanceMeta from '@/components/ProductCardClearanceMeta';
import { snapshotProductDataAsProduct } from '@/lib/viewed-product-card';
import { buildHomeListingHrefByChineseShop } from '@/lib/product-related-tabs';
import { displayableBrandOrOrigin } from '@/lib/utils';

interface FavoriteItem {
  id: number;
  product_id: number;
  product_data?: {
    id?: number;
    product_id?: string;
    name?: string;
    price?: number;
    main_image?: string;
    brand_name?: string;
    slug?: string;
    shop_name_chinese?: string;
  };
}

function formatVnd(n: number) {
  return new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(n);
}

function FavoriteCardSkeleton() {
  return (
    <div className="overflow-hidden rounded-xl bg-white ring-1 ring-gray-100" aria-hidden>
      <div className="aspect-[3/4] animate-pulse bg-gray-200" />
      <div className="space-y-2 p-2.5">
        <div className="h-3.5 animate-pulse rounded bg-gray-200" />
        <div className="h-3 w-2/3 animate-pulse rounded bg-gray-200" />
        <div className="h-4 w-1/3 animate-pulse rounded bg-gray-200" />
      </div>
    </div>
  );
}

type FavoriteCardProps = {
  item: FavoriteItem;
  removing: boolean;
  priorityImage?: boolean;
  onRemove: (productId: number, favoriteId: number) => void;
};

function FavoriteProductCard({ item, removing, priorityImage, onRemove }: FavoriteCardProps) {
  const [imageError, setImageError] = useState(false);
  const data = item.product_data || {};
  const name = data.name || `Sản phẩm #${item.product_id}`;
  const price = data.price ?? 0;
  const pathSeg = productPathSlugFromApi(data.slug, String(item.product_id));
  const href = `/products/${pathSeg}`;
  const imageUrl = getOptimizedImage(data.main_image, {
    width: 480,
    height: 640,
    quality: 85,
    fallbackStrategy: 'local',
  });
  const brand = displayableBrandOrOrigin(data.brand_name);
  const similarShopHref = buildHomeListingHrefByChineseShop(data.shop_name_chinese || '');

  return (
    <article className="group flex flex-col overflow-hidden rounded-xl bg-white ring-1 ring-gray-100 transition-shadow hover:shadow-md hover:ring-orange-100">
      <div className="relative aspect-[3/4] overflow-hidden bg-gray-50">
        <Link href={href} className="absolute inset-0 z-0 block" aria-label={`Xem ${name}`}>
          {!imageError ? (
            <Image
              src={imageUrl}
              alt={name}
              fill
              priority={priorityImage}
              sizes="(max-width: 767px) 46vw, (min-width: 1280px) 22vw, (min-width: 1024px) 28vw, 33vw"
              className="object-cover transition-transform duration-300 group-hover:scale-[1.03]"
              onError={() => setImageError(true)}
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center bg-gray-100 text-xs text-gray-400">
              Không có ảnh
            </div>
          )}
        </Link>

        <button
          type="button"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onRemove(item.product_id, item.id);
          }}
          disabled={removing}
          className="absolute right-2 top-2 z-10 flex h-9 w-9 items-center justify-center rounded-full bg-white/95 text-red-500 shadow-sm ring-1 ring-black/5 transition hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
          aria-label="Bỏ yêu thích sản phẩm"
        >
          {removing ? (
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-red-300 border-t-red-600" />
          ) : (
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
              <path d="M4.318 6.318a4.5 4.5 0 016.364 0L12 7.636l1.318-1.318a4.5 4.5 0 116.364 6.364L12 20.364l-7.682-7.682a4.5 4.5 0 010-6.364z" />
            </svg>
          )}
        </button>
      </div>

      <div className="flex flex-col gap-1 p-2.5 sm:p-3">
        <Link href={href} className="min-h-0">
          <h2 className="line-clamp-2 text-xs font-medium leading-snug text-gray-900 transition-colors group-hover:text-[#ea580c] sm:text-sm">
            {name}
          </h2>
        </Link>

        {brand ? (
          <p className="line-clamp-1 text-[11px] text-gray-500 sm:text-xs">{brand}</p>
        ) : null}

        <p className="text-sm font-bold tabular-nums text-[#ea580c] sm:text-base">{formatVnd(price)}</p>

        <ProductCardClearanceMeta
          product={snapshotProductDataAsProduct(item.product_id, data as Record<string, unknown>)}
          compact
          className="mt-1"
        />

        <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1">
          <Link
            href={href}
            className="text-xs font-semibold text-gray-800 underline decoration-gray-300 underline-offset-2 hover:text-[#ea580c] hover:decoration-[#ea580c]/40"
          >
            Xem chi tiết
          </Link>
          {similarShopHref ? (
            <Link
              href={similarShopHref}
              className="text-xs font-medium text-[#ea580c] hover:text-[#c2410c]"
              onClick={() => trackEvent('favorite_similar_shop_click', { product_id: item.product_id })}
            >
              SP tương tự →
            </Link>
          ) : null}
        </div>
      </div>
    </article>
  );
}

export default function FavoritesPage() {
  const { refreshFavorites } = useFavorites();
  const { isAuthenticated } = useAuth();
  const { pushToast } = useToast();
  const [items, setItems] = useState<FavoriteItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [removingId, setRemovingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    apiClient
      .getFavorites()
      .then(async (list) => {
        const raw = Array.isArray(list) ? list : [];
        const enriched = await Promise.all(
          raw.map(async (item: FavoriteItem) => {
            const data = item.product_data || {};
            const needsEnrich =
              !data.name ||
              data.price == null ||
              data.price === undefined ||
              !data.main_image ||
              !data.shop_name_chinese;
            if (!needsEnrich) return item;
            try {
              const product = await apiClient.getProductById(item.product_id);
              return {
                ...item,
                product_data: {
                  ...data,
                  id: product.id,
                  code: product.code,
                  product_id: product.product_id,
                  name: product.name,
                  price: product.price,
                  main_image: product.main_image,
                  brand_name: product.brand_name ?? data.brand_name,
                  slug: product.slug ?? data.slug,
                  shop_name_chinese: product.shop_name_chinese ?? data.shop_name_chinese,
                },
              };
            } catch {
              return item;
            }
          }),
        );
        if (cancelled) return;
        setItems(enriched);
        setError(null);
        void refreshFavorites();
      })
      .catch((e) => {
        if (cancelled) return;
        setItems([]);
        setError((e as Error)?.message || 'Không thể tải danh sách yêu thích');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, refreshFavorites]);

  const handleRemove = useCallback(
    async (productId: number, favoriteId: number) => {
      setRemovingId(favoriteId);
      try {
        await apiClient.removeFromFavorites(productId);
        setItems((prev) => prev.filter((f) => f.id !== favoriteId));
        await refreshFavorites();
        trackEvent('remove_favorite', { product_id: productId });
        pushToast({ title: 'Đã bỏ yêu thích', variant: 'success', durationMs: 2500 });
      } catch (e) {
        pushToast({
          title: 'Không thể bỏ yêu thích',
          description: (e as Error)?.message || 'Vui lòng thử lại',
          variant: 'error',
          durationMs: 3000,
        });
      } finally {
        setRemovingId(null);
      }
    },
    [pushToast, refreshFavorites],
  );

  const [retryLoading, setRetryLoading] = useState(false);

  const reload = () => {
    setError(null);
    setRetryLoading(true);
    window.location.reload();
  };

  return (
    <div className="min-h-screen bg-[#f8f9fb]">
      <div className="mx-auto max-w-7xl px-3 pb-8 pt-3 sm:px-4 md:py-6">
        <header className="mb-4 flex items-end justify-between gap-3 md:mb-6">
          <div>
            <h1 className="text-lg font-bold tracking-tight text-gray-900 md:text-2xl">Sản phẩm yêu thích</h1>
            <p className="mt-0.5 text-xs text-gray-500 sm:text-sm">
              {loading ? 'Đang tải…' : `${items.length} sản phẩm đã lưu`}
            </p>
          </div>
          {!loading && items.length > 0 ? (
            <LoadingLink
              href="/"
              className="shrink-0 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 shadow-sm hover:border-orange-200 hover:text-[#ea580c] sm:text-sm inline-flex items-center"
            >
              Tiếp tục mua sắm
            </LoadingLink>
          ) : null}
        </header>

        {error ? (
          <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}{' '}
            <Button
              type="button"
              variant="ghost"
              size="inline"
              onClick={reload}
              loading={retryLoading}
              className="font-medium underline hover:bg-transparent"
            >
              Thử lại
            </Button>
          </div>
        ) : null}

        {loading ? (
          <div className="grid grid-cols-2 gap-2 sm:gap-3 md:grid-cols-3 md:gap-4 lg:grid-cols-4">
            {[...Array(6)].map((_, i) => (
              <FavoriteCardSkeleton key={i} />
            ))}
          </div>
        ) : items.length === 0 ? (
          <div className="rounded-2xl border border-gray-100 bg-white px-6 py-12 text-center shadow-sm md:py-16">
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-red-50 text-red-400">
              <svg className="h-8 w-8" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
                <path d="M4.318 6.318a4.5 4.5 0 016.364 0L12 7.636l1.318-1.318a4.5 4.5 0 116.364 6.364L12 20.364l-7.682-7.682a4.5 4.5 0 010-6.364z" />
              </svg>
            </div>
            <p className="mb-1 text-base font-medium text-gray-900">Chưa có sản phẩm yêu thích</p>
            <p className="mb-6 text-sm text-gray-500">Nhấn ♥ trên sản phẩm để lưu vào danh sách này.</p>
            <LoadingLink
              href="/"
              className="inline-flex min-h-[44px] items-center justify-center rounded-xl bg-[#ea580c] px-6 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-[#c2410c]"
            >
              Khám phá sản phẩm
            </LoadingLink>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-2 sm:gap-3 md:grid-cols-3 md:gap-4 lg:grid-cols-4">
            {items.map((item, index) => (
              <FavoriteProductCard
                key={item.id}
                item={item}
                removing={removingId === item.id}
                priorityImage={index < 2}
                onRemove={handleRemove}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
