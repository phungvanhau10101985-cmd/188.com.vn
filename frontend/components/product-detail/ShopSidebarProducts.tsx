// frontend/components/product-detail/ShopSidebarProducts.tsx
'use client';

import { useEffect, useMemo, useState } from 'react';
import { cdnUrl } from '@/lib/cdn-url';
import Image from 'next/image';
import Link from 'next/link';
import { Product } from '@/types/api';
import { apiClient } from '@/lib/api-client';
import { formatPrice, getProductMainImage } from '@/lib/utils';

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

  useEffect(() => {
    let isMounted = true;
    const fetchSameShop = async () => {
      try {
        setLoading(true);
        if (!currentProduct.shop_id) {
          if (isMounted) setProducts([]);
          return;
        }
        const response = await apiClient.getProducts({
          shop_id: currentProduct.shop_id,
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
    fetchSameShop();
    return () => {
      isMounted = false;
    };
  }, [currentProduct.id, currentProduct.shop_id]);

  const visibleProducts = useMemo(() => products, [products]);

  if (loading || visibleProducts.length === 0) return null;

  return (
    <aside className="w-full">
      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <div className="divide-y divide-gray-100">
          {visibleProducts.map((product) => (
            <Link
              key={product.id}
              href={`/products/${product.slug || product.id}`}
              className="flex flex-col items-center gap-2 p-3 -mt-6 first:mt-0 hover:bg-gray-50"
            >
              <div className="w-32 h-32 bg-gray-100 rounded overflow-hidden flex-shrink-0 relative">
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
              </div>
              <div className="text-sm font-bold text-[#ea580c] mt-0.5">
                {formatPrice(product.price)}
              </div>
            </Link>
          ))}
        </div>
      </div>
    </aside>
  );
}
