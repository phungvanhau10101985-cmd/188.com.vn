import { SHOP_NAME_CHINESE_QUERY_PARAM } from '@/lib/product-related-tabs';

export function spGetMeta(
  sp: Record<string, string | string[] | undefined>,
  key: string
): string | undefined {
  const v = sp[key];
  if (Array.isArray(v)) return v[0];
  return v;
}

/** Tham số ảnh hưởng snippet SEO (ngoài path cố định). */
export function categoryListingHasSeoDimensions(
  sp: Record<string, string | string[] | undefined>
): boolean {
  const page = parseInt(String(spGetMeta(sp, 'page') ?? '1'), 10) || 1;
  if (page > 1) return true;
  const keys = ['min_price', 'max_price', 'size', 'color', 'sort'] as const;
  return keys.some((k) => Boolean((spGetMeta(sp, k) ?? '').trim()));
}

/** Khớp `homeHasListingFilters` (app/page.tsx) — không tính `page` đơn thuần. */
export function homeHasListingFiltersFromSp(
  sp: Record<string, string | string[] | undefined>
): boolean {
  return Boolean(
    (spGetMeta(sp, 'q') ?? '').trim() ||
      (spGetMeta(sp, 'category') ?? '').trim() ||
      (spGetMeta(sp, 'subcategory') ?? '').trim() ||
      (spGetMeta(sp, 'sub_subcategory') ?? '').trim() ||
      (spGetMeta(sp, 'shop_id') ?? '').trim() ||
      (spGetMeta(sp, 'shop_name') ?? '').trim() ||
      (spGetMeta(sp, 'pro_lower_price') ?? '').trim() ||
      (spGetMeta(sp, 'pro_high_price') ?? '').trim() ||
      (spGetMeta(sp, 'shop_name_chinese') ?? '').trim() ||
      (spGetMeta(sp, SHOP_NAME_CHINESE_QUERY_PARAM) ?? '').trim() ||
      (spGetMeta(sp, 'chinese_name') ?? '').trim() ||
      (spGetMeta(sp, 'style') ?? '').trim() ||
      (spGetMeta(sp, 'min_price') ?? '').trim() ||
      (spGetMeta(sp, 'max_price') ?? '').trim() ||
      (spGetMeta(sp, 'size') ?? '').trim() ||
      (spGetMeta(sp, 'color') ?? '').trim() ||
      (spGetMeta(sp, 'sort') ?? '').trim()
  );
}

/** Giống `homeHasListingFilters` + trang listing `page>1` cho canonical/metadata. */
export function homeUrlNeedsFilteredMeta(
  sp: Record<string, string | string[] | undefined>
): boolean {
  const pageNum = Math.max(1, parseInt(String(spGetMeta(sp, 'page') ?? '1'), 10) || 1);
  if (pageNum > 1) return true;
  return homeHasListingFiltersFromSp(sp);
}

const SORT_LABEL_VI: Record<string, string> = {
  newest: 'Mới nhất',
  oldest: 'Cũ nhất',
  views_desc: 'Xem nhiều',
  default: 'Mặc định',
};

function formatVndShort(n: number): string {
  if (!Number.isFinite(n)) return '';
  const v = Math.round(n);
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(v % 1_000_000 === 0 ? 0 : 1)} triệu ₫`.replace('.', ',');
  if (v >= 1000) return `${Math.round(v / 1000)}k ₫`;
  return `${v.toLocaleString('vi-VN')} ₫`;
}

/** Mảng mô tả ngắn cho title / description (tiếng Việt). */
export function buildCategoryFilterMetaParts(
  sp: Record<string, string | string[] | undefined>
): string[] {
  const parts: string[] = [];
  const page = Math.max(1, parseInt(String(spGetMeta(sp, 'page') ?? '1'), 10) || 1);
  if (page > 1) parts.push(`Trang ${page}`);

  const sz = (spGetMeta(sp, 'size') ?? '').trim();
  if (sz) parts.push(`Size ${sz}`);

  const cl = (spGetMeta(sp, 'color') ?? '').trim();
  if (cl) parts.push(`Màu ${cl}`);

  const minRaw = (spGetMeta(sp, 'min_price') ?? '').trim();
  const maxRaw = (spGetMeta(sp, 'max_price') ?? '').trim();
  const minN = minRaw ? Number(minRaw) : NaN;
  const maxN = maxRaw ? Number(maxRaw) : NaN;
  if (!Number.isNaN(minN) && !Number.isNaN(maxN)) {
    parts.push(`Giá ${formatVndShort(minN)}–${formatVndShort(maxN)}`);
  } else if (!Number.isNaN(minN)) {
    parts.push(`Từ ${formatVndShort(minN)}`);
  } else if (!Number.isNaN(maxN)) {
    parts.push(`Đến ${formatVndShort(maxN)}`);
  }

  const sort = (spGetMeta(sp, 'sort') ?? '').trim();
  if (sort) {
    parts.push(`Sắp xếp: ${SORT_LABEL_VI[sort] ?? sort}`);
  }

  return parts;
}

function normalizeSiteUrl(): string {
  const raw = (
    process.env.NEXT_PUBLIC_SITE_URL?.trim() ||
    process.env.NEXT_PUBLIC_DOMAIN?.trim() ||
    (process.env.NODE_ENV === 'development' ? 'http://localhost:3001' : 'https://188.com.vn')
  ).replace(/\/$/, '');
  if (/^https?:\/\//i.test(raw)) return raw;
  return `https://${raw.replace(/^\/+/, '')}`;
}

/** Canonical ổn định: chỉ các key lọc + page, sắp xếp alphabet. */
export function buildCategoryCanonicalWithFilters(
  pathWithoutQuery: string,
  sp: Record<string, string | string[] | undefined>
): string {
  const site = normalizeSiteUrl();
  const keys = ['color', 'max_price', 'min_price', 'page', 'size', 'sort'] as const;
  const p = new URLSearchParams();
  for (const key of keys) {
    const v = (spGetMeta(sp, key) ?? '').trim();
    if (!v) continue;
    if (key === 'page' && (v === '1' || v === '01')) continue;
    p.set(key, v);
  }
  const qs = p.toString();
  const path = pathWithoutQuery.startsWith('/') ? pathWithoutQuery : `/${pathWithoutQuery}`;
  return qs ? `${site}${path}?${qs}` : `${site}${path}`;
}

const HOME_META_KEYS = [
  'category',
  'chinese_name',
  'color',
  'max_price',
  'min_price',
  'page',
  'pro_high_price',
  'pro_lower_price',
  'q',
  'shop_id',
  'shop_name',
  'shop_name_chinese',
  SHOP_NAME_CHINESE_QUERY_PARAM,
  'size',
  'sort',
  'style',
  'sub_subcategory',
  'subcategory',
] as const;

export function buildHomeCanonicalWithFilters(
  sp: Record<string, string | string[] | undefined>
): string {
  const site = normalizeSiteUrl();
  const p = new URLSearchParams();
  for (const key of HOME_META_KEYS) {
    const v = (spGetMeta(sp, key) ?? '').trim();
    if (!v) continue;
    if (key === 'page' && (v === '1' || v === '01')) continue;
    p.set(key, v);
  }
  const qs = p.toString();
  return qs ? `${site}/?${qs}` : `${site}/`;
}

export function buildHomeFilterTitleParts(
  sp: Record<string, string | string[] | undefined>
): string[] {
  const parts: string[] = [];
  const q = (spGetMeta(sp, 'q') ?? '').trim();
  if (q) parts.push(`Tìm “${q.length > 48 ? `${q.slice(0, 47)}…` : q}”`);

  const style = (spGetMeta(sp, 'style') ?? '').trim();
  if (style) parts.push(`Style ${style.length > 40 ? `${style.slice(0, 39)}…` : style}`);

  const cat = [spGetMeta(sp, 'category'), spGetMeta(sp, 'subcategory'), spGetMeta(sp, 'sub_subcategory')]
    .map((s) => (s ?? '').trim())
    .filter(Boolean);
  if (cat.length) parts.push(cat.join(' › '));

  const shop = (spGetMeta(sp, 'shop_name') ?? '').trim();
  if (shop) parts.push(`Shop ${shop.length > 32 ? `${shop.slice(0, 31)}…` : shop}`);

  parts.push(...buildCategoryFilterMetaParts(sp));
  return parts;
}

