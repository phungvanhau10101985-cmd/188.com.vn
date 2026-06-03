// frontend/components/ProductCard.tsx - FIXED VERSION
'use client';

import Image from 'next/image';
import Link from 'next/link';
import { useMemo, useState } from 'react';
import { Product } from '@/types/api';
import { formatPrice, getDiscountPercentage, truncateText } from '@/lib/utils';
import { getOptimizedImage } from '@/lib/image-utils';
import { hasVideoLink } from '@/lib/video-utils';
import { productPathSlugFromApi } from '@/lib/product-path-slug';
import { useBirthdayDiscount } from '@/lib/use-birthday-discount';
import { BirthdayPromoImageBadge, BirthdayPromoPriceCakeIcon } from '@/components/BirthdayPromoProductMarkers';
import SiteSaleProductBadge from '@/components/SiteSaleProductBadge';
import SiteSaleCountdownChip from '@/components/SiteSaleCountdownChip';
import ProductCardClearanceMeta from '@/components/ProductCardClearanceMeta';
import ProductCardClearanceImageBadges from '@/components/ProductCardClearanceImageBadges';
import { mergeProductSiteSaleFromCalendar, resolveProductDisplayPricing } from '@/lib/site-sale';
import { useSiteSale } from '@/lib/use-site-sale';
import {
  getClearanceCardHero,
  productShowsClearanceOnCard,
  warehouseStandaloneSaleImage,
} from '@/lib/warehouse-clearance';

type ResolvedProductPricing = ReturnType<typeof resolveProductDisplayPricing>;

function getProductCardPromoDisplay(
  pricing: ResolvedProductPricing,
  displayPrice: number,
  birthdayActive: boolean,
) {
  if (birthdayActive) {
    return {
      showOriginal: false,
      showSavingsLine: false,
      showTeaserLine: false,
      originalPrice: null as number | null,
      savings: 0,
      expectedPrice: null as number | null,
    };
  }

  const isActive = pricing.sitePhase === 'active' && pricing.sitePercent > 0;
  const isTeaser = pricing.sitePhase === 'teaser' && pricing.sitePercent > 0;
  const originalPrice =
    pricing.compareUnitPrice != null && pricing.compareUnitPrice > displayPrice
      ? pricing.compareUnitPrice
      : isActive && pricing.listPrice > displayPrice
        ? pricing.listPrice
        : null;
  const savings = isActive
    ? Math.max(
        0,
        originalPrice != null
          ? originalPrice - displayPrice
          : pricing.siteSavings || pricing.savingsAmount,
      )
    : isTeaser
      ? Math.max(
          0,
          pricing.siteSavings ||
            pricing.savingsAmount ||
            Math.round(displayPrice * pricing.sitePercent / 100),
        )
      : 0;
  const expectedPrice =
    isTeaser && pricing.expectedSalePrice != null && pricing.expectedSalePrice > 0
      ? pricing.expectedSalePrice
      : isTeaser && savings > 0
        ? Math.max(0, displayPrice - savings)
        : null;

  return {
    showOriginal: isActive && originalPrice != null && originalPrice > displayPrice,
    showSavingsLine: isActive && savings > 0,
    showTeaserLine: isTeaser && savings > 0,
    originalPrice,
    savings,
    expectedPrice,
  };
}

function ProductCardPricePromo({
  pricing,
  displayPrice,
  birthdayActive,
  birthdayPercent,
  productListPrice,
  priceClassName,
  strikeClassName = 'text-[10px] text-gray-500 line-through decoration-1 decoration-gray-400',
  savingsClassName = 'text-[10px] font-medium text-emerald-600',
  teaserClassName = 'text-[10px] font-medium text-amber-700',
}: {
  pricing: ResolvedProductPricing;
  displayPrice: number;
  birthdayActive: boolean;
  birthdayPercent: number;
  productListPrice?: number;
  priceClassName: string;
  strikeClassName?: string;
  savingsClassName?: string;
  teaserClassName?: string;
}) {
  const promo = getProductCardPromoDisplay(pricing, displayPrice, birthdayActive);

  return (
    <div className="space-y-0.5">
      <div className="flex flex-wrap items-baseline gap-x-1 gap-y-0">
        <span className={priceClassName}>{formatPrice(displayPrice)}</span>
        <BirthdayPromoPriceCakeIcon active={birthdayActive} percent={birthdayPercent} />
        {birthdayActive && displayPrice < (productListPrice || 0) ? (
          <span className={strikeClassName}>{formatPrice(productListPrice || 0)}</span>
        ) : null}
        {promo.showOriginal ? (
          <span className={strikeClassName}>{formatPrice(promo.originalPrice!)}</span>
        ) : null}
        {promo.showTeaserLine && promo.expectedPrice != null ? (
          <span className="text-[10px] font-semibold text-emerald-700">
            → {formatPrice(promo.expectedPrice)}
          </span>
        ) : null}
      </div>
      {promo.showSavingsLine ? (
        <p className={savingsClassName}>Tiết kiệm {formatPrice(promo.savings)}</p>
      ) : null}
      {promo.showTeaserLine ? (
        <p className={teaserClassName}>
          Sắp giảm {pricing.sitePercent}% — tiết kiệm ~{formatPrice(promo.savings)}
        </p>
      ) : null}
    </div>
  );
}

function useProductCardPricing(product: Product) {
  const birthdayDiscount = useBirthdayDiscount();
  const { state: siteSaleState } = useSiteSale();
  const productForPricing = mergeProductSiteSaleFromCalendar(product, siteSaleState);
  const pricing = resolveProductDisplayPricing(
    productForPricing,
    birthdayDiscount.active,
    birthdayDiscount.percent,
  );
  return { pricing, displayPrice: pricing.displayPrice, birthdayDiscount };
}

function ProductVideoBadge({ videoLink }: { videoLink?: string | null }) {
  if (!hasVideoLink(videoLink)) return null;
  return (
    <div
      className="absolute bottom-2 left-2 z-[1] flex h-7 w-7 items-center justify-center rounded-full bg-black/55 text-white shadow-md ring-1 ring-white/35 pointer-events-none"
      title="Có video"
    >
      <span className="sr-only">Sản phẩm có video</span>
      <svg className="h-3.5 w-3.5 translate-x-[1px]" fill="currentColor" viewBox="0 0 24 24" aria-hidden>
        <path d="M8 5v14l11-7z" />
      </svg>
    </div>
  );
}

function PersonalizedCohortImageBadge() {
  return (
    <div
      className="pointer-events-none absolute left-2 top-2 z-[2] max-w-[calc(100%-3rem)] rounded-md bg-[#ea580c] px-1.5 py-0.5 text-[9px] font-semibold leading-tight text-white shadow-md sm:text-[10px]"
      aria-hidden
    >
      Đề xuất
    </div>
  );
}

interface ProductCardProps {
  product: Product;
  onAddToCart?: (product: Product) => void;
  onAddToFavorite?: (product: Product) => void;
  onQuickView?: (product: Product) => void;
  size?: 'small' | 'medium' | 'large';
}

// Helper functions - ĐƯA LÊN ĐẦU ĐỂ TRÁNH LỖI HOISTING
const getImageSize = (size: string) => {
  switch (size) {
    case 'small':
      return { width: 200, height: 200 };
    case 'large':
      return { width: 400, height: 400 };
    case 'medium':
    default:
      return { width: 300, height: 300 };
  }
};

// CSS classes theo size
const getSizeClasses = (size: string) => {
  switch (size) {
    case 'small':
      return {
        container: 'p-2',
        image: 'aspect-square',
        name: 'text-xs min-h-[1.5rem]',
        price: 'text-sm',
        button: 'py-1 px-2 text-xs'
      };
    case 'large':
      return {
        container: 'p-4',
        image: 'aspect-square',
        name: 'text-base min-h-[2.5rem]',
        price: 'text-lg',
        button: 'py-3 px-4 text-base'
      };
    case 'medium':
    default:
      return {
        container: 'p-3',
        image: 'aspect-square',
        name: 'text-sm min-h-[2rem]',
        price: 'text-base',
        button: 'py-2 px-3 text-sm'
      };
  }
};

export default function ProductCard({ 
  product, 
  onAddToCart, 
  onAddToFavorite, 
  onQuickView,
  size = 'medium'
}: ProductCardProps) {
  const [imageError, setImageError] = useState(false);
  const [imageLoading, setImageLoading] = useState(true);
  
  const available = (product.available || 0) > 0;
  const { pricing, displayPrice, birthdayDiscount } = useProductCardPricing(product);
  const clearanceHero = useMemo(() => getClearanceCardHero(product), [product]);
  const showsClearance = productShowsClearanceOnCard(product);
  const hasDiscount =
    !showsClearance &&
    ((pricing.compareAt != null && pricing.compareAt > displayPrice) ||
      (product.original_price != null && product.original_price > product.price));
  
  // Sử dụng image utils với kích thước tối ưu — ảnh màu thanh lý thay ảnh đại diện khi có kho sale
  const cardImageSource =
    clearanceHero?.imageUrl || warehouseStandaloneSaleImage(product) || product.main_image;
  const imageUrl = getOptimizedImage(cardImageSource, {
    width: getImageSize(size).width,
    height: getImageSize(size).height,
    quality: 85,
    fallbackStrategy: 'local'
  });

  // Tạo blur placeholder từ image utils
  const blurDataUrl = getOptimizedImage(undefined, { 
    width: 20, 
    height: 20 
  });

  const handleImageError = () => {
    setImageError(true);
    setImageLoading(false);
  };

  const handleImageLoad = () => {
    setImageLoading(false);
  };

  const handleAddToCart = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onAddToCart?.(product);
  };

  const handleAddToFavorite = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onAddToFavorite?.(product);
  };

  const handleQuickView = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onQuickView?.(product);
  };

  const sizeClasses = getSizeClasses(size);

  const productSlug =
    productPathSlugFromApi(product.slug, product.product_id) ||
    product.product_id ||
    (product.id != null ? String(product.id) : '');
  const productHref = productSlug ? `/products/${productSlug}` : '#';

  return (
    <div className={`product-card group bg-white rounded-xl border border-gray-100 shadow-sm hover:shadow-lg hover:border-orange-200 overflow-hidden ${sizeClasses.container}`}>
      {/* Image Section */}
      <div
        className={`relative overflow-hidden bg-gray-50 rounded-t-xl ${sizeClasses.image} ${
          showsClearance ? 'ring-2 ring-inset ring-amber-400/70' : ''
        }`}
      >
        <Link href={productHref}>
          {!imageError ? (
            <>
              {imageLoading && (
                <div className="absolute inset-0 bg-gray-200 animate-pulse flex items-center justify-center">
                  <div className="text-gray-400 text-xs">Đang tải...</div>
                </div>
              )}
              <Image
                src={imageUrl}
                alt={product.name}
                fill
                className={`object-cover group-hover:scale-105 transition-transform duration-300 ${
                  imageLoading ? 'opacity-0' : 'opacity-100'
                }`}
                onError={handleImageError}
                onLoad={handleImageLoad}
                sizes="(max-width: 768px) 50vw, (max-width: 1200px) 33vw, 25vw"
                placeholder="blur"
                blurDataURL={blurDataUrl}
                priority={false}
              />
            </>
          ) : (
            <div className="w-full h-full flex items-center justify-center bg-gray-200">
              <div className="text-center text-gray-500">
                <div className="text-xl mb-1">📦</div>
                <div className="text-xs">Không có hình ảnh</div>
              </div>
            </div>
          )}
        </Link>

        {/* Discount Badge */}
        {!imageError && (
          <>
            <ProductCardClearanceImageBadges
              product={product}
              compact={size === 'small'}
            />
            <SiteSaleProductBadge siteSale={product.site_sale} />
            <SiteSaleCountdownChip siteSale={product.site_sale} />
            <BirthdayPromoImageBadge active={birthdayDiscount.active} percent={birthdayDiscount.percent} />
          </>
        )}
        {hasDiscount && !imageError && !birthdayDiscount.active && !product.site_sale?.phase ? (
          <div className="absolute top-2 left-2 bg-red-500 text-white px-1.5 py-0.5 rounded-full text-xs font-bold shadow-md">
            -{getDiscountPercentage(product.original_price!, product.price)}%
          </div>
        ) : null}

        {!imageError && <ProductVideoBadge videoLink={product.video_link} />}

        {/* Action Buttons */}
        <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity duration-300 space-y-1">
          <button
            onClick={handleQuickView}
            className="bg-white p-1.5 rounded-full shadow-md hover:bg-gray-50 transition-colors hover:scale-110 transform text-xs"
            title="Xem nhanh"
          >
            👁️
          </button>
          <button
            onClick={handleAddToFavorite}
            className="bg-white p-1.5 rounded-full shadow-md hover:bg-gray-50 transition-colors hover:scale-110 transform text-xs"
            title="Thêm vào yêu thích"
          >
            ❤️
          </button>
        </div>

        {/* Out of Stock Overlay */}
        {!available && (
          <div className="absolute inset-0 bg-black bg-opacity-40 flex items-center justify-center">
            <span className="bg-white px-2 py-1 rounded text-xs font-medium text-gray-900">
              Hết hàng
            </span>
          </div>
        )}
      </div>

      {/* Product Info */}
      <div className="space-y-2">
        {/* Brand */}
        {product.brand_name && (
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded">
              {truncateText(product.brand_name, 12)}
            </span>
            <div className="flex items-center text-xs text-gray-500">
              <span className="text-yellow-400">★</span>
              <span className="mx-0.5">{product.rating_point || 0}</span>
              <span>({product.rating_total || 0})</span>
            </div>
          </div>
        )}

        {/* Product Name */}
        <Link href={productHref}>
          <h3 className={`font-medium text-gray-900 leading-tight line-clamp-2 hover:text-orange-500 transition-colors cursor-pointer ${sizeClasses.name}`}>
            {truncateText(product.name, size === 'small' ? 40 : 50)}
          </h3>
        </Link>

        {/* Price */}
        <div className="space-y-1">
          {pricing.sitePhase && pricing.sitePercent > 0 && !birthdayDiscount.active ? (
            <ProductCardPricePromo
              pricing={pricing}
              displayPrice={displayPrice}
              birthdayActive={birthdayDiscount.active}
              birthdayPercent={birthdayDiscount.percent}
              productListPrice={product.price}
              priceClassName={`font-bold text-red-600 ${sizeClasses.price}`}
              strikeClassName="text-xs text-gray-500 line-through decoration-1 decoration-gray-400"
              savingsClassName="text-xs font-medium text-emerald-600"
              teaserClassName="text-xs text-amber-700"
            />
          ) : (
            <div className="flex flex-wrap items-baseline gap-x-1 gap-y-0">
              <span className={`font-bold text-red-600 ${sizeClasses.price}`}>
                {formatPrice(displayPrice)}
              </span>
              <BirthdayPromoPriceCakeIcon active={birthdayDiscount.active} percent={birthdayDiscount.percent} />
              {birthdayDiscount.active && displayPrice < (product.price || 0) && (
                <span className="text-xs text-gray-500 line-through decoration-1 decoration-gray-400">
                  {formatPrice(product.price)}
                </span>
              )}
              {pricing.compareAt != null && pricing.compareAt > displayPrice && !birthdayDiscount.active && (
                <span className="text-xs text-gray-500 line-through">
                  {formatPrice(pricing.compareAt)}
                </span>
              )}
              {hasDiscount && pricing.compareAt == null && !birthdayDiscount.active && !product.site_sale?.phase && (
                <span className="text-xs text-gray-500 line-through">
                  {formatPrice(product.original_price!)}
                </span>
              )}
            </div>
          )}
          
          {/* Installment */}
          {displayPrice && displayPrice > 1000000 && (
            <div className="text-xs text-green-600 font-medium">
              Trả góp 0% • {formatPrice(displayPrice / 6)}/tháng
            </div>
          )}
        </div>

        <ProductCardClearanceMeta
          product={product}
          compact={size === 'small'}
          className={size === 'small' ? 'mt-1' : 'mt-1.5'}
        />

        {/* Stats */}
        <div className="flex justify-between items-center text-xs text-gray-500">
          <span>Đã bán: {product.purchases || 0}</span>
          <span
            className={`font-medium ${
              available || productShowsClearanceOnCard(product) ? 'text-green-600' : 'text-red-600'
            }`}
          >
            {available || productShowsClearanceOnCard(product) ? 'Còn hàng' : 'Hết hàng'}
          </span>
        </div>

        {/* Add to Cart Button - nút phụ màu xám (theme 188) */}
        <button 
          onClick={handleAddToCart}
          disabled={!available}
          className={`w-full rounded font-medium transition-all flex items-center justify-center space-x-1 ${
            available 
              ? 'bg-gray-500 hover:bg-gray-600 text-white shadow-sm hover:shadow-md' 
              : 'bg-gray-300 text-gray-500 cursor-not-allowed'
          } ${sizeClasses.button}`}
        >
          <span>🛒</span>
          <span>{available ? 'Thêm vào giỏ' : 'Hết hàng'}</span>
        </button>
      </div>
    </div>
  );
}

// Optimized Product Card cho ProductGrid (không có quick actions)
export const SimpleProductCard = ({ 
  product, 
  onFavorite,
  isFavorited = false,
  /** Badge góc ảnh — SP gợi ý theo tuổi/giới tính trong lưới trộn. */
  showPersonalizedBadge = false,
  /** Ưu tiên tải ảnh đầu trang — cải thiện LCP (PSI) */
  priority = false,
}: { 
  product: Product;
  onFavorite: (productId: number, e: React.MouseEvent) => void | Promise<void>;
  /** Trạng thái thích từ server (khách + đăng nhập); mặc định false */
  isFavorited?: boolean;
  showPersonalizedBadge?: boolean;
  priority?: boolean;
}) => {
  const [imageError, setImageError] = useState(false);
  const { pricing, displayPrice, birthdayDiscount } = useProductCardPricing(product);
  const clearanceHero = useMemo(() => getClearanceCardHero(product), [product]);
  const showsClearance = productShowsClearanceOnCard(product);
  const cardImageSource =
    clearanceHero?.imageUrl || warehouseStandaloneSaleImage(product) || product.main_image;

  const imageUrl = getOptimizedImage(cardImageSource, {
    width: 250,
    height: 250,
    quality: 80,
    fallbackStrategy: 'local'
  });
  const blurDataUrl = getOptimizedImage(undefined, { width: 20, height: 20 });

  const handleFavorite = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    void onFavorite(product.id, e);
  };

  const handleImageError = () => {
    setImageError(true);
  };

  const pathSlug = productPathSlugFromApi(product.slug, product.product_id) || product.product_id;
  const stackedPromoBadgeClass = showPersonalizedBadge ? '!top-8' : '';

  return (
    <Link 
      href={pathSlug ? `/products/${pathSlug}` : `/products/${product.id}`}
      className="product-card group bg-white rounded-xl border border-gray-100 shadow-sm hover:shadow-lg hover:border-orange-200 overflow-hidden transition-all block"
    >
      {/* Image Container */}
      <div
        className={`relative aspect-square bg-gray-50 overflow-hidden rounded-t-xl ${
          showsClearance ? 'ring-2 ring-inset ring-amber-400/70' : ''
        }`}
      >
        {!imageError ? (
          <Image
            src={imageUrl}
            alt={product.name}
            fill
            className="object-cover group-hover:scale-105 transition-transform duration-300"
            onError={handleImageError}
            sizes="(max-width: 768px) 50vw, 25vw"
            priority={priority}
            fetchPriority={priority ? 'high' : undefined}
            placeholder="blur"
            blurDataURL={blurDataUrl}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center bg-gray-200">
            <span className="text-gray-400 text-xs">No Image</span>
          </div>
        )}

        {!imageError && (
          <>
            <ProductCardClearanceImageBadges product={product} compact />
            {showPersonalizedBadge ? <PersonalizedCohortImageBadge /> : null}
            <SiteSaleProductBadge siteSale={product.site_sale} className={stackedPromoBadgeClass} />
            <SiteSaleCountdownChip siteSale={product.site_sale} />
            <BirthdayPromoImageBadge
              active={birthdayDiscount.active}
              percent={birthdayDiscount.percent}
              className={stackedPromoBadgeClass}
            />
          </>
        )}

        {/* Favorite Button */}
        <button
          type="button"
          onClick={handleFavorite}
          className={`absolute top-1 right-1 min-w-[44px] min-h-[44px] w-11 h-11 -mt-1 -mr-1 rounded-full flex items-center justify-center text-xs transition-all z-[2] ${
            isFavorited
              ? 'bg-red-500 text-white shadow'
              : 'bg-white bg-opacity-90 text-gray-600 hover:bg-red-500 hover:text-white'
          }`}
          aria-label={isFavorited ? 'Bỏ yêu thích' : 'Thêm yêu thích'}
        >
          {isFavorited ? '❤️' : '🤍'}
        </button>

        {!imageError && <ProductVideoBadge videoLink={product.video_link} />}
      </div>

      {/* Product Info */}
      <div className="p-2">
        {/* Product Name */}
        <h3 className="font-medium text-gray-900 text-xs mb-1 line-clamp-2 leading-tight group-hover:text-orange-600 transition-colors min-h-[2rem]">
          {truncateText(product.name, 45)}
        </h3>

        {/* Price */}
        {pricing.sitePhase && pricing.sitePercent > 0 && !birthdayDiscount.active ? (
          <div className="mb-1">
            <ProductCardPricePromo
              pricing={pricing}
              displayPrice={displayPrice}
              birthdayActive={birthdayDiscount.active}
              birthdayPercent={birthdayDiscount.percent}
              productListPrice={product.price}
              priceClassName="text-sm font-bold text-gray-900"
            />
          </div>
        ) : (
          <div className="mb-1 flex flex-wrap items-baseline gap-x-1 gap-y-0">
            <span className="text-sm font-bold text-gray-900">{formatPrice(displayPrice)}</span>
            <BirthdayPromoPriceCakeIcon active={birthdayDiscount.active} percent={birthdayDiscount.percent} />
            {birthdayDiscount.active && displayPrice < (product.price || 0) && (
              <span className="text-[10px] text-gray-500 line-through decoration-1 decoration-gray-400">
                {formatPrice(product.price)}
              </span>
            )}
          </div>
        )}

        <ProductCardClearanceMeta product={product} compact className="mb-1.5" />

        {/* Stats */}
        <div className="flex justify-between items-center text-xs text-gray-500">
          <span>★ {product.rating_point?.toFixed(1) || '0.0'}</span>
          <span>Đã bán: {product.purchases || 0}</span>
        </div>
      </div>
    </Link>
  );
};