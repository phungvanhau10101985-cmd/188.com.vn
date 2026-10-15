/**
 * SSR banner trang chủ — ảnh LCP có trong HTML, không chờ hydrate rồi mới gọi API.
 */
import type { MarketingBannerItem } from '@/types/api';

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8001/api/v1';

const FETCH_TIMEOUT_MS = 12000;
const isDev = process.env.NODE_ENV === 'development';
const disableCache =
  process.env.NEXT_PUBLIC_DISABLE_CACHE === '1' || process.env.DISABLE_CACHE === '1';
const REVALIDATE = isDev || disableCache ? 0 : 60;

export async function getInitialMarketingBanners(): Promise<MarketingBannerItem[] | null> {
  try {
    const res = await fetch(`${API_BASE}/marketing-banners/current`, {
      next: { revalidate: REVALIDATE },
      headers: { 'Content-Type': 'application/json' },
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    });
    if (!res.ok) return null;
    const data = (await res.json()) as { items?: MarketingBannerItem[] };
    if (!Array.isArray(data?.items)) return null;
    return data.items.filter((item) => (item.image_url || '').trim());
  } catch {
    return null;
  }
}
