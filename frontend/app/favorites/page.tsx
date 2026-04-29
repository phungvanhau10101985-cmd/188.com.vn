'use client';

import { useState, useEffect } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { apiClient } from '@/lib/api-client';
import { getOptimizedImage } from '@/lib/image-utils';
import { useFavorites } from '@/features/favorites/hooks/useFavorites';
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
  const { pushToast } = useToast();
  const [items, setItems] = useState<FavoriteItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [removingId, setRemovingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
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
        setItems(enriched);
        setError(null);
      })
      .catch((e) => {
        setItems([]);
        setError((e as Error)?.message || 'Không thể tải danh sách yêu thích');
      })
      .finally(() => setLoading(false));
  }, []);

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
      <div className="max-w-7xl mx-auto px-4 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Sản phẩm yêu thích</h1>
          <p className="text-gray-600 mt-1">Danh sách sản phẩm bạn đã thích ({items.length})</p>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm mb-4">
            {error}
          </div>
        )}

        {loading ? (
          <div className="py-12 text-center text-gray-500">Đang tải...</div>
        ) : items.length === 0 ? (
          <div className="bg-white rounded-xl shadow border border-gray-100 p-12 text-center">
            <p className="text-gray-500 mb-4">Bạn chưa thích sản phẩm nào.</p>
            <Link
              href="/"
              className="inline-block px-5 py-2.5 bg-[#ea580c] text-white font-medium rounded-lg hover:bg-[#c2410c]"
            >
              Khám phá sản phẩm
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
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
                  <div className="p-4">
                    <Link href={href}>
                      <h3 className="font-medium text-gray-900 line-clamp-2 hover:text-[#ea580c]">
                        {name}
                      </h3>
                    </Link>
                    {data.brand_name && (
                      <p className="text-sm text-gray-500 mt-0.5">{data.brand_name}</p>
                    )}
                    <p className="text-lg font-bold text-[#ea580c] mt-2">
                      {formatVnd(price)}
                    </p>
                    <div className="mt-3 flex gap-2">
                      <Link
                        href={href}
                        className="flex-1 text-center py-2 px-3 bg-gray-100 text-gray-800 rounded-lg text-sm font-medium hover:bg-gray-200"
                      >
                        Xem chi tiết
                      </Link>
                      <button
                        type="button"
                        onClick={() => handleRemove(item.product_id, item.id)}
                        disabled={removingId === item.id}
                        className="py-2 px-3 border border-red-200 text-red-600 rounded-lg text-sm font-medium hover:bg-red-50 disabled:opacity-50"
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
