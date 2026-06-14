// frontend/components/product-detail/ShopSidebarProducts.tsx
'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useNearViewport } from '@/lib/use-near-viewport';
import { cdnUrl } from '@/lib/cdn-url';
import Image from 'next/image';
import Link from 'next/link';
import { Product } from '@/types/api';
import { formatPrice, getProductMainImage } from '@/lib/utils';
import { productPathSlugFromApi } from '@/lib/product-path-slug';
import { excelCell } from '@/lib/product-related-tabs';
import {
  getCachedPdpSidebarProducts,
  loadRelatedProductsSnapshot,
  pickRandomSidebarProducts,
} from '@/lib/related-products-pdp-fetch';
import { applyBirthdayDiscount } from '@/lib/birthday-discount';
import { useBirthdayDiscount } from '@/lib/use-birthday-discount';
import { BirthdayPromoImageBadge, BirthdayPromoPriceCakeIcon } from '@/components/BirthdayPromoProductMarkers';
import ProductCardClearanceMeta from '@/components/ProductCardClearanceMeta';

interface ShopSidebarProductsProps {
  currentProduct: Product;
}

export default function ShopSidebarProducts({ currentProduct }: ShopSidebarProductsProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const isNear = useNearViewport(containerRef);
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(false);
  const birthdayDiscount = useBirthdayDiscount();

  useEffect(() => {
    if (!isNear) return;

    const st = excelCell(currentProduct.style);
    if (!st) {
      setProducts([]);
      return;
    }

    const applyPool = (pool: Product[]) => {
      setProducts(pickRandomSidebarProducts(pool));
    };

    const cached = getCachedPdpSidebarProducts(currentProduct.id);
    if (cached?.length) {
      applyPool(cached);
      return;
    }

    let isMounted = true;
    setLoading(true);
    void loadRelatedProductsSnapshot(currentProduct, 'bestselling')
      .then((snap) => {
        if (!isMounted) return;
        const pool = snap.sidebarProducts?.length
          ? snap.sidebarProducts
          : getCachedPdpSidebarProducts(currentProduct.id) ?? [];
        applyPool(pool);
      })
      .catch(() => {
        if (isMounted) setProducts([]);
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [isNear, currentProduct]);

  const visibleProducts = useMemo(() => products, [products]);

  if (!isNear) {
    return <div ref={containerRef} className="min-h-[8rem] w-full" aria-hidden="true" />;
  }

  if (loading || visibleProducts.length === 0) return null;

  return (
    <aside ref={containerRef} className="w-full">
      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <div className="divide-y divide-gray-100">
          {visibleProducts.map((product) => {
            const displayPrice = birthdayDiscount.active
              ? applyBirthdayDiscount(product.price || 0, birthdayDiscount.percent)
              : product.price || 0;
            const pathSeg =
              productPathSlugFromApi(product.slug, product.product_id) || product.product_id;
            if (!pathSeg) return null;
            return (
              <Link
                key={product.id}
                href={`/products/${encodeURIComponent(String(pathSeg))}`}
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
                <ProductCardClearanceMeta product={product} compact className="mt-1 w-full max-w-[8.5rem]" />
              </Link>
            );
          })}
        </div>
      </div>
    </aside>
  );
}
