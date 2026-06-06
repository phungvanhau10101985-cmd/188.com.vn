import type { Product, WarehouseClearanceVariant, WarehouseVariantPricing } from '@/types/api';
import { productPathSlugFromApi } from '@/lib/product-path-slug';

/** Giá sale kho: ưu tiên API; nếu thiếu thì tính từ list_price + % admin. */
export function resolveWarehouseVariantPricing(
  variant: WarehouseClearanceVariant,
  fallbackDiscountPercent = 0,
): WarehouseVariantPricing {
  const listPrice = Math.max(
    0,
    Number(variant.list_price ?? variant.original_price ?? variant.display_price ?? 0),
  );
  const apiDisplay = Math.max(0, Number(variant.display_price ?? listPrice));
  const apiOriginal = Math.max(0, Number(variant.original_price ?? listPrice));
  const pct = Math.max(
    0,
    Math.min(
      100,
      Number(variant.clearance_percent > 0 ? variant.clearance_percent : fallbackDiscountPercent),
    ),
  );

  let displayPrice = apiDisplay;
  let originalPrice = apiOriginal > 0 ? apiOriginal : listPrice;

  if (pct > 0 && listPrice > 0 && (displayPrice >= originalPrice || (variant.savings_amount ?? 0) <= 0)) {
    displayPrice = Math.max(0, Math.round(listPrice * (1 - pct / 100)));
    originalPrice = listPrice;
  }

  const hasDiscount = originalPrice > displayPrice && displayPrice > 0;
  const savingsAmount = hasDiscount ? Math.max(0, originalPrice - displayPrice) : 0;
  return { displayPrice, originalPrice, listPrice, percent: pct, hasDiscount, savingsAmount };
}

/** Gộp SP gốc + dòng kho để add-to-cart với đúng product_id DB kho. */
export function warehouseVariantAsProduct(
  parent: Product,
  variant: WarehouseClearanceVariant,
): Product {
  const fallbackPct = parent.warehouse_clearance?.discount_percent ?? 0;
  const pricing = resolveWarehouseVariantPricing(variant, fallbackPct);
  const lineImage =
    (variant.color_image || variant.main_image || '').trim() ||
    (parent.main_image || '').trim() ||
    undefined;
  const colorName = (variant.color || '').trim() || 'Như ảnh';
  const colorEntry = lineImage
    ? { name: colorName, value: colorName, img: lineImage }
    : { name: colorName, value: colorName };

  return {
    ...parent,
    id: variant.id,
    product_id: variant.product_id,
    price: pricing.displayPrice,
    original_price: pricing.hasDiscount ? pricing.originalPrice : undefined,
    available: variant.available,
    main_image: lineImage || parent.main_image,
    sizes: variant.size ? [variant.size] : [],
    colors: [colorEntry],
    site_sale: undefined,
  };
}

export function warehouseVariantsInStock(product: Product): WarehouseClearanceVariant[] {
  return (product.warehouse_variants ?? []).filter((v) => (v.available ?? 0) > 0);
}

export function isWarehouseClearanceProductId(productId?: string | null): boolean {
  return String(productId || '').includes('/');
}

export function isWarehouseClearanceProduct(product: Product): boolean {
  if (product.is_warehouse_clearance) return true;
  return isWarehouseClearanceProductId(product.product_id);
}

export function warehouseVariantThumbUrl(variant: WarehouseClearanceVariant): string | null {
  const raw = (variant.color_image || variant.main_image || '').trim();
  return raw || null;
}

/** Ảnh màu dòng kho đơn (listing /kho-sale) — không dùng ảnh SP gốc nếu có ảnh variant. */
export function warehouseStandaloneSaleImage(product: Product): string | null {
  const rawColor = product.colors?.[0];
  if (typeof rawColor === 'object' && rawColor != null) {
    const img = String(
      (rawColor as { img?: string; image?: string }).img ||
        (rawColor as { image?: string }).image ||
        '',
    ).trim();
    if (img) return img;
  }
  const urls = product.color_image_urls;
  if (Array.isArray(urls)) {
    for (const u of urls) {
      const s = String(u || '').trim();
      if (s) return s;
    }
  }
  return String(product.main_image || '').trim() || null;
}

/** Size từ cột sizes hoặc mã dòng kho (HN256/XL/2 → XL). */
export function warehouseStandaloneSize(product: Product): string | null {
  const fromSizes = product.sizes?.[0];
  if (fromSizes != null && String(fromSizes).trim()) {
    return String(fromSizes).trim();
  }
  const pid = String(product.product_id || '').trim();
  if (!pid.includes('/')) return null;
  const parts = pid.split('/').map((p) => p.trim()).filter(Boolean);
  if (parts.length < 2) return null;
  const seg = parts[1];
  return seg || null;
}

function clearanceLineFromStandaloneProduct(product: Product): ClearanceCardLine {
  const fallbackPct = product.warehouse_clearance?.discount_percent ?? 0;
  const thumbUrl = warehouseStandaloneSaleImage(product);
  const size = warehouseStandaloneSize(product);
  const displayPrice = Math.max(0, Number(product.price ?? 0));
  const apiOriginal = product.original_price;
  const originalPrice =
    apiOriginal != null && apiOriginal > displayPrice
      ? apiOriginal
      : null;
  const hasDiscount = originalPrice != null && originalPrice > displayPrice;
  let discountPercent = clearanceLineDiscountPercent(
    displayPrice,
    originalPrice,
    fallbackPct,
  );
  if (discountPercent <= 0 && hasDiscount && originalPrice != null) {
    discountPercent = Math.max(
      0,
      Math.min(100, Math.round(((originalPrice - displayPrice) / originalPrice) * 100)),
    );
  }
  if (discountPercent <= 0 && fallbackPct > 0) {
    discountPercent = Math.round(fallbackPct);
  }
  const rawColor = product.colors?.[0];
  const color =
    typeof rawColor === 'object' && rawColor != null
      ? String(rawColor.name || rawColor.value || '').trim()
      : String(rawColor || '').trim();
  return {
    color: color || (thumbUrl ? 'Như ảnh' : '—'),
    size,
    displayPrice,
    originalPrice,
    hasDiscount,
    thumbUrl,
    discountPercent,
  };
}

/** % hiển thị badge góc ảnh — luôn có khi có giá gạch hoặc % cấu hình kho. */
export function resolveClearanceCardHeroPercent(
  product: Product,
  firstLine?: ClearanceCardLine | null,
): number {
  const line = firstLine ?? getClearanceCardDisplayLines(product, 1)[0];
  let pct = getClearanceCardBestDiscountPercent(product);
  if (pct <= 0 && line) pct = line.discountPercent;
  if (
    pct <= 0 &&
    line?.hasDiscount &&
    line.originalPrice != null &&
    line.originalPrice > line.displayPrice
  ) {
    pct = Math.max(
      0,
      Math.min(
        100,
        Math.round(((line.originalPrice - line.displayPrice) / line.originalPrice) * 100),
      ),
    );
  }
  const cfg = Math.round(Number(product.warehouse_clearance?.discount_percent ?? 0));
  return Math.max(pct, cfg);
}

export type ClearanceCardLine = {
  color: string;
  size: string | null;
  displayPrice: number;
  originalPrice: number | null;
  hasDiscount: boolean;
  thumbUrl: string | null;
  discountPercent: number;
};

export type ClearanceCardHero = {
  /** Ảnh màu thanh lý — ưu tiên `color_image` biến thể đầu còn tồn. */
  imageUrl: string | null;
  /** % giảm cao nhất trong các dòng kho còn hàng. */
  discountPercent: number;
  /** Nhãn size trên badge ảnh (một size, hoặc «XL · L», hoặc «XL +2»). */
  sizeBadge: string | null;
};

/** % giảm thực tế của một dòng kho (ưu tiên chênh lệch giá, sau đó % cấu hình). */
export function clearanceLineDiscountPercent(
  displayPrice: number,
  originalPrice: number | null,
  configuredPercent = 0,
): number {
  const orig = originalPrice != null && originalPrice > displayPrice ? originalPrice : 0;
  if (orig > 0 && displayPrice > 0) {
    return Math.max(0, Math.min(100, Math.round(((orig - displayPrice) / orig) * 100)));
  }
  return Math.max(0, Math.min(100, Math.round(configuredPercent)));
}

function clearanceLineFromVariant(
  product: Product,
  variant: WarehouseClearanceVariant,
  fallbackPct: number,
): ClearanceCardLine {
  const pricing = resolveWarehouseVariantPricing(variant, fallbackPct);
  const originalPrice = pricing.hasDiscount ? pricing.originalPrice : null;
  return {
    color: warehouseVariantColorLabel(variant),
    size: warehouseVariantSizeLabel(variant),
    displayPrice: pricing.displayPrice,
    originalPrice,
    hasDiscount: pricing.hasDiscount,
    thumbUrl:
      warehouseVariantThumbUrl(variant) || String(product.main_image || '').trim() || null,
    discountPercent: clearanceLineDiscountPercent(
      pricing.displayPrice,
      originalPrice,
      pricing.percent,
    ),
  };
}

/** Dòng Màu/Size + giá sale kho trên thẻ SP (tối đa `limit`). */
export function getClearanceCardDisplayLines(product: Product, limit = 2): ClearanceCardLine[] {
  const fallbackPct = product.warehouse_clearance?.discount_percent ?? 0;
  const variants = warehouseVariantsInStock(product);
  if (variants.length > 0) {
    return variants.slice(0, limit).map((v) => clearanceLineFromVariant(product, v, fallbackPct));
  }
  if (!isWarehouseClearanceProduct(product)) return [];
  return [clearanceLineFromStandaloneProduct(product)];
}

/** Nhãn size gọn cho badge trên ảnh thẻ SP. */
export function getClearanceCardSizeBadge(product: Product): string | null {
  const variants = warehouseVariantsInStock(product);
  const sizes = [
    ...new Set(
      variants
        .map((v) => warehouseVariantSizeLabel(v))
        .filter((s): s is string => Boolean(s)),
    ),
  ];
  if (sizes.length === 1) return sizes[0];
  if (sizes.length === 2) return `${sizes[0]} · ${sizes[1]}`;
  if (sizes.length > 2) return `${sizes[0]} +${sizes.length - 1}`;
  const line = getClearanceCardDisplayLines(product, 1)[0];
  return line?.size ?? null;
}

/** % giảm cao nhất trong các dòng thanh lý còn tồn. */
export function getClearanceCardBestDiscountPercent(product: Product): number {
  const fallbackPct = product.warehouse_clearance?.discount_percent ?? 0;
  const variants = warehouseVariantsInStock(product);
  if (variants.length > 0) {
    const percents = variants.map(
      (v) => clearanceLineFromVariant(product, v, fallbackPct).discountPercent,
    );
    return Math.max(0, ...percents);
  }
  const line = getClearanceCardDisplayLines(product, 1)[0];
  return line?.discountPercent ?? 0;
}

/** Ảnh + % + size cho vùng ảnh đại diện thẻ SP khi có thanh lý. */
export function getClearanceCardHero(product: Product): ClearanceCardHero | null {
  if (!productShowsClearanceOnCard(product)) return null;
  const lines = getClearanceCardDisplayLines(product, 1);
  const first = lines[0];
  if (!first) return null;
  const discountPercent = resolveClearanceCardHeroPercent(product, first);
  const imageUrl =
    first.thumbUrl ||
    warehouseStandaloneSaleImage(product) ||
    String(product.main_image || '').trim() ||
    null;
  return {
    imageUrl,
    discountPercent,
    sizeBadge: getClearanceCardSizeBadge(product) ?? first.size,
  };
}

/** Có dòng kho thanh lý còn tồn — không phụ thuộc `warehouse_clearance.enabled` (cờ admin chỉ ảnh hưởng % giảm). */
export function productShowsClearanceOnCard(product: Product): boolean {
  return getClearanceCardDisplayLines(product).length > 0;
}

export function clearanceVariantCountOnCard(product: Product): number {
  const n = warehouseVariantsInStock(product).length;
  if (n > 0) return n;
  return isWarehouseClearanceProduct(product) ? 1 : 0;
}

/** Nhãn màu dòng kho — có ảnh Variant thì mặc định «Như ảnh». */
export function warehouseVariantColorLabel(variant: WarehouseClearanceVariant): string {
  const raw = (variant.color || '').trim();
  if (raw) return raw;
  if ((variant.color_image || variant.main_image || '').trim()) return 'Như ảnh';
  return '—';
}

export function warehouseVariantSizeLabel(variant: WarehouseClearanceVariant): string | null {
  const raw = (variant.size || '').trim();
  return raw || null;
}

export function warehouseVariantAriaLabel(variant: WarehouseClearanceVariant): string {
  const color = warehouseVariantColorLabel(variant);
  const size = warehouseVariantSizeLabel(variant);
  const parts: string[] = [];
  if (color !== '—') parts.push(`Màu ${color}`);
  if (size) parts.push(`Size ${size}`);
  return parts.length > 0 ? parts.join(', ') : String(variant.product_id || '');
}

export function canOrderSourceProduct(product: Product): boolean {
  if (product.source_oos) return false;
  return (product.available ?? 0) > 0;
}

export function canOrderAnyVariant(product: Product): boolean {
  return canOrderSourceProduct(product) || warehouseVariantsInStock(product).length > 0;
}

/** Storefront: ẩn SP hết hàng — khớp backend storefront_sellable_expr. */
export function isStorefrontVisibleProduct(product: Product): boolean {
  return canOrderAnyVariant(product);
}

export function filterStorefrontVisibleProducts(products: Product[]): Product[] {
  return products.filter(isStorefrontVisibleProduct);
}

/** Loại SP hết hàng khỏi payload listing (cache cũ / edge case). */
export function sanitizeStorefrontProductList<T extends { products?: Product[]; total?: number }>(
  body: T,
): T {
  const raw = body.products ?? [];
  const visible = filterStorefrontVisibleProducts(raw);
  if (visible.length === raw.length) return body;
  const stripped = raw.length - visible.length;
  const total =
    visible.length === 0 && stripped > 0
      ? 0
      : Math.max(0, (body.total ?? raw.length) - stripped);
  return { ...body, products: visible, total };
}

export function isWarehouseCartLine(item: {
  product_code?: string | null;
  product_data?: Record<string, unknown> | null;
}): boolean {
  const pd = item.product_data;
  if (pd && pd.is_warehouse_clearance === true) return true;
  const code = String(pd?.product_id ?? item.product_code ?? '');
  return code.includes('/');
}

/** Số lượng tối đa trong giỏ cho dòng kho = tồn kho dòng đó. */
export function cartLineMaxQuantity(item: {
  product_data?: Record<string, unknown> | null;
}): number {
  if (!isWarehouseCartLine(item)) return 100;
  const avail = Number(item.product_data?.available);
  if (!Number.isFinite(avail) || avail < 1) return 1;
  return Math.max(1, Math.floor(avail));
}

/** Giá đơn vị dòng giỏ kho thanh lý (sale + gốc gạch). */
/** Metadata gửi kèm product_data khi thêm dòng kho vào giỏ. */
export function warehouseCartProductDataExtras(p: Product): Record<string, unknown> {
  const code = String(p.product_id || '');
  if (!code.includes('/')) return {};
  const parentSlug = productPathSlugFromApi(p.slug, undefined);
  return {
    is_warehouse_clearance: true,
    warehouse_clearance_percent: p.warehouse_clearance?.discount_percent ?? 0,
    available: p.available,
    list_price: p.original_price != null && p.original_price > (p.price ?? 0) ? p.original_price : p.price,
    original_price: p.original_price,
    ...(parentSlug ? { slug: parentSlug, parent_slug: parentSlug } : {}),
  };
}

/** Slug PDP gốc khi mở từ giỏ — dòng kho không dùng slug có suffix product_id. */
export function resolveWarehouseCartPdpSlug(item: {
  product_code?: string | null;
  product_data?: Record<string, unknown> | null;
}): string | null {
  if (!isWarehouseCartLine(item)) return null;
  const pd = item.product_data || {};
  const fromParent = productPathSlugFromApi(
    typeof pd.parent_slug === 'string' ? pd.parent_slug : undefined,
    typeof pd.slug === 'string' ? pd.slug : undefined,
  );
  return fromParent || null;
}

export function resolveWarehouseCartLineUnitPricing(item: {
  product_price?: number;
  list_price?: number | null;
  original_price?: number | null;
  product_data?: Record<string, unknown> | null;
}): WarehouseVariantPricing {
  const pd = item.product_data || {};
  const fallbackPct = Number(pd.warehouse_clearance_percent ?? 0);
  const listPrice = Math.max(
    0,
    Number(
      item.list_price ??
        item.original_price ??
        pd.list_price ??
        pd.original_price ??
        item.product_price ??
        0,
    ),
  );
  const apiDisplay = Math.max(0, Number(item.product_price ?? pd.price ?? listPrice));
  const apiOriginal = Math.max(
    0,
    Number(item.original_price ?? pd.original_price ?? listPrice),
  );

  if (apiOriginal > apiDisplay && apiDisplay > 0) {
    const inferredPct =
      fallbackPct > 0
        ? fallbackPct
        : Math.round(((apiOriginal - apiDisplay) / apiOriginal) * 100);
    const savingsAmount = Math.max(0, apiOriginal - apiDisplay);
    return {
      displayPrice: apiDisplay,
      originalPrice: apiOriginal,
      listPrice: apiOriginal,
      percent: Math.max(0, Math.min(100, inferredPct)),
      hasDiscount: true,
      savingsAmount,
    };
  }

  const pct = Math.max(0, Math.min(100, fallbackPct));
  let displayPrice = apiDisplay;
  let originalPrice = apiOriginal > 0 ? apiOriginal : listPrice;

  if (pct > 0 && listPrice > 0 && displayPrice >= originalPrice) {
    displayPrice = Math.max(0, Math.round(listPrice * (1 - pct / 100)));
    originalPrice = listPrice;
  }

  const hasDiscount = originalPrice > displayPrice && displayPrice > 0;
  const savingsAmount = hasDiscount ? Math.max(0, originalPrice - displayPrice) : 0;
  return {
    displayPrice,
    originalPrice,
    listPrice: listPrice || originalPrice,
    percent: pct,
    hasDiscount,
    savingsAmount,
  };
}
