// frontend/app/products/[slug]/page.tsx - OPTIMIZED VERSION
'use client';

import { useState, useEffect, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { apiClient } from '@/lib/api-client';
import { formatPrice, getDiscountPercentage, validateImageUrl, truncateText } from '@/lib/utils';
import type { Product, SimpleProductResponse } from '@/types/api';
import { useCart } from '@/features/cart/hooks/useCart';

// Import product detail components
import ProductGallery from '@/components/product-detail/ProductGallery';
import ProductInfo from '@/components/product-detail/ProductInfo';
import ProductTabs from '@/components/product-detail/ProductTabs';
import RelatedProducts from '@/components/product-detail/RelatedProducts';

function extractProductIdFromSlug(slug: string): string | null {
  const slugParts = slug.split('-');
  for (const part of slugParts) {
    if ((part.startsWith('A') || part.startsWith('B')) && part.length > 5) {
      return part;
    }
  }
  return null;
}

export default function ProductDetailPage() {
  const params = useParams();
  const router = useRouter();
  const slug = params.slug as string;
  
  const [product, setProduct] = useState<Product | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  const { addToCart } = useCart();

  const fetchProductDetail = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      
      let productData: Product | null = null;

      try {
        productData = await apiClient.getProductBySlug(slug);
      } catch (mainError: any) {
        try {
          const simpleResult: SimpleProductResponse = await apiClient.simple.getProductBySlug(slug);
          if (simpleResult.found && simpleResult.product) {
            productData = simpleResult.product;
          } else if (simpleResult.found && simpleResult.products && simpleResult.products.length > 0) {
            productData = simpleResult.products[0];
          } else {
            throw new Error(simpleResult.message || 'Product not found');
          }
        } catch (simpleError: any) {
          const productId = extractProductIdFromSlug(slug);
          if (productId) {
            productData = await apiClient.getProductByProductId(productId);
          } else {
            throw new Error(`Không tìm thấy sản phẩm với slug: ${slug}`);
          }
        }
      }

      if (productData) {
        setProduct(productData);
        await apiClient.trackProductView(productData.id, {
          id: productData.id,
          product_id: productData.product_id,
          name: productData.name,
          price: productData.price,
          main_image: productData.main_image,
          brand_name: productData.brand_name,
          slug: productData.slug,
        });
      } else {
        throw new Error('Không thể tải thông tin sản phẩm');
      }
      
    } catch (err: any) {
      console.error('Error fetching product:', err);
      setError(err.message || 'Không thể tải thông tin sản phẩm');
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    if (slug) {
      fetchProductDetail();
    }
  }, [slug, retryCount, fetchProductDetail]);

  const handleRetry = () => {
    setRetryCount(prev => prev + 1);
  };

  const handleAddToCart = useCallback(
    async (p: Product, quantity: number, selectedSize?: string, selectedColor?: string) => {
      try {
        await addToCart({
          product_id: p.id,
          quantity,
          selected_size: selectedSize,
          selected_color: selectedColor,
          product_data: {
            id: p.id,
            product_id: p.product_id,
            name: p.name,
            price: p.price,
            main_image: p.main_image,
            brand_name: p.brand_name,
            available: p.available,
            original_price: p.original_price,
          },
        });
      } catch (err: unknown) {
        alert(err instanceof Error ? err.message : 'Không thể thêm vào giỏ hàng');
      }
    },
    [addToCart]
  );

  const handleAddToFavorite = useCallback(
    async (p: Product) => {
      try {
        await apiClient.addToFavorites(p.id, {
          id: p.id,
          product_id: p.product_id,
          name: p.name,
          price: p.price,
          main_image: p.main_image,
          brand_name: p.brand_name,
          slug: p.slug,
        });
      } catch (err: unknown) {
        alert(err instanceof Error ? err.message : 'Không thể thêm yêu thích');
      }
    },
    []
  );

  // Loading state
  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50">
        <div className="max-w-7xl mx-auto px-4 py-8">
          <div className="animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-1/4 mb-4"></div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              <div className="aspect-square bg-gray-200 rounded-lg"></div>
              <div className="space-y-4">
                <div className="h-8 bg-gray-200 rounded w-3/4"></div>
                <div className="h-4 bg-gray-200 rounded w-1/2"></div>
                <div className="h-6 bg-gray-200 rounded w-1/4"></div>
                <div className="h-10 bg-gray-200 rounded w-full"></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Error state
  if (error && !product) {
    return (
      <div className="min-h-screen bg-gray-50">
        <div className="max-w-4xl mx-auto px-4 py-16 text-center">
          <div className="text-6xl mb-4">😢</div>
          <h1 className="text-2xl font-bold text-gray-900 mb-2">Không tìm thấy sản phẩm</h1>
          <p className="text-gray-600 mb-6">{error}</p>
          <div className="space-y-3 max-w-sm mx-auto">
            <button 
              onClick={handleRetry}
              className="block w-full bg-[#ea580c] text-white px-6 py-3 rounded-lg hover:bg-[#c2410c] transition-colors font-medium"
            >
              Thử tải lại
            </button>
            <Link 
              href="/"
              className="block w-full border border-gray-300 text-gray-700 px-6 py-3 rounded-lg hover:bg-gray-50 transition-colors"
            >
              ← Quay lại trang chủ
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (!product) {
    return null;
  }
  const category = product.raw_category ?? product.category;
  const categorySlug = category ? category.toLowerCase().replace(/\s+/g, '-') : '';
  const subcategory = product.raw_subcategory ?? product.subcategory;
  const subcategorySlug = subcategory ? subcategory.toLowerCase().replace(/\s+/g, '-') : '';
  const subSubcategory = product.sub_subcategory;
  const subSubcategorySlug = subSubcategory ? subSubcategory.toLowerCase().replace(/\s+/g, '-') : '';

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Breadcrumb */}
      <nav className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 py-3">
          <div className="flex items-center space-x-2 text-sm text-gray-600">
            <Link href="/" className="hover:text-blue-600 transition-colors">Trang chủ</Link>
            
            {/* Danh mục cấp 1 - Sử dụng raw_category nếu có, nếu không dùng category */}
            {category && (
              <>
                <span>/</span>
                <Link 
                  href={`/danh-muc/${categorySlug}`}
                  className="hover:text-blue-600 transition-colors"
                >
                  {category}
                </Link>
              </>
            )}

            {/* Danh mục cấp 2 - Sử dụng raw_subcategory nếu có, nếu không dùng subcategory */}
            {subcategory && categorySlug && (
              <>
                <span>/</span>
                <Link 
                  href={`/danh-muc/${categorySlug}/${subcategorySlug}`}
                  className="hover:text-blue-600 transition-colors"
                >
                  {subcategory}
                </Link>
              </>
            )}

            {/* Danh mục cấp 3 */}
            {subSubcategory && categorySlug && subcategorySlug && (
              <>
                <span>/</span>
                <Link 
                  href={`/danh-muc/${categorySlug}/${subcategorySlug}/${subSubcategorySlug}`}
                  className="hover:text-blue-600 transition-colors"
                >
                  {subSubcategory}
                </Link>
              </>
            )}

            <span>/</span>
            <span className="text-gray-900 font-medium line-clamp-1">
              {truncateText(product.name, 50)}
            </span>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-4 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-12">
          {/* Product Gallery */}
          <div>
            <ProductGallery product={product} />
          </div>

          {/* Product Info */}
          <div>
            <ProductInfo product={product} onAddToCart={handleAddToCart} onAddToFavorite={handleAddToFavorite} />
          </div>
        </div>

        {/* Product Tabs */}
        <div className="mb-12">
          <ProductTabs product={product} />
        </div>

        {/* Related Products */}
        <div>
          <RelatedProducts currentProduct={product} />
        </div>
      </main>

    </div>
  );
}
