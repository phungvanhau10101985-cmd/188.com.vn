'use client';

import { useEffect, useMemo, useState } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import type { Product } from '@/types/api';
import { apiClient } from '@/lib/api-client';
import { sortProductsByIds } from '@/lib/ladipage-utils';
import { formatPrice } from '@/lib/utils';
import { productPathSlugFromApi } from '@/lib/product-path-slug';
import ProductBuyModal from './ProductBuyModal';

interface ProductsGridSectionProps {
  productIds: number[];
  /** Sản phẩm đã fetch server-side — SEO + SSR lưới sản phẩm trên ladipage. */
  initialProducts?: Product[];
  /** Nguồn cho analytics, vd `ladipage:{slug}`. */
  source?: string;
}

export default function ProductsGridSection({
  productIds,
  initialProducts,
  source,
}: ProductsGridSectionProps) {
  const sortedInitial = useMemo(
    () => (initialProducts?.length ? sortProductsByIds(initialProducts, productIds) : []),
    [initialProducts, productIds],
  );
  const hasInitial = sortedInitial.length > 0;

  const [products, setProducts] = useState<Product[]>(() => (hasInitial ? sortedInitial : []));
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>(() =>
    !productIds?.length ? 'ready' : hasInitial ? 'ready' : 'loading',
  );
  const [openProductId, setOpenProductId] = useState<number | null>(null);

  useEffect(() => {
    if (hasInitial) {
      setProducts(sortedInitial);
      setStatus('ready');
    }
  }, [hasInitial, sortedInitial]);

  useEffect(() => {
    if (hasInitial) return;
    let alive = true;
    if (!productIds || productIds.length === 0) {
      setProducts([]);
      setStatus('ready');
      return;
    }
    setStatus('loading');
    apiClient
      .getProductsByIds(productIds)
      .then((rows) => {
        if (!alive) return;
        setProducts(sortProductsByIds(rows, productIds));
        setStatus('ready');
      })
      .catch(() => {
        if (!alive) return;
        setStatus('error');
      });
    return () => {
      alive = false;
    };
  }, [productIds, hasInitial]);

  const retryFetch = () => {
    if (!productIds?.length) return;
    setStatus('loading');
    apiClient
      .getProductsByIds(productIds)
      .then((rows) => {
        setProducts(sortProductsByIds(rows, productIds));
        setStatus('ready');
      })
      .catch(() => setStatus('error'));
  };

  const openProduct = products.find((p) => p.id === openProductId) || null;

  return (
    <section className="scroll-mt-6 py-8 md:py-12" id="ladipage-products">
      <div className="mb-6 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-orange-600">Lựa chọn dành cho bạn</p>
          <h2 className="mt-1 text-2xl font-extrabold tracking-tight text-gray-950 md:text-3xl">Sản phẩm nổi bật</h2>
          <p className="mt-2 text-sm text-gray-600">
            Khám phá thông tin, giá bán và lựa chọn phù hợp với nhu cầu của bạn.
          </p>
        </div>
        {status === 'ready' && products.length > 0 && (
          <p className="text-sm font-semibold text-gray-500">{products.length} sản phẩm</p>
        )}
      </div>

      {status === 'loading' && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="animate-pulse overflow-hidden rounded-2xl border border-gray-100 bg-white">
              <div className="aspect-square bg-gray-200" />
              <div className="space-y-2 p-3">
                <div className="h-3 w-3/4 rounded bg-gray-200" />
                <div className="h-3 w-1/2 rounded bg-gray-200" />
              </div>
            </div>
          ))}
        </div>
      )}

      {status === 'error' && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          Không tải được danh sách sản phẩm.{' '}
          <button type="button" onClick={retryFetch} className="font-medium underline">
            Thử lại
          </button>
        </div>
      )}

      {status === 'ready' && products.length === 0 && (
        <p className="italic text-gray-400">Chưa có sản phẩm nào để hiển thị.</p>
      )}

      {status === 'ready' && products.length > 0 && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {products.map((p) => {
            const seg = productPathSlugFromApi(p.slug, p.product_id) || p.product_id;
            const href = seg ? `/products/${encodeURIComponent(seg)}` : '#';
            return (
              <div
                key={p.id}
                className="group overflow-hidden rounded-2xl border border-gray-100 bg-white shadow-sm transition duration-200 hover:-translate-y-1 hover:border-orange-200 hover:shadow-xl hover:shadow-orange-900/10"
              >
                <Link href={href} className="block aspect-square overflow-hidden bg-gray-50">
                  {p.main_image || p.images?.[0] ? (
                    <Image
                      src={p.main_image || p.images![0]}
                      alt={p.name}
                      width={400}
                      height={400}
                      className="h-full w-full object-cover transition duration-500 group-hover:scale-105"
                    />
                  ) : (
                    <div className="flex h-full w-full items-center justify-center text-xs text-gray-400">
                      Không có ảnh
                    </div>
                  )}
                </Link>
                <div className="p-4">
                  <Link
                    href={href}
                    className="line-clamp-2 min-h-[2.5em] text-sm font-semibold leading-relaxed text-gray-900 transition hover:text-orange-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-600"
                  >
                    {p.name}
                  </Link>
                  <p className="mt-2 text-lg font-extrabold text-orange-600">{formatPrice(p.price)}</p>
                  <button
                    type="button"
                    onClick={() => setOpenProductId(p.id)}
                    className="mt-3 w-full rounded-full bg-gray-950 py-2.5 text-xs font-bold text-white transition hover:bg-orange-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-600"
                  >
                    Thêm vào giỏ
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {openProduct && (
        <ProductBuyModal
          product={openProduct}
          isOpen
          onClose={() => setOpenProductId(null)}
          source={source}
        />
      )}
    </section>
  );
}
