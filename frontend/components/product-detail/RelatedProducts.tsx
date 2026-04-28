// frontend/components/product-detail/RelatedProducts.tsx - FILE FIX
'use client';

import { useState, useEffect, useCallback } from 'react';
import { cdnUrl } from '@/lib/cdn-url';
import Image from 'next/image';
import Link from 'next/link';
import { Product } from '@/types/api';
import { apiClient } from '@/lib/api-client';
import { formatPrice, getProductMainImage } from '@/lib/utils';

interface RelatedProductsProps {
  currentProduct: Product;
}

export default function RelatedProducts({ currentProduct }: RelatedProductsProps) {
  const [relatedProducts, setRelatedProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [visibleCount, setVisibleCount] = useState(5);
  const [total, setTotal] = useState(0);
  const [showAllLoading, setShowAllLoading] = useState(false);

  const fetchRelatedProducts = useCallback(async () => {
    try {
      setLoading(true);
      if (!currentProduct.shop_name) {
        setRelatedProducts([]);
        setTotal(0);
        return;
      }

      const response = await apiClient.getProducts({
        shop_name: currentProduct.shop_name,
        limit: 60,
        is_active: true
      });

      const filteredProducts = response.products.filter(
        product => product.id !== currentProduct.id
      );

      setRelatedProducts(filteredProducts);
      setTotal(Math.max(0, response.total - 1));
      setVisibleCount(5);
    } catch (error) {
      console.error('Error fetching related products:', error);
      setRelatedProducts([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [currentProduct.id, currentProduct.shop_name]);

  useEffect(() => {
    fetchRelatedProducts();
  }, [fetchRelatedProducts]);

  if (loading) {
    return (
      <div className="border-t border-gray-200 pt-5">
        <h3 className="text-lg font-bold text-gray-900 mb-3">Sản Phẩm Liên Quan</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[...Array(4)].map((_, index) => (
            <div key={index} className="animate-pulse">
              <div className="aspect-square bg-gray-200 rounded-lg mb-2"></div>
              <div className="h-4 bg-gray-200 rounded mb-1"></div>
              <div className="h-4 bg-gray-200 rounded w-3/4"></div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (relatedProducts.length === 0) {
    return null;
  }

  const visibleProducts = relatedProducts.slice(0, visibleCount);
  const canLoadMore = visibleCount < relatedProducts.length;
  const canShowAll = relatedProducts.length > 0 && visibleCount < relatedProducts.length;

  const handleLoadMore = () => {
    setVisibleCount((prev) => Math.min(prev + 5, relatedProducts.length));
  };

  const handleShowAll = async () => {
    if (relatedProducts.length >= total || total === 0) {
      setVisibleCount(relatedProducts.length);
      return;
    }
    try {
      setShowAllLoading(true);
      const response = await apiClient.getProducts({
        shop_name: currentProduct.shop_name,
        limit: Math.min(total, 200),
        is_active: true
      });
      const filteredProducts = response.products.filter(
        product => product.id !== currentProduct.id
      );
      setRelatedProducts(filteredProducts);
      setVisibleCount(filteredProducts.length);
      setTotal(Math.max(0, response.total - 1));
    } catch (error) {
      console.error('Error fetching all related products:', error);
      setVisibleCount(relatedProducts.length);
    } finally {
      setShowAllLoading(false);
    }
  };

  return (
    <div className="border-t border-gray-200 pt-5">
      <h3 className="text-base font-bold text-gray-900 mb-3 uppercase">Sản phẩm cùng shop</h3>

      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
        {visibleProducts.map((product) => (
          <Link
            key={product.id}
            href={`/products/${product.slug || product.id}`}
            className="group block bg-white rounded-lg border border-gray-200 overflow-hidden hover:shadow-md transition-all"
          >
            <div className="aspect-square bg-gray-100 overflow-hidden relative">
              <Image
                src={getProductMainImage(product)}
                alt={product.name}
                fill
                sizes="(min-width: 1024px) 20vw, (min-width: 640px) 25vw, 50vw"
                className="object-cover group-hover:scale-110 transition-transform duration-300"
                onError={(e) => {
                  (e.currentTarget as HTMLImageElement).src = cdnUrl('/images/placeholder.jpg');
                }}
              />
            </div>

            <div className="p-2">
              <h4 className="font-medium text-gray-900 line-clamp-2 text-xs leading-tight mb-1 group-hover:text-[#ea580c] transition-colors">
                {product.name}
              </h4>

              <div className="flex items-baseline justify-between">
                <span className="text-sm font-bold text-[#ea580c]">
                  {formatPrice(product.price)}
                </span>
                {product.original_price && product.original_price > product.price && (
                  <span className="text-xs text-gray-500 line-through">
                    {formatPrice(product.original_price)}
                  </span>
                )}
              </div>

              {typeof product.purchases === 'number' && product.purchases > 0 && (
                <div className="mt-1 text-[10px] text-gray-500">Đã bán {product.purchases}</div>
              )}
            </div>
          </Link>
        ))}
      </div>

      {(canLoadMore || canShowAll) && (
        <div className="flex items-center justify-center gap-4 mt-4">
          {canLoadMore && (
            <button
              type="button"
              onClick={handleLoadMore}
              className="inline-flex items-center gap-2 text-sm text-gray-700 hover:text-[#ea580c]"
            >
              <span className="inline-flex items-center justify-center w-7 h-7 rounded-full border border-gray-300">
                ↻
              </span>
              Xem thêm
            </button>
          )}
          {canShowAll && (
            <button
              type="button"
              onClick={handleShowAll}
              disabled={showAllLoading}
              className="px-4 py-2 bg-[#ea580c] text-white rounded-lg text-sm font-medium disabled:opacity-60"
            >
              {showAllLoading ? 'Đang tải...' : 'Xem tất cả'}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
