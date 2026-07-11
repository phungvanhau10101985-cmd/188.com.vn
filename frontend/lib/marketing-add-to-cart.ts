import type { AddToCartRequest } from '@/features/cart/types/cart';
import type { Product } from '@/types/api';
import { cartLineMainImage } from '@/lib/product-color-variant';
import { warehouseCartProductDataExtras } from '@/lib/warehouse-clearance';
import { trackMetaAddToCart } from '@/lib/meta-pixel';
import { trackGoogleAdsAddToCart } from '@/lib/google-ads-gtag';

/** Payload giỏ hàng + trường Meta/Google remarketing (id sheet, SKU, giá, tên). */
export function buildAddToCartRequestFromProduct(
  p: Product,
  quantity: number,
  selectedSize?: string,
  selectedColor?: string,
  extra?: Partial<Omit<AddToCartRequest, 'product_id' | 'quantity' | 'selected_size' | 'selected_color'>>
): AddToCartRequest {
  const lineImg = cartLineMainImage(p, selectedColor);
  return {
    product_id: p.id,
    quantity,
    selected_size: selectedSize,
    selected_color: selectedColor,
    line_image_url: lineImg,
    ...extra,
    product_data: {
      id: p.id,
      code: p.code,
      product_id: p.product_id,
      name: p.name,
      price: p.price,
      list_price:
        p.original_price != null && p.original_price > (p.price ?? 0) ? p.original_price : p.price,
      main_image: lineImg,
      brand_name: p.brand_name,
      available: p.available,
      original_price: p.original_price,
      slug: p.slug,
      ...warehouseCartProductDataExtras(p),
    },
  };
}

/** Pixel + CAPI Meta (+ Google Ads) khi khách xác nhận thêm giỏ — không chờ API / login. */
export function trackMarketingAddToCartIntent(item: AddToCartRequest): void {
  trackMetaAddToCart(item);
  trackGoogleAdsAddToCart(item);
}
