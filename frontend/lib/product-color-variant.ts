import type { Product, ProductColor } from '@/types/api';

/** Lấy URL ảnh ô màu — Excel/import có thể dùng `image`, `image_url`, v.v. thay vì `img`. */
export function colorEntryImageUrl(entry: ProductColor | Record<string, unknown> | null | undefined): string {
  if (!entry || typeof entry !== 'object') return '';
  const o = entry as Record<string, unknown>;
  const keys = ['img', 'image', 'image_url', 'imageUrl', 'thumb', 'url', 'picture'] as const;
  for (const k of keys) {
    const v = o[k];
    if (v != null && String(v).trim()) return String(v).trim();
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
      const img = colorEntryImageUrl(colors[i]);
      return img || fallback;
    }
  }
  const m = /\((\d+)\)\s*$/.exec(label);
  if (m) {
    const idx = parseInt(m[1], 10) - 1;
    if (idx >= 0 && idx < colors.length) {
      const img = colorEntryImageUrl(colors[idx]);
      if (img) return img;
    }
  }
  return fallback;
}
