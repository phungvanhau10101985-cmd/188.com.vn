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
      <div className="max-w-7xl mx-auto px-3 pt-3 pb-6 md:px-4 md:py-8">
        <div className="mb-4 md:mb-6">
          <h1 className="text-lg font-bold tracking-tight text-gray-900 md:text-2xl">
            Sản phẩm đã xem
          </h1>
          <p className="mt-0.5 text-sm text-gray-600 md:mt-1 md:text-base">
            Đã xem gần đây ({items.length})
          </p>
          {/* Mobile: gọn — mở rộng khi cần; desktop: luôn hiện đủ */}
          <details className="mt-2 rounded-lg border border-gray-200 bg-white open:[&_summary_svg]:rotate-180 md:hidden">
            <summary className="cursor-pointer list-none px-3 py-2.5 text-sm font-medium text-gray-800 [&::-webkit-details-marker]:hidden">
              <span className="flex items-center justify-between gap-2">
                Lưu ý đồng bộ danh sách
                <svg className="h-4 w-4 shrink-0 text-gray-400 transition-transform duration-200" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </span>
            </summary>
            <p className="border-t border-gray-100 px-3 py-2 text-xs leading-relaxed text-gray-600">
              Không cần đăng nhập vẫn xem được trong phiên trình duyệt này. Đăng nhập để đồng bộ và giữ trên tài khoản (phiên khách gộp vào tài khoản khi đăng nhập).
            </p>
          </details>
          <p className="mt-2 hidden text-sm text-gray-600 md:block rounded-lg border border-gray-200 bg-gray-50 px-3 py-2">
            Không cần đăng nhập vẫn xem được danh sách đã xem trong phiên trình duyệt này. Đăng nhập để đồng bộ và giữ trên tài khoản (phiên khách được gộp vào tài khoản khi đăng nhập).
          </p>
        </div>

        {loading ? (
          <div className="py-8 text-center text-gray-500 md:py-12">Đang tải...</div>
        ) : items.length === 0 ? (
          <div className="rounded-xl border border-gray-100 bg-white p-8 text-center shadow md:p-12">
            <p className="text-gray-500 mb-4">Bạn chưa xem sản phẩm nào.</p>
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
                    <Link
                      href={href}
                      className="mt-3 flex min-h-[44px] w-full items-center justify-center rounded-lg bg-[#ea580c] px-3 py-2 text-center text-sm font-medium text-white hover:bg-orange-600 md:min-h-0"
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
