import type { ProductListResponse } from '@/types/api';

const PREFIX = '188-sr-cache:v1';
const META_KEY = `${PREFIX}:meta`;

/** Thời gian sống cache — sau đó gọi API lại (đồng bộ kho / giá). */
export const SEARCH_RESULT_CACHE_TTL_MS = 5 * 60 * 1000;

/** Giới hạn số entry / tab (mỗi entry ≈ một cặp skip+limit của một truy vấn). */
const MAX_CACHE_KEYS = 36;

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

/**
 * Fingerprint ổn định cho một request tìm theo `q` + filter + phân trang (skip/limit).
 */
export function searchRequestCacheFingerprint(params: {
  q: string;
  is_active?: boolean;
  shop_id?: string | undefined;
  shop_name?: string | undefined;
  pro_lower_price?: string | undefined;
  pro_high_price?: string | undefined;
  min_price?: number | undefined;
  max_price?: number | undefined;
  skip: number;
  limit: number;
}): string {
  const n = {
    q: String(params.q).trim(),
    ia: params.is_active !== false ? 1 : 0,
    sid: params.shop_id ?? '',
    sn: params.shop_name ?? '',
    pl: params.pro_lower_price ?? '',
    ph: params.pro_high_price ?? '',
    min: params.min_price ?? '',
    max: params.max_price ?? '',
    sk: params.skip,
    li: params.limit,
  };
  return fnv1a32(JSON.stringify(n));
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
