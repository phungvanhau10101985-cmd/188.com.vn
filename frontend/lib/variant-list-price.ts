import type { Product, ProductColor } from '@/types/api';
import { colorLabelForCart } from '@/lib/product-color-variant';
import { productShowsClearanceOnCard } from '@/lib/warehouse-clearance';

type PricedColor = ProductColor & { price?: number; price_cny?: number; sku_code?: string };

type VariantPair = {
  color?: string;
  size?: string;
  price?: number;
  price_cny?: number;
  sku_code?: string;
};

function positive(raw: unknown): number | null {
  const n = typeof raw === 'number' ? raw : Number(raw);
  if (!Number.isFinite(n) || n <= 0) return null;
  return n;
}

function variantPairs(product: { product_info?: unknown }): VariantPair[] {
  const info = product.product_info;
  if (!info || typeof info !== 'object') return [];
  const variants = (info as { variants?: { pairs?: unknown; price_pairs?: unknown } }).variants;
  const raw = Array.isArray(variants?.pairs) && variants.pairs.length
    ? variants.pairs
    : variants?.price_pairs;
  if (!Array.isArray(raw)) return [];
  return raw.filter((row) => row && typeof row === 'object') as VariantPair[];
}

/** Giá bán đã lưu của đúng màu, hoặc của cặp màu + size nếu có. */
export function variantListPrice(
  product: Product,
  colorIndex: number,
  size?: string | null,
): number | null {
  const colors = (product.colors || []) as PricedColor[];
  const color = colorIndex >= 0 ? colors[colorIndex] : undefined;
  const sizeName = (size || '').trim();
  if (color && sizeName) {
    const label = colorLabelForCart(colors, colorIndex);
    const name = (color.name || '').trim();
    const hit = variantPairs(product).find((pair) => {
      const pairSize = (pair.size || '').trim();
      const pairColor = (pair.color || '').trim();
      if (pairSize !== sizeName) return false;
      return pairColor === label || pairColor === name;
    });
    const pairPrice = positive(hit?.price);
    if (pairPrice != null) return pairPrice;
  }
  return positive(color?.price);
}

/** Gắn giá mã đang chọn làm giá catalog trước khi áp sale. Cùng giá thì giữ nguyên. */
export function productPricedForVariant(
  product: Product,
  colorIndex: number,
  size?: string | null,
): Product {
  const list = variantListPrice(product, colorIndex, size);
  if (list == null) return product;
  const current = Number(product.price || 0);
  if (Math.abs(list - current) < 1) return product;
  return {
    ...product,
    price: list,
    original_price: undefined,
    site_sale: undefined,
    flash_sale: undefined,
  };
}

type VariantPriceSource = {
  colors?: Array<{ price?: number | string | null }> | null;
  product_info?: unknown;
  is_warehouse_clearance?: boolean | null;
  product_id?: string | null;
  warehouse_variants?: Product['warehouse_variants'];
  warehouse_clearance?: Product['warehouse_clearance'];
  main_image?: string | null;
};

/** Nhiều mã khác giá — thẻ và trang chưa chọn mã hiện «từ». */
export function productHasTieredVariantPrices(product: VariantPriceSource): boolean {
  const values: number[] = [];
  for (const color of (product.colors || []) as PricedColor[]) {
    const price = positive(color.price);
    if (price != null) values.push(price);
  }
  for (const pair of variantPairs(product)) {
    const price = positive(pair.price);
    if (price != null) values.push(price);
  }
  if (values.length < 2) return false;
  return Math.max(...values) - Math.min(...values) >= 1;
}

/** «từ» khi các mã khác giá. Hàng thanh lý giữ giá kho, không thêm chữ này. */
export function listingPricePrefix(product: VariantPriceSource): '' | 'từ' {
  if (productShowsClearanceOnCard(product as Product)) return '';
  return productHasTieredVariantPrices(product) ? 'từ' : '';
}
