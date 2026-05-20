/**
 * SSR: nhóm danh mục hero trang chủ (đã cache DB) — hiển thị ngay, không chờ API cá nhân hóa.
 */
import type { HeroCategoryTilesResponse } from '@/types/api';

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8001/api/v1';

const FETCH_TIMEOUT_MS = 6000;
const isDev = process.env.NODE_ENV === 'development';
const disableCache =
  process.env.NEXT_PUBLIC_DISABLE_CACHE === '1' || process.env.DISABLE_CACHE === '1';
const REVALIDATE = isDev || disableCache ? 0 : 300;

export async function getInitialHomeHeroCategories(
  gender: 'Nam' | 'Nữ' = 'Nam',
  limit = 16,
): Promise<HeroCategoryTilesResponse | null> {
  try {
    const params = new URLSearchParams({
      gender,
      limit: String(limit),
    });
    const res = await fetch(`${API_BASE}/categories/from-products/hero-tiles-cached?${params}`, {
      next: { revalidate: REVALIDATE },
      headers: { 'Content-Type': 'application/json' },
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    });
    if (!res.ok) return null;
    const data = (await res.json()) as HeroCategoryTilesResponse;
    if (!Array.isArray(data?.tiles) || data.tiles.length === 0) return null;
    return {
      tiles: data.tiles,
      gender_label: data.gender_label ?? gender,
      heading: data.heading ?? null,
      subtitle: data.subtitle ?? null,
      anchor_category: data.anchor_category ?? null,
      source: data.source ?? 'cached_db',
    };
  } catch {
    return null;
  }
}
