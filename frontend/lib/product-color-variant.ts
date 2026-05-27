import type { Product, ProductColor, NanoaiColorVariant } from '@/types/api';

export type ColorSwatchProductRef = Pick<
  Product,
  'colors' | 'color_image_urls' | 'color_variants' | 'images' | 'gallery' | 'main_image'
>;

/** Lấy URL ảnh ô màu — Excel/import có thể dùng `image`, `image_url`, v.v. thay vì `img`. */
export function colorEntryImageUrl(
  entry: ProductColor | NanoaiColorVariant | Record<string, unknown> | null | undefined,
): string {
  if (!entry || typeof entry !== 'object') return '';
  const o = entry as Record<string, unknown>;
  const keys = ['img', 'image', 'image_url', 'imageUrl', 'thumb', 'url', 'picture'] as const;
  for (const k of keys) {
    const v = o[k];
    if (v != null && String(v).trim()) return String(v).trim();
  }
  return '';
}

function dedupeTrimmedUrls(urls: (string | null | undefined)[]): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const raw of urls) {
    const u = (raw ?? '').trim();
    if (!u || seen.has(u)) continue;
    seen.add(u);
    out.push(u);
  }
  return out;
}

/** Ảnh thumbnail cho ô màu thứ `index` — thử entry, color_image_urls, color_variants, gallery/images. */
export function resolveColorSwatchImageUrl(product: ColorSwatchProductRef, index: number): string {
  if (index < 0) return '';
  const colors = product.colors || [];

  const fromEntry = colors[index] ? colorEntryImageUrl(colors[index]) : '';
  if (fromEntry) return fromEntry;

  const colorUrls = product.color_image_urls ?? (product as { colorImageUrls?: string[] }).colorImageUrls;
  if (Array.isArray(colorUrls)) {
    const u = (colorUrls[index] ?? '').trim();
    if (u) return u;
  }

  const variants = product.color_variants ?? (product as { colorVariants?: ProductColor[] }).colorVariants;
  if (Array.isArray(variants) && variants[index]) {
    const fromVariant = colorEntryImageUrl(variants[index]);
    if (fromVariant) return fromVariant;
  }

  const galleryPool = dedupeTrimmedUrls([...(product.gallery || []), ...(product.images || [])]);
  if (galleryPool[index]) return galleryPool[index];

  if (index === 0) {
    const main = (product.main_image ?? '').trim();
    if (main) return main;
  }

  return '';
}

/**
 * Nhãn gửi giỏ / đơn: khi nhiều dòng trùng `name` (vd. cùng «NHƯ ẢNH»), thêm hậu tố (1)(2)… để phân biệt.
 */
export function colorLabelForCart(colors: ProductColor[], index: number): string {
  if (index < 0 || !colors[index]) return '';
  const c = colors[index];
  const base = (c.name || '').trim() || 'Màu';
  const nameNorm = (c.name || '').trim();
  const dupCount = colors.filter((x) => (x.name || '').trim() === nameNorm).length;
  if (dupCount > 1 || !nameNorm) return `${base} (${index + 1})`;
  return base;
}

/** Phần màu trong khóa biến thể nội bộ (luôn khác nhau theo ô trong Excel). */
export function colorVariantKeyPart(colorsLength: number, index: number): string {
  if (colorsLength <= 0 || index < 0) return '';
  return `c${index}`;
}

/** Ảnh hiển thị trong giỏ theo nhãn màu đã chọn (`colorLabelForCart`), fallback `main_image`. */
export function cartLineMainImage(product: Product, selectedColorLabel?: string | null): string | undefined {
  const fallback = product.main_image?.trim() || undefined;
  const label = (selectedColorLabel || '').trim();
  const colors = product.colors || [];
  if (!label || colors.length === 0) return fallback;
  for (let i = 0; i < colors.length; i++) {
    if (colorLabelForCart(colors, i) === label) {
      const img = resolveColorSwatchImageUrl(product, i);
      return img || fallback;
    }
  }
  const m = /\((\d+)\)\s*$/.exec(label);
  if (m) {
    const idx = parseInt(m[1], 10) - 1;
    if (idx >= 0 && idx < colors.length) {
      const img = resolveColorSwatchImageUrl(product, idx);
      if (img) return img;
    }
  }
  return fallback;
}

/** URL ảnh một dòng giỏ — `line_image_url` → `product_data.main_image` → `product_image`. */
export function resolveCartItemImageUrl(item: {
  line_image_url?: string | null;
  product_data?: { main_image?: string } | Record<string, unknown> | null;
  product_image?: string | null;
}): string {
  const explicit = item.line_image_url;
  if (explicit != null && String(explicit).trim()) return String(explicit).trim();
  const pd = item.product_data;
  if (pd && typeof pd === 'object') {
    const fromPd = (pd as { main_image?: string }).main_image;
    if (fromPd != null && String(fromPd).trim()) return String(fromPd).trim();
  }
  const fromCol = item.product_image;
  if (fromCol != null && String(fromCol).trim()) return String(fromCol).trim();
  return '';
}
