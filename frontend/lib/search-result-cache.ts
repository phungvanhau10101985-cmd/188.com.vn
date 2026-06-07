import type { ProductListResponse } from '@/types/api';

/**
 * Cache sessionStorage theo từ khóa (đã ngừng dùng cho phân trang tìm kiếm).
 * Danh sách SP được cache server-side (DB) theo từ khóa + filter — không theo trang.
 */

const PREFIX = '188-sr-cache:v9';
const META_KEY = `${PREFIX}:meta`;

/** @deprecated Không dùng cho luồng tìm kiếm — giữ để dọn session cũ. */
export const SEARCH_RESULT_CACHE_TTL_MS = 5 * 60 * 1000;

const MAX_CACHE_KEYS = 24;

type Meta = { order: string[] };

function storageKey(hash: string): string {
  return `${PREFIX}:${hash}`;
}

function fnv1a32(str: string): string {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0).toString(36);
}

/** Fingerprint theo từ khóa + filter — không có skip/limit. */
export function searchKeywordCacheFingerprint(params: {
  q: string;
  is_active?: boolean;
  shop_id?: string | undefined;
  shop_name?: string | undefined;
  shop_name_chinese?: string | undefined;
  chinese_name?: string | undefined;
  style?: string | undefined;
  pro_lower_price?: string | undefined;
  pro_high_price?: string | undefined;
  min_price?: number | undefined;
  max_price?: number | undefined;
  size?: string | undefined;
  color?: string | undefined;
  style_tag?: string | undefined;
  sort?: string | undefined;
}): string {
  const n = {
    q: String(params.q).trim(),
    ia: params.is_active !== false ? 1 : 0,
    sid: params.shop_id ?? '',
    sn: params.shop_name ?? '',
    stc: params.shop_name_chinese ?? '',
    cn: params.chinese_name ?? '',
    sty: params.style ?? '',
    pl: params.pro_lower_price ?? '',
    ph: params.pro_high_price ?? '',
    min: params.min_price ?? '',
    max: params.max_price ?? '',
    sz: params.size ?? '',
    cl: params.color ?? '',
    stylet: params.style_tag ?? '',
    so: params.sort ?? '',
  };
  return fnv1a32(JSON.stringify(n));
}

/** @deprecated Dùng searchKeywordCacheFingerprint — không gồm skip/limit. */
export function searchRequestCacheFingerprint(params: {
  q: string;
  is_active?: boolean;
  shop_id?: string | undefined;
  shop_name?: string | undefined;
  shop_name_chinese?: string | undefined;
  chinese_name?: string | undefined;
  style?: string | undefined;
  pro_lower_price?: string | undefined;
  pro_high_price?: string | undefined;
  min_price?: number | undefined;
  max_price?: number | undefined;
  size?: string | undefined;
  color?: string | undefined;
  style_tag?: string | undefined;
  sort?: string | undefined;
  skip: number;
  limit: number;
}): string {
  const { skip: _skip, limit: _limit, ...rest } = params;
  return searchKeywordCacheFingerprint(rest);
}

function readMeta(): Meta {
  if (typeof window === 'undefined') return { order: [] };
  try {
    const raw = sessionStorage.getItem(META_KEY);
    if (!raw) return { order: [] };
    const p = JSON.parse(raw) as Meta;
    return Array.isArray(p.order) ? p : { order: [] };
  } catch {
    return { order: [] };
  }
}

function writeMeta(m: Meta) {
  if (typeof window === 'undefined') return;
  sessionStorage.setItem(META_KEY, JSON.stringify(m));
}

function removeFromMeta(hash: string) {
  const m = readMeta();
  m.order = m.order.filter((h) => h !== hash);
  writeMeta(m);
}

function touchMeta(hash: string) {
  let m = readMeta();
  m.order = m.order.filter((h) => h !== hash);
  m.order.push(hash);
  while (m.order.length > MAX_CACHE_KEYS) {
    const drop = m.order.shift();
    if (drop) {
      try {
        sessionStorage.removeItem(storageKey(drop));
      } catch {
        /* noop */
      }
    }
  }
  writeMeta(m);
}

interface StoredPayload {
  t: number;
  body: ProductListResponse;
}

/** @deprecated Tìm kiếm dùng cache server — không đọc session theo trang. */
export function readSearchResultCache(fp: string): ProductListResponse | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = sessionStorage.getItem(storageKey(fp));
    if (!raw) return null;
    const s = JSON.parse(raw) as StoredPayload;
    if (!s || typeof s.t !== 'number' || !s.body) {
      sessionStorage.removeItem(storageKey(fp));
      removeFromMeta(fp);
      return null;
    }
    if (Date.now() - s.t > SEARCH_RESULT_CACHE_TTL_MS) {
      sessionStorage.removeItem(storageKey(fp));
      removeFromMeta(fp);
      return null;
    }
    return s.body;
  } catch {
    return null;
  }
}

/** @deprecated Tìm kiếm dùng cache server — không ghi session theo trang. */
export function writeSearchResultCache(fp: string, body: ProductListResponse): void {
  if (typeof window === 'undefined') return;
  if (body.redirect_path) return;
  try {
    const payload: StoredPayload = { t: Date.now(), body };
    sessionStorage.setItem(storageKey(fp), JSON.stringify(payload));
    touchMeta(fp);
  } catch {
    trimSearchResultCacheHalf();
    try {
      const payload: StoredPayload = { t: Date.now(), body };
      sessionStorage.setItem(storageKey(fp), JSON.stringify(payload));
      touchMeta(fp);
    } catch {
      /* bỏ qua nếu vẫn đầy */
    }
  }
}

function trimSearchResultCacheHalf() {
  const m = readMeta();
  const dropN = Math.max(1, Math.ceil(m.order.length / 2));
  for (let i = 0; i < dropN && m.order.length > 0; i++) {
    const h = m.order.shift();
    if (h) {
      try {
        sessionStorage.removeItem(storageKey(h));
      } catch {
        /* noop */
      }
    }
  }
  writeMeta(m);
}
