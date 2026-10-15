/**
 * SSR trạng thái sale lịch — banner trên cùng có chiều cao ngay từ HTML (tránh CLS).
 */
import type { SiteSaleCalendarState } from '@/types/api';

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8001/api/v1';

const FETCH_TIMEOUT_MS = 4000;
const isDev = process.env.NODE_ENV === 'development';
const disableCache =
  process.env.NEXT_PUBLIC_DISABLE_CACHE === '1' || process.env.DISABLE_CACHE === '1';
const REVALIDATE = isDev || disableCache ? 0 : 60;

export async function getInitialSiteSaleCalendar(): Promise<SiteSaleCalendarState | null> {
  try {
    const res = await fetch(`${API_BASE}/sale-calendar/current`, {
      next: { revalidate: REVALIDATE },
      headers: { 'Content-Type': 'application/json' },
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    });
    if (!res.ok) return null;
    const data = (await res.json()) as SiteSaleCalendarState;
    if (!data || typeof data.enabled !== 'boolean') return null;
    return data;
  } catch {
    return null;
  }
}
