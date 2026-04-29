'use client';

import { useState, useEffect } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { apiClient } from '@/lib/api-client';
import { getOptimizedImage } from '@/lib/image-utils';

interface ViewedItem {
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
  viewed_at?: string;
}

function formatVnd(n: number) {
  return new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(n);
}

export default function DaXemPage() {
  const [items, setItems] = useState<ViewedItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    apiClient
      .getViewedProducts(24)
      .then(async (list) => {
        const raw = Array.isArray(list) ? list : [];
        const enriched = await Promise.all(
          raw.map(async (item: ViewedItem) => {
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
      })
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Sản phẩm đã xem</h1>
          <p className="text-gray-600 mt-1">
            Các sản phẩm bạn đã xem gần đây ({items.length})
          </p>
          <p className="text-sm text-gray-600 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 mt-2">
            Không cần đăng nhập vẫn xem được danh sách đã xem trong phiên trình duyệt này. Đăng nhập để đồng bộ và giữ trên tài khoản (phiên khách được gộp vào tài khoản khi đăng nhập).
          </p>
        </div>

        {loading ? (
          <div className="py-12 text-center text-gray-500">Đang tải...</div>
        ) : items.length === 0 ? (
          <div className="bg-white rounded-xl shadow border border-gray-100 p-12 text-center">
            <p className="text-gray-500 mb-4">Bạn chưa xem sản phẩm nào.</p>
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
                    <Link
                      href={href}
                      className="mt-3 block w-full text-center py-2 px-3 bg-[#ea580c] text-white rounded-lg text-sm font-medium hover:bg-orange-600"
                    >
                      Xem chi tiết
                    </Link>
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
