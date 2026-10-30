import { getApiBaseUrl } from '@/lib/api-base';
import { isHolidayThemeId, type HolidayThemeId } from '@/lib/holiday-themes';

export type { HolidayThemeId };

export function formatHolidayYear(year: number | null | undefined, yearEnd?: number | null): string {
  if (!year) return '';
  if (yearEnd && yearEnd !== year) return `${year}–${yearEnd}`;
  return String(year);
}

export type PublicHolidayTheme = {
  theme: HolidayThemeId | null;
  year: number | null;
  yearEnd: number | null;
  years: Record<string, number>;
};

/** Bản xem trước của tài khoản shop đang đăng nhập. `undefined` = lỗi mạng, giữ trạng thái cũ. */
export async function fetchMineHolidayPreview(): Promise<{ theme: HolidayThemeId | null; expiresAt: number } | undefined> {
  if (typeof window === 'undefined') return undefined;
  let token = '';
  try {
    token = localStorage.getItem('access_token') || '';
  } catch {
    return { theme: null, expiresAt: 0 };
  }
  if (!token) return { theme: null, expiresAt: 0 };
  try {
    const res = await fetch(`${getApiBaseUrl()}/holiday-theme/mine`, {
      cache: 'no-store',
      headers: { Accept: 'application/json', Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return undefined;
    const data = (await res.json()) as { active_theme?: unknown; expires_at?: unknown };
    const theme =
      typeof data.active_theme === 'string' && isHolidayThemeId(data.active_theme) ? data.active_theme : null;
    const exp = typeof data.expires_at === 'number' ? data.expires_at : Number(data.expires_at);
    const expiresAt = Number.isFinite(exp) && exp > 0 ? (exp > 1e12 ? exp : exp * 1000) : 0;
    return { theme, expiresAt };
  } catch {
    return undefined;
  }
}

/** `undefined` = không gọi được API, giữ trạng thái đang có. */
export async function fetchPublicHolidayTheme(): Promise<PublicHolidayTheme | undefined> {
  try {
    const init: RequestInit & { next?: { revalidate: number } } = {
      headers: { Accept: 'application/json' },
    };
    if (typeof window === 'undefined') {
      const isDev = process.env.NODE_ENV === 'development';
      const disableCache =
        process.env.NEXT_PUBLIC_DISABLE_CACHE === '1' || process.env.DISABLE_CACHE === '1';
      init.next = { revalidate: isDev || disableCache ? 0 : 20 };
    } else {
      init.cache = 'no-store';
    }
    const res = await fetch(`${getApiBaseUrl()}/holiday-theme/public`, init);
    if (!res.ok) return undefined;
    const data = (await res.json()) as {
      active_theme?: unknown;
      event_year?: unknown;
      event_year_end?: unknown;
      occasion_years?: unknown;
    };
    const years: Record<string, number> = {};
    if (data.occasion_years && typeof data.occasion_years === 'object') {
      for (const [code, year] of Object.entries(data.occasion_years as Record<string, unknown>)) {
        if (typeof year === 'number') years[code] = year;
      }
    }
    const year = typeof data.event_year === 'number' ? data.event_year : null;
    const yearEnd = typeof data.event_year_end === 'number' ? data.event_year_end : year;
    return {
      theme: typeof data.active_theme === 'string' && isHolidayThemeId(data.active_theme) ? data.active_theme : null,
      year,
      yearEnd,
      years,
    };
  } catch {
    return undefined;
  }
}
