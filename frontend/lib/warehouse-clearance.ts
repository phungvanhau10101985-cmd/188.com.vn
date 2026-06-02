import type { Product, WarehouseClearanceVariant } from '@/types/api';

/** Gộp SP gốc + dòng kho để add-to-cart với đúng product_id DB kho. */
export function warehouseVariantAsProduct(
  parent: Product,
  variant: WarehouseClearanceVariant,
): Product {
  return {
    ...parent,
    id: variant.id,
    product_id: variant.product_id,
    price: variant.display_price,
    original_price: variant.original_price,
    available: variant.available,
    main_image: variant.main_image || parent.main_image,
    sizes: variant.size ? [variant.size] : [],
    colors: variant.color ? [{ name: variant.color, value: variant.color }] : [],
    site_sale: undefined,
  };
}

export function warehouseVariantsInStock(product: Product): WarehouseClearanceVariant[] {
  return (product.warehouse_variants ?? []).filter((v) => (v.available ?? 0) > 0);
}

export function canOrderSourceProduct(product: Product): boolean {
  if (product.source_oos) return false;
  return (product.available ?? 0) > 0;
}

export function canOrderAnyVariant(product: Product): boolean {
  return canOrderSourceProduct(product) || warehouseVariantsInStock(product).length > 0;
}
