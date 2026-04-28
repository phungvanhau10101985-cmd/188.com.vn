import { cdnUrl } from '@/lib/cdn-url';
import type { Product } from '@/types/api';

interface ProductCardProps {
  product: Product;
  onAddToCart?: (product: Product) => void;
  onProductClick?: (product: Product) => void;
}

export default function ProductCard({ product, onAddToCart, onProductClick }: ProductCardProps) {
  // Xử lý image URL từ backend
  const getImageUrl = () => {
    if (!product.main_image) return cdnUrl('/images/placeholder-product.jpg');
    
    if (product.main_image.startsWith('//')) {
      return `https:${product.main_image}`;
    }
    
    return product.main_image;
  };

  // Format price
  const formatPrice = (price: number) => {
    return new Intl.NumberFormat('vi-VN').format(price) + '₫';
  };

  // Handle product click
  const handleProductClick = () => {
    onProductClick?.(product);
  };

  // Handle add to cart
  const handleAddToCart = (e: React.MouseEvent) => {
    e.stopPropagation();
    onAddToCart?.(product);
  };

  return (
    <div 
      className="bg-white rounded-lg shadow-md hover:shadow-lg transition-all duration-300 border border-gray-200 overflow-hidden cursor-pointer"
      onClick={handleProductClick}
    >
      {/* Product Image */}
      <div className="relative">
        <img 
          src={getImageUrl()} 
          alt={product.name}
          className="w-full h-48 object-cover"
          onError={(e) => {
            e.currentTarget.src = cdnUrl('/images/placeholder-product.jpg');
          }}
        />
        
        {/* Stock Status Badge */}
        <div className="absolute top-2 right-2">
          <span className={`px-2 py-1 rounded text-xs font-medium ${
            (product.available ?? 0) > 0
              ? 'bg-green-500 text-white' 
              : 'bg-red-500 text-white'
          }`}>
            {(product.available ?? 0) > 0 ? 'Còn hàng' : 'Hết hàng'}
          </span>
        </div>
      </div>

      {/* Product Info */}
      <div className="p-4">
        {/* Product Name */}
        <h3 className="font-semibold text-gray-800 line-clamp-2 mb-2 min-h-[3rem]">
          {product.name}
        </h3>

        {/* Brand */}
        {product.brand_name && (
          <p className="text-gray-600 text-sm mb-2">Thương hiệu: {product.brand_name}</p>
        )}

        {/* Description */}
        {product.product_description && (
          <p className="text-gray-600 text-sm line-clamp-2 mb-3">
            {product.product_description}
          </p>
        )}

        {/* Pricing */}
        <div className="flex items-center gap-2 mb-3">
          <span className="text-red-600 font-bold text-lg">
            {formatPrice(product.price)}
          </span>
          
          {/* Original Price */}
          {product.original_price && product.original_price > product.price && (
            <span className="text-gray-500 line-through text-sm">
              {formatPrice(product.original_price)}
            </span>
          )}
        </div>

        {/* Rating & Stats */}
        <div className="flex items-center justify-between mb-3 text-sm text-gray-500">
          <div className="flex items-center gap-1">
            {product.rating_point ? (
              <>
                ⭐ {product.rating_point}
                <span className="text-gray-400">•</span>
              </>
            ) : null}
            {product.purchases ? (
              <span>Đã bán {product.purchases}</span>
            ) : null}
          </div>
          
          {product.likes && (
            <span>❤️ {product.likes}</span>
          )}
        </div>

        {/* Add to Cart Button */}
        <button
          onClick={handleAddToCart}
          disabled={(product.available ?? 0) === 0}
          className={`w-full py-2 px-4 rounded-lg font-medium transition-colors ${
            (product.available ?? 0) > 0
              ? 'bg-orange-500 hover:bg-orange-600 text-white'
              : 'bg-gray-300 text-gray-500 cursor-not-allowed'
          }`}
        >
          {(product.available ?? 0) > 0 ? 'Thêm vào giỏ' : 'Hết hàng'}
        </button>
      </div>
    </div>
  );
}
