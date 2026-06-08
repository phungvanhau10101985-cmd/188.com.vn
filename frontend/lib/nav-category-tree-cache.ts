import type { CategoryLevel1 } from '@/types/api';

/** Cache cây danh mục menu desktop — localStorage, tồn tại qua tab/session. */
export const NAV_CATEGORY_TREE_CACHE_KEY = '188-nav-category-tree-v1';

/** Hiển thị ngay; refresh nền khi cũ hơn ngưỡng này. */
export const NAV_CATEGORY_TREE_CACHE_MAX_AGE_MS = 6 * 60 * 60 * 1000;

interface NavCategoryTreeCachePayload {
  v: 1;
  savedAt: number;
  tree: CategoryLevel1[];
}

function parsePayload(raw: string): NavCategoryTreeCachePayload | null {
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (Array.isArray(parsed)) {
      return { v: 1, savedAt: 0, tree: parsed as CategoryLevel1[] };
    }
    if (!parsed || typeof parsed !== 'object') return null;
    const p = parsed as Partial<NavCategoryTreeCachePayload>;
    if (p.v !== 1 || !Array.isArray(p.tree)) return null;
    return {
      v: 1,
      savedAt: typeof p.savedAt === 'number' ? p.savedAt : 0,
      tree: p.tree as CategoryLevel1[],
    };
  } catch {
    return null;
  }
}

function readLegacySessionCategoryTree(): CategoryLevel1[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = sessionStorage.getItem(NAV_CATEGORY_TREE_CACHE_KEY);
    if (!raw) return [];
    const payload = parsePayload(raw);
    return payload?.tree?.length ? payload.tree : [];
  } catch {
    return [];
  }
}

/** Đọc cây danh mục đã lưu — dùng ngay khi SSR chưa kịp trả data. */
export function readNavCategoryTreeCache(): CategoryLevel1[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(NAV_CATEGORY_TREE_CACHE_KEY);
    if (raw) {
      const payload = parsePayload(raw);
      if (payload?.tree?.length) return payload.tree;
    }
    const legacy = readLegacySessionCategoryTree();
    if (legacy.length > 0) {
      writeNavCategoryTreeCache(legacy);
      try {
        sessionStorage.removeItem(NAV_CATEGORY_TREE_CACHE_KEY);
      } catch {
        /* ignore */
      }
    }
    return legacy;
  } catch {
    return [];
  }
}

export function readNavCategoryTreeCacheSavedAt(): number | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(NAV_CATEGORY_TREE_CACHE_KEY);
    if (!raw) return null;
    const payload = parsePayload(raw);
    return payload?.savedAt ?? null;
  } catch {
    return null;
  }
}

export function isNavCategoryTreeCacheStale(
  maxAgeMs: number = NAV_CATEGORY_TREE_CACHE_MAX_AGE_MS,
): boolean {
  const savedAt = readNavCategoryTreeCacheSavedAt();
  if (savedAt == null) return true;
  return Date.now() - savedAt > maxAgeMs;
}

export function writeNavCategoryTreeCache(tree: CategoryLevel1[]): void {
  if (typeof window === 'undefined' || tree.length === 0) return;
  try {
    const payload: NavCategoryTreeCachePayload = {
      v: 1,
      savedAt: Date.now(),
      tree,
    };
    localStorage.setItem(NAV_CATEGORY_TREE_CACHE_KEY, JSON.stringify(payload));
  } catch {
    /* quota / private mode */
  }
}
