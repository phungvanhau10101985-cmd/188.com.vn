// frontend/components/ProductGrid.tsx - COMPLETE UPDATED VERSION
'use client';

import { useState, useEffect } from 'react';
import type { Product } from '@/types/api';
import { SimpleProductCard } from './ProductCard';
import { apiClient } from '@/lib/api-client';
import { useAuth } from '@/features/auth/hooks/useAuth';

interface ProductGridProps {
  products: Product[];
  loading: boolean;
  searchTerm?: string;
  selectedCategory?: string;
  onReload?: () => void;
  showFilters?: boolean;
}

// Skeleton Loading Component
const ProductGridSkeleton = () => (
  <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-5">
    {[...Array(10)].map((_, i) => (
      <div key={i} className="bg-white rounded-xl border border-gray-100 overflow-hidden animate-pulse shadow-sm">
        <div className="aspect-square bg-gray-100"></div>
        <div className="p-3 space-y-2">
          <div className="h-3 bg-gray-100 rounded w-3/4"></div>
          <div className="h-3 bg-gray-100 rounded w-full"></div>
          <div className="h-4 bg-gray-100 rounded w-2/5"></div>
        </div>
      </div>
    ))}
  </div>
);

// Empty State Component
const EmptyState = ({
  searchTerm,
  selectedCategory,
  onReload
}: {
  searchTerm: string;
  selectedCategory: string;
  onReload?: () => void;
}) => (
  <div className="text-center py-12 px-4">
    <div className="text-6xl mb-4">🔍</div>
    <h3 className="text-xl font-semibold text-gray-900 mb-3">
      {searchTerm ? 'Không tìm thấy sản phẩm phù hợp' : 'Danh mục trống'}
    </h3>
    <p className="text-gray-600 mb-6 max-w-md mx-auto text-sm leading-relaxed">
      {searchTerm ? (
        <>
          Không tìm thấy sản phẩm nào cho <strong>{searchTerm}</strong>. Thử tìm kiếm với từ khóa khác hoặc điều chỉnh bộ lọc.
        </>
      ) : selectedCategory !== 'all' ? (
        <>
          Danh mục <strong>{selectedCategory}</strong> hiện chưa có sản phẩm. Vui lòng quay lại sau.
        </>
      ) : (
        'Hiện tại không có sản phẩm nào trong kho. Vui lòng kiểm tra lại sau.'
      )}
    </p>
    <div className="flex flex-col sm:flex-row gap-3 justify-center items-center">
      {onReload && (
        <button
          onClick={onReload}
          className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2.5 rounded-lg font-medium transition-colors duration-200 text-sm"
        >
          🔄 Tải lại dữ liệu
        </button>
      )}
      {searchTerm && (
        <button
          onClick={() => window.location.reload()}
          className="border border-gray-300 hover:bg-gray-50 text-gray-700 px-6 py-2.5 rounded-lg font-medium transition-colors duration-200 text-sm"
        >
          📋 Xem tất cả sản phẩm
        </button>
      )}
    </div>
  </div>
);

// Filter Bar Component
const FilterBar = ({ 
  totalProducts, 
  searchTerm,
  selectedCategory,
  onSortChange,
  onPriceFilterChange 
}: {
  totalProducts: number;
  searchTerm: string;
  selectedCategory: string;
  onSortChange: (sort: string) => void;
  onPriceFilterChange: (range: string) => void;
}) => (
  <div className="bg-white border-b border-gray-200 p-4 mb-6 rounded-lg shadow-sm">
    <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
      {/* Results Info */}
      <div className="flex-1">
        <p className="text-sm text-gray-700">
          <span className="font-semibold text-gray-900">{totalProducts}</span> sản phẩm
          {searchTerm && (
            <span>
              {' '}cho &quot;<span className="font-medium text-blue-600">{searchTerm}</span>&quot;
            </span>
          )}
          {selectedCategory !== 'all' && (
            <span>
              {' '}trong danh mục &quot;<span className="font-medium text-green-600">{selectedCategory}</span>&quot;
            </span>
          )}
        </p>
      </div>

      {/* Filter Controls */}
      <div className="flex flex-col sm:flex-row gap-3">
        {/* Sort Select */}
        <div className="flex items-center gap-2">
          <label htmlFor="sort-select" className="text-sm font-medium text-gray-700 whitespace-nowrap">
            Sắp xếp:
          </label>
          <select
            id="sort-select"
            onChange={(e) => onSortChange(e.target.value)}
            className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
            defaultValue="popular"
          >
            <option value="popular">Phổ biến nhất</option>
            <option value="newest">Mới nhất</option>
            <option value="price_asc">Giá: Thấp đến cao</option>
            <option value="price_desc">Giá: Cao đến thấp</option>
            <option value="rating">Đánh giá cao</option>
            <option value="sales">Bán chạy</option>
          </select>
        </div>

        {/* Price Filter */}
        <div className="flex items-center gap-2">
          <label htmlFor="price-filter" className="text-sm font-medium text-gray-700 whitespace-nowrap">
            Khoảng giá:
          </label>
          <select
            id="price-filter"
            onChange={(e) => onPriceFilterChange(e.target.value)}
            className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
            defaultValue="all"
          >
            <option value="all">Tất cả</option>
            <option value="under500k">Dưới 500K</option>
            <option value="500k-1m">500K - 1 Triệu</option>
            <option value="1m-3m">1 - 3 Triệu</option>
            <option value="3m-5m">3 - 5 Triệu</option>
            <option value="over5m">Trên 5 Triệu</option>
          </select>
        </div>
      </div>
    </div>
  </div>
);

// Main ProductGrid Component
export default function ProductGrid({ 
  products, 
  loading, 
  searchTerm = '',
  selectedCategory = 'all',
  onReload,
  showFilters = true
}: ProductGridProps) {
  const { isAuthenticated } = useAuth();
  const [favoriteIds, setFavoriteIds] = useState<Set<number>>(new Set());
  const [sortBy, setSortBy] = useState('popular');
  const [priceRange, setPriceRange] = useState('all');

  useEffect(() => {
    let cancelled = false;
    apiClient
      .getFavorites()
      .then((list) => {
        if (cancelled || !Array.isArray(list)) return;
        const ids = list
          .map((x: { product_id?: number }) => x.product_id)
          .filter((n): n is number => typeof n === 'number');
        setFavoriteIds(new Set(ids));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated]);

  const handleFavorite = async (productId: number, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const product = sortedProducts.find((p) => p.id === productId);
    const had = favoriteIds.has(productId);
    try {
      if (had) {
        await apiClient.removeFromFavorites(productId);
        setFavoriteIds((prev) => {
          const n = new Set(prev);
          n.delete(productId);
          return n;
        });
      } else {
        await apiClient.addToFavorites(
          productId,
          product
            ? {
                name: product.name,
                main_image: product.main_image,
                price: product.price,
                slug: product.slug,
                product_id: product.product_id,
              }
            : undefined
        );
        setFavoriteIds((prev) => new Set(prev).add(productId));
      }
    } catch {
      /* ignore */
    }
  };

  const handleSortChange = (sortType: string) => {
    setSortBy(sortType);
    // Gọi API hoặc filter local data dựa trên sort type
    console.log('Sort changed to:', sortType);
  };

  const handlePriceFilterChange = (range: string) => {
    setPriceRange(range);
    // Gọi API hoặc filter local data dựa trên price range
    console.log('Price filter changed to:', range);
  };

  // Apply local filters (tạm thời - có thể thay bằng API call)
  const filteredProducts = products.filter(product => {
    // Price filter logic
    const price = product.price || 0;
    switch (priceRange) {
      case 'under500k':
        if (price > 500000) return false;
        break;
      case '500k-1m':
        if (price < 500000 || price > 1000000) return false;
        break;
      case '1m-3m':
        if (price < 1000000 || price > 3000000) return false;
        break;
      case '3m-5m':
        if (price < 3000000 || price > 5000000) return false;
        break;
      case 'over5m':
        if (price < 5000000) return false;
        break;
    }
    return true;
  });

  // Apply sorting (tạm thời - có thể thay bằng API call)
  const sortedProducts = [...filteredProducts].sort((a, b) => {
    switch (sortBy) {
      case 'price_asc':
        return (a.price || 0) - (b.price || 0);
      case 'price_desc':
        return (b.price || 0) - (a.price || 0);
      case 'rating':
        return (b.rating_point || 0) - (a.rating_point || 0);
      case 'sales':
        return (b.purchases || 0) - (a.purchases || 0);
      case 'newest':
        return new Date(b.created_at || '').getTime() - new Date(a.created_at || '').getTime();
      case 'popular':
      default:
        return (b.purchases || 0) - (a.purchases || 0);
    }
  });

  if (loading) {
    return <ProductGridSkeleton />;
  }

  if (products.length === 0) {
    return (
      <EmptyState 
        searchTerm={searchTerm}
        selectedCategory={selectedCategory}
        onReload={onReload}
      />
    );
  }

  return (
    <div className="w-full">
      {/* Filter Bar */}
      {showFilters && (
        <FilterBar
          totalProducts={sortedProducts.length}
          searchTerm={searchTerm}
          selectedCategory={selectedCategory}
          onSortChange={handleSortChange}
          onPriceFilterChange={handlePriceFilterChange}
        />
      )}

      {/* Products Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-5">
        {sortedProducts.map((product) => (
          <SimpleProductCard
            key={product.id}
            product={product}
            onFavorite={handleFavorite}
            isFavorited={favoriteIds.has(product.id)}
          />
        ))}
      </div>

      {/* Load More Section */}
      {sortedProducts.length > 0 && (
        <div className="text-center py-10 mt-10">
          <p className="text-sm text-gray-500 mb-4">
            Đang hiển thị {sortedProducts.length} trong tổng số {products.length} sản phẩm
          </p>
          {sortedProducts.length < products.length && (
            <button className="bg-[#ea580c] hover:bg-[#c2410c] text-white px-6 py-2.5 rounded-xl font-medium transition-colors duration-200 text-sm shadow-sm">
              Tải thêm sản phẩm
            </button>
          )}
        </div>
      )}

      {/* No Results after filtering */}
      {sortedProducts.length === 0 && products.length > 0 && (
        <div className="text-center py-12">
          <div className="text-5xl mb-4">😔</div>
          <h3 className="text-lg font-semibold text-gray-900 mb-2">
            Không có sản phẩm phù hợp
          </h3>
          <p className="text-gray-600 mb-6 text-sm">
            Thử điều chỉnh bộ lọc hoặc xóa một số điều kiện để xem nhiều sản phẩm hơn.
          </p>
          <button 
            onClick={() => {
              setSortBy('popular');
              setPriceRange('all');
            }}
            className="bg-[#ea580c] hover:bg-[#c2410c] text-white px-6 py-2.5 rounded-xl font-medium transition-colors duration-200 text-sm shadow-sm"
          >
            Xóa bộ lọc
          </button>
        </div>
      )}
    </div>
  );
}

// Additional utility exports
export { ProductGridSkeleton, EmptyState, FilterBar };
