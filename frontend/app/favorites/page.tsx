'use client';

import { useState, useEffect } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { apiClient } from '@/lib/api-client';
import { getOptimizedImage } from '@/lib/image-utils';
import { useFavorites } from '@/features/favorites/hooks/useFavorites';
import { useAuth } from '@/features/auth/hooks/useAuth';
import { useToast } from '@/components/ToastProvider';
import { trackEvent } from '@/lib/analytics';

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
  };
}

function formatVnd(n: number) {
  return new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(n);
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
        // Bổ sung product_data từ API nếu thiếu (favorites cũ hoặc lỗi lưu)
        const enriched = await Promise.all(
          raw.map(async (item: FavoriteItem) => {
            const data = item.product_data || {};
            const needsEnrich =
              !data.name || data.price == null || data.price === undefined || !data.main_image;
            if (!needsEnrich) return item;
            try {
              const product = await apiClient.getProductById(item.product_id);
              return {
                ...item,
                product_data: {
                  ...data,
                  id: product.id,
                  product_id: product.product_id,
                  name: product.name,
                  price: product.price,
                  main_image: product.main_image,
                  brand_name: product.brand_name ?? data.brand_name,
                  slug: product.slug ?? data.slug,
                },
              };
            } catch {
              return item;
            }
          })
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

  const handleRemove = async (productId: number, favoriteId: number) => {
    setRemovingId(favoriteId);
    try {
      await apiClient.removeFromFavorites(productId);
      setItems((prev) => prev.filter((f) => f.id !== favoriteId));
      await refreshFavorites();
      trackEvent('remove_favorite', { product_id: productId });
      pushToast({ title: 'Đã bỏ yêu thích', variant: 'success', durationMs: 2500 });
    } catch (e) {
      pushToast({ title: 'Không thể bỏ yêu thích', description: (e as Error)?.message || 'Vui lòng thử lại', variant: 'error', durationMs: 3000 });
    } finally {
      setRemovingId(null);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-3 pb-5 pt-2 sm:px-3 md:px-4 md:py-8 md:pb-6 md:pt-3">
        <div className="mb-3 md:mb-6">
          <h1 className="text-base font-bold tracking-tight text-gray-900 sm:text-lg md:text-2xl">
            Sản phẩm yêu thích
          </h1>
          <p className="mt-0.5 text-xs text-gray-600 sm:text-sm md:mt-1 md:text-base">
            Đã thích ({items.length})
          </p>
        </div>

        {error && (
          <div className="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 md:mb-4 md:px-4 md:py-3 md:text-sm">
            {error}
          </div>
        )}

        {loading ? (
          <div className="py-6 text-center text-sm text-gray-500 md:py-12 md:text-base">Đang tải...</div>
        ) : items.length === 0 ? (
          <div className="rounded-xl border border-gray-100 bg-white p-6 text-center shadow sm:p-8 md:p-12">
            <p className="mb-3 text-sm text-gray-500 md:mb-4 md:text-base">Bạn chưa thích sản phẩm nào.</p>
            <Link
              href="/"
              className="inline-flex min-h-[44px] items-center justify-center rounded-lg bg-[#ea580c] px-5 py-2.5 font-medium text-white hover:bg-[#c2410c] md:min-h-0"
            >
              Khám phá sản phẩm
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-2 md:gap-6 lg:grid-cols-3 xl:grid-cols-4">
            {items.map((item) => {
              const data = item.product_data || {};
              const name = data.name || `Sản phẩm #${item.product_id}`;
              const price = data.price ?? 0;
              const slug = data.slug || String(item.product_id);
              const href = `/products/${slug}`;
              const imageUrl = getOptimizedImage(data.main_image, { fallbackStrategy: 'local' });

              return (
                <div
                  key={item.id}
                  className="bg-white rounded-xl shadow border border-gray-100 overflow-hidden hover:shadow-md transition-shadow"
                >
                  <Link href={href} className="block aspect-square bg-gray-100 relative">
                    <Image src={imageUrl} alt={name} fill sizes="(min-width: 1280px) 20vw, (min-width: 1024px) 25vw, (min-width: 640px) 33vw, 100vw" className="object-cover" />
                  </Link>
                  <div className="p-3 md:p-4">
                    <Link href={href}>
                      <h3 className="text-sm font-medium leading-snug text-gray-900 line-clamp-2 hover:text-[#ea580c] md:text-base">
                        {name}
                      </h3>
                    </Link>
                    {data.brand_name && (
                      <p className="mt-0.5 text-xs text-gray-500 md:text-sm">{data.brand_name}</p>
                    )}
                    <p className="mt-2 text-base font-bold text-[#ea580c] md:text-lg">
                      {formatVnd(price)}
                    </p>
                    <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                      <Link
                        href={href}
                        className="flex-1 rounded-lg bg-gray-100 px-3 py-2 text-center text-sm font-medium text-gray-800 hover:bg-gray-200 min-h-[44px] flex items-center justify-center md:min-h-0"
                      >
                        Xem chi tiết
                      </Link>
                      <button
                        type="button"
                        onClick={() => handleRemove(item.product_id, item.id)}
                        disabled={removingId === item.id}
                        className="rounded-lg border border-red-200 px-3 py-2 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50 min-h-[44px] md:min-h-0"
                      >
                        {removingId === item.id ? 'Đang xóa...' : 'Bỏ thích'}
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
