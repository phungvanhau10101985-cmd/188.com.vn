'use client';

import { useState, useEffect } from 'react';
import type { Product, ProductSearchParams } from '@/types/api';
import { productAPI } from '../api/product-api';
import ProductCard from './ProductCard';

interface ProductListProps {
  initialProducts?: Product[];
  searchParams?: ProductSearchParams;
  showFilters?: boolean;
  onProductClick?: (product: Product) => void;
  onAddToCart?: (product: Product) => void;
}

export default function ProductList({ 
  initialProducts = [], 
  searchParams = {},
  showFilters = true,
  onProductClick,
  onAddToCart 
}: ProductListProps) {
  const [products, setProducts] = useState<Product[]>(initialProducts);
  const [loading, setLoading] = useState(!initialProducts.length);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<ProductSearchParams>({
    page: 1,
    limit: 20,
    ...searchParams
  });

  // Fetch products
  const fetchProducts = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await productAPI.getProducts(filters);
      setProducts(response.products);
    } catch (err) {
      setError('Không thể tải danh sách sản phẩm');
      console.error('Lỗi tải sản phẩm:', err);
    } finally {
      setLoading(false);
    }
  };

  // Load products on component mount and when filters change
  useEffect(() => {
    if (!initialProducts.length) {
      fetchProducts();
    }
  }, [filters, initialProducts.length]);

  // Handle filter changes
  const handleFilterChange = (newFilters: Partial<ProductSearchParams>) => {
    setFilters((prev: ProductSearchParams) => ({ ...prev, ...newFilters, page: 1 }));
  };

  // Handle load more
  const handleLoadMore = () => {
    setFilters((prev: ProductSearchParams) => ({ ...prev, page: (prev.page || 1) + 1 }));
  };

  // Handle product click
  const handleProductClick = (product: Product) => {
    onProductClick?.(product);
    // Có thể điều hướng đến trang chi tiết sản phẩm
    // router.push(`/products/${product.id}`);
  };

  // Handle add to cart
  const handleAddToCart = (product: Product) => {
    onAddToCart?.(product);
    // Có thể hiển thị thông báo thành công
  };

  if (loading && !products.length) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
          {[...Array(10)].map((_, index) => (
            <div key={index} className="bg-white rounded-lg shadow-md p-4 animate-pulse">
              <div className="bg-gray-300 h-48 rounded-md mb-4"></div>
              <div className="space-y-2">
                <div className="h-4 bg-gray-300 rounded w-3/4"></div>
                <div className="h-4 bg-gray-300 rounded w-1/2"></div>
                <div className="h-6 bg-gray-300 rounded w-1/3"></div>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="container mx-auto px-4 py-8 text-center">
        <div className="bg-red-50 border border-red-200 rounded-lg p-6">
          <p className="text-red-600 mb-4">{error}</p>
          <button
            onClick={fetchProducts}
            className="bg-red-500 hover:bg-red-600 text-white px-4 py-2 rounded-lg"
          >
            Thử lại
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-2xl font-bold text-gray-800">
          Sản Phẩm {products.length > 0 && `(${products.length})`}
        </h2>
      </div>

      {/* Filters */}
      {showFilters && (
        <div className="sticky top-[var(--mobile-app-header-height)] z-40 mb-6 border-b border-gray-200 bg-gray-50/95 px-2 py-1.5 shadow-sm backdrop-blur md:top-[var(--listing-filter-sticky-top)] md:border-t-0 md:bg-gray-50 md:shadow-none md:backdrop-blur-none">
          <div className="flex flex-wrap items-end gap-2">
            <div>
              <label className="sr-only">Sắp xếp</label>
              <select
                onChange={(e) => handleFilterChange({ sort_by: e.target.value as any })}
                className="h-8 rounded-md border border-gray-300 px-2 text-xs"
              >
                <option value="created_at">Mới nhất</option>
                <option value="price">Giá thấp đến cao</option>
                <option value="price_desc">Giá cao đến thấp</option>
                <option value="name">Tên A-Z</option>
              </select>
            </div>
            <div>
              <label className="sr-only">Khoảng giá</label>
              <div className="flex gap-2">
                <input
                  type="number"
                  placeholder="Từ"
                  className="h-8 w-24 rounded-md border border-gray-300 px-2 text-xs"
                  onChange={(e) => handleFilterChange({ min_price: Number(e.target.value) })}
                />
                <input
                  type="number"
                  placeholder="Đến"
                  className="h-8 w-24 rounded-md border border-gray-300 px-2 text-xs"
                  onChange={(e) => handleFilterChange({ max_price: Number(e.target.value) })}
                />
              </div>
            </div>
            
            <div>
              <label className="sr-only">Tình trạng</label>
              <select 
                onChange={(e) => handleFilterChange({ in_stock: e.target.value === 'true' })}
                className="h-8 rounded-md border border-gray-300 px-2 text-xs"
              >
                <option value="">Tất cả</option>
                <option value="true">Còn hàng</option>
                <option value="false">Hết hàng</option>
              </select>
            </div>
          </div>
        </div>
      )}

      {/* Product Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4 md:gap-6">
        {products.map((product) => (
          <ProductCard
            key={product.id}
            product={product}
            onProductClick={handleProductClick}
            onAddToCart={handleAddToCart}
          />
        ))}
      </div>

      {/* Empty State */}
      {products.length === 0 && !loading && (
        <div className="text-center py-12">
          <div className="text-gray-400 text-6xl mb-4">📦</div>
          <h3 className="text-xl font-semibold text-gray-600 mb-2">Không tìm thấy sản phẩm</h3>
          <p className="text-gray-500">Hãy thử điều chỉnh bộ lọc hoặc tìm kiếm với từ khóa khác</p>
        </div>
      )}

      {/* Load More */}
      {products.length > 0 && (
        <div className="text-center mt-8">
          <button
            onClick={handleLoadMore}
            disabled={loading}
            className="bg-orange-500 hover:bg-orange-600 text-white px-6 py-3 rounded-lg font-medium disabled:opacity-50"
          >
            {loading ? 'Đang tải...' : 'Xem thêm sản phẩm'}
          </button>
        </div>
      )}
    </div>
  );
}
