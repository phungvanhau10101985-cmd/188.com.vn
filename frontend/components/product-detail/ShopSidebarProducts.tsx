// frontend/components/product-detail/ShopSidebarProducts.tsx
'use client';

import { useEffect, useMemo, useState } from 'react';
import { cdnUrl } from '@/lib/cdn-url';
import Image from 'next/image';
import Link from 'next/link';
import { Product } from '@/types/api';
import { apiClient } from '@/lib/api-client';
import { formatPrice, getProductMainImage } from '@/lib/utils';
import { productPathSlugFromApi } from '@/lib/product-path-slug';
import { excelCell } from '@/lib/product-related-tabs';
import { applyBirthdayDiscount } from '@/lib/birthday-discount';
import { useBirthdayDiscount } from '@/lib/use-birthday-discount';
import { BirthdayPromoImageBadge, BirthdayPromoPriceCakeIcon } from '@/components/BirthdayPromoProductMarkers';

interface ShopSidebarProductsProps {
  currentProduct: Product;
}

function shuffle<T>(items: T[]): T[] {
  const arr = [...items];
  for (let i = arr.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

export default function ShopSidebarProducts({ currentProduct }: ShopSidebarProductsProps) {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const birthdayDiscount = useBirthdayDiscount();

  useEffect(() => {
    let isMounted = true;
    const fetchSameStyle = async () => {
      try {
        setLoading(true);
        /** Sidebar: lọc theo cột Style (AF) — khác với nhóm «cùng shop TQ / shop_name_chinese» trên tab liên quan. */
        const st = excelCell(currentProduct.style);
        if (!st) {
          if (isMounted) setProducts([]);
          return;
        }
        const response = await apiClient.getProducts({
          style: st,
          limit: 40,
          is_active: true,
        });
        const filtered = response.products.filter((p) => p.id !== currentProduct.id);
        if (isMounted) setProducts(shuffle(filtered).slice(0, 8));
      } catch {
        if (isMounted) setProducts([]);
      } finally {
        if (isMounted) setLoading(false);
      }
    };
    fetchSameStyle();
    return () => {
      isMounted = false;
    };
  }, [currentProduct.id, currentProduct.style]);

  const visibleProducts = useMemo(() => products, [products]);

  if (loading || visibleProducts.length === 0) return null;

  return (
    <aside className="w-full">
      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <div className="divide-y divide-gray-100">
          {visibleProducts.map((product) => {
            const displayPrice = birthdayDiscount.active
              ? applyBirthdayDiscount(product.price || 0, birthdayDiscount.percent)
              : product.price || 0;
            return (
              <Link
                key={product.id}
                href={`/products/${productPathSlugFromApi(product.slug, product.product_id) || product.id}`}
                className="flex flex-col items-center gap-2 p-3 -mt-6 first:mt-0 hover:bg-gray-50"
              >
                <div className="relative h-32 w-32 flex-shrink-0 overflow-hidden rounded bg-gray-100">
                  <Image
                    src={getProductMainImage(product)}
                    alt={product.name}
                    fill
                    sizes="128px"
                    className="object-cover"
                    onError={(e) => {
                      (e.currentTarget as HTMLImageElement).src = cdnUrl('/images/placeholder.jpg');
                    }}
                  />
                  <BirthdayPromoImageBadge
                    active={birthdayDiscount.active}
                    percent={birthdayDiscount.percent}
                    className="left-1 top-1 px-1 py-px text-[9px] sm:text-[10px]"
                  />
                </div>
                <div className="flex flex-wrap items-center justify-center gap-x-1 gap-y-0">
                  <div className="mt-0.5 text-sm font-bold text-[#ea580c]">{formatPrice(displayPrice)}</div>
                  <BirthdayPromoPriceCakeIcon active={birthdayDiscount.active} percent={birthdayDiscount.percent} />
                </div>
                {birthdayDiscount.active && displayPrice < (product.price || 0) && (
                  <div className="-mt-2 text-xs text-gray-400 line-through decoration-1 decoration-gray-400">
                    {formatPrice(product.price)}
                  </div>
                )}
              </Link>
            );
          })}
        </div>
      </div>
    </aside>
  );
}
