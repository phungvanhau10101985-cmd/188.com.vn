import { isHolidayThemeId, type HolidayThemeId } from '@/lib/holiday-themes';

export const HOLIDAY_PREVIEW_MS = 10 * 60 * 1000;
const PREVIEW_KEY = '188-holiday-admin-preview';

export type HolidayAdminPreview = {
  code: HolidayThemeId;
  expiresAt: number;
};

function hasAdminToken(): boolean {
  try {
    return Boolean(localStorage.getItem('admin_token'));
  } catch {
    return false;
  }
}

export function readHolidayAdminPreview(now = Date.now()): HolidayAdminPreview | null {
  if (!hasAdminToken()) return null;
  try {
    const raw = localStorage.getItem(PREVIEW_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw) as { code?: unknown; expiresAt?: unknown };
    const code = typeof data.code === 'string' ? data.code : null;
    if (!isHolidayThemeId(code)) return null;
    if (typeof data.expiresAt !== 'number' || data.expiresAt <= now) {
      localStorage.removeItem(PREVIEW_KEY);
      return null;
    }
    return { code, expiresAt: data.expiresAt };
  } catch {
    return null;
  }
}

export function startHolidayAdminPreview(code: HolidayThemeId, now = Date.now()): HolidayAdminPreview | null {
  if (!hasAdminToken()) return null;
  const next = { code, expiresAt: now + HOLIDAY_PREVIEW_MS };
  localStorage.setItem(PREVIEW_KEY, JSON.stringify(next));
  return next;
}

export function clearHolidayAdminPreview() {
  try {
    localStorage.removeItem(PREVIEW_KEY);
  } catch {
    /* trình duyệt chặn storage */
  }
}

export function formatPreviewRemaining(ms: number): string {
  const total = Math.max(0, Math.ceil(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}
