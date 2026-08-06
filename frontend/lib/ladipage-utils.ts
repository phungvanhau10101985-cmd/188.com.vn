import type { AdminProduct } from '@/lib/admin-api';
import type { HeroImageOption } from '@/components/ladipage/types';

export type { HeroImageOption };

export function sortProductsByIds<T extends { id: number }>(products: T[], ids: number[]): T[] {
  const order = new Map(ids.map((id, index) => [id, index]));
  return [...products].sort((a, b) => (order.get(a.id) ?? 999) - (order.get(b.id) ?? 999));
}

type LooseProduct = AdminProduct & {
  color_image_urls?: string[];
  color_variants?: Array<{ name?: string | null; img?: string | null }>;
  colors?: Array<{ name?: string; img?: string; value?: string }>;
};

/** Gom ảnh đại diện, gallery, chi tiết, màu — dùng chọn hero / ảnh chất liệu ladipage 1 SP. */
export function buildProductImageOptionsFromProducts(products: LooseProduct[]): HeroImageOption[] {
  const options: HeroImageOption[] = [];
  const seen = new Set<string>();

  const push = (product: LooseProduct, url: string, label: string) => {
    const u = url.trim();
    if (!u || seen.has(u)) return;
    seen.add(u);
    options.push({
      url: u,
      productId: product.id,
      productName: product.name,
      label,
    });
  };

  for (const product of products) {
    if (product.main_image?.trim()) {
      push(product, product.main_image, 'Ảnh đại diện');
    }
    if (Array.isArray(product.images)) {
      let i = 0;
      for (const img of product.images) {
        if (typeof img !== 'string' || !img.trim()) continue;
        i += 1;
        push(product, img, `Gallery ${i}`);
      }
    }
    if (Array.isArray(product.gallery)) {
      let i = 0;
      for (const img of product.gallery) {
        if (typeof img !== 'string' || !img.trim()) continue;
        i += 1;
        push(product, img, `Chi tiết ${i}`);
      }
    }
    if (Array.isArray(product.color_image_urls)) {
      let i = 0;
      for (const img of product.color_image_urls) {
        if (typeof img !== 'string' || !img.trim()) continue;
        i += 1;
        push(product, img, `Ảnh màu ${i}`);
      }
    }
    if (Array.isArray(product.color_variants)) {
      for (const cv of product.color_variants) {
        const img = cv?.img?.trim();
        if (!img) continue;
        const name = (cv?.name || '').trim();
        push(product, img, name ? `Màu ${name}` : 'Ảnh màu');
      }
    }
    if (Array.isArray(product.colors)) {
      for (const cv of product.colors) {
        const img = cv?.img?.trim();
        if (!img) continue;
        const name = (cv?.name || '').trim();
        push(product, img, name ? `Màu ${name}` : 'Ảnh màu');
      }
    }
  }

  return options;
}

/** @deprecated Alias — dùng buildProductImageOptionsFromProducts */
export const buildHeroImageOptionsFromProducts = buildProductImageOptionsFromProducts;

export function parseHeroObjectPosition(raw?: string | null): { x: number; y: number } {
  if (!raw?.trim()) return { x: 50, y: 50 };
  const parts = raw.trim().split(/\s+/);
  const read = (part: string, fallback: number) => {
    const match = part.match(/^([\d.]+)%$/);
    if (!match) return fallback;
    return Math.min(100, Math.max(0, Number(match[1])));
  };
  return {
    x: read(parts[0] || '', 50),
    y: read(parts[1] || parts[0] || '', 50),
  };
}

export function formatHeroObjectPosition(x: number, y: number): string {
  return `${Math.round(x)}% ${Math.round(y)}%`;
}
