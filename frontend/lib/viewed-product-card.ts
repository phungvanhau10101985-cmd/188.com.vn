import type { Product } from '@/types/api';
import { representativeProductImage } from '@/lib/image-utils';

function coverFromProduct(product: {
  main_image?: string | null;
  images?: readonly (string | null | undefined)[] | null;
}): string | undefined {
  return representativeProductImage(product);
}

/** Snapshot `product_data` (đã xem / yêu thích) → Product cho thẻ lưới. */
export function snapshotProductDataAsProduct(
  productId: number,
  productData?: Record<string, unknown> | null,
): Product {
  const d = productData || {};
  return {
    id: productId,
    product_id: String(d.product_id ?? productId),
    code: String(d.code ?? ''),
    name: String(d.name ?? `Sản phẩm #${productId}`),
    slug: String(d.slug ?? productId),
    price: Number(d.price ?? 0),
    created_at: String(d.created_at ?? new Date(0).toISOString()),
    main_image: coverFromProduct({
      main_image: typeof d.main_image === 'string' ? d.main_image : undefined,
      images: Array.isArray(d.images) ? (d.images as string[]) : undefined,
    }),
    images: Array.isArray(d.images) ? (d.images as string[]) : undefined,
    brand_name: typeof d.brand_name === 'string' ? d.brand_name : undefined,
    warehouse_variants: Array.isArray(d.warehouse_variants) ? (d.warehouse_variants as Product['warehouse_variants']) : undefined,
    warehouse_clearance: d.warehouse_clearance as Product['warehouse_clearance'],
    is_warehouse_clearance: d.is_warehouse_clearance === true,
    sizes: Array.isArray(d.sizes) ? (d.sizes as string[]) : undefined,
    colors: Array.isArray(d.colors) ? (d.colors as Product['colors']) : undefined,
  };
}

export function snapshotNeedsProductRefresh(data: Record<string, unknown>): boolean {
  const cover = coverFromProduct({
    main_image: typeof data.main_image === 'string' ? data.main_image : undefined,
    images: Array.isArray(data.images) ? (data.images as string[]) : undefined,
  });
  const missingBasics =
    !data.name || data.price == null || data.price === undefined || !cover;
  const neverEnrichedClearance =
    data.warehouse_clearance === undefined && data.warehouse_variants === undefined;
  return missingBasics || neverEnrichedClearance;
}

/** Snapshot chưa enrich kho — chỉ fetch by-ids khi API chưa gắn warehouse_clearance/variants. */
export function snapshotNeedsClearanceEnrich(data: Record<string, unknown>): boolean {
  if (data.is_warehouse_clearance === true) return false;
  // API đã batch-enrich (kể cả variants rỗng) → không gọi lại by-ids.
  if (Array.isArray(data.warehouse_variants) || data.warehouse_clearance !== undefined) return false;
  if (String(data.product_id || '').includes('/')) return false;
  return true;
}

export function mergeProductSnapshotFromApi(
  data: Record<string, unknown>,
  product: Product,
): Record<string, unknown> {
  return {
    ...data,
    id: product.id,
    code: product.code,
    product_id: product.product_id,
    name: product.name,
    price: product.price,
    main_image: coverFromProduct(product) || product.main_image,
    images: product.images ?? data.images,
    brand_name: product.brand_name ?? data.brand_name,
    slug: product.slug ?? data.slug,
    warehouse_variants: product.warehouse_variants,
    warehouse_clearance: product.warehouse_clearance,
    is_warehouse_clearance: product.is_warehouse_clearance,
    sizes: product.sizes,
    colors: product.colors,
  };
}
