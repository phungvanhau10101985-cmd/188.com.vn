import { getApiBaseUrl } from '@/lib/api-base';
import { isHolidayThemeId, type HolidayThemeId } from '@/lib/holiday-themes';

export const HOLIDAY_PREVIEW_MS = 10 * 60 * 1000;
const PREVIEW_KEY = '188-holiday-admin-preview';

export type HolidayAdminPreview = {
  code: HolidayThemeId;
  expiresAt: number;
};

type StoredPreview = {
  code: HolidayThemeId;
  expiresAt: number;
  grantToken: string | null;
};

/** Mã đã được API xác nhận trong phiên tab này. Không tin cờ tự ghi trong localStorage. */
let trustedGrantToken: string | null = null;

function hasAdminToken(): boolean {
  try {
    return Boolean(localStorage.getItem('admin_token'));
  } catch {
    return false;
  }
}

function parseStored(now: number): StoredPreview | null {
  try {
    const raw = localStorage.getItem(PREVIEW_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw) as { code?: unknown; expiresAt?: unknown; grantToken?: unknown };
    const code = typeof data.code === 'string' ? data.code : null;
    if (!isHolidayThemeId(code)) return null;
    if (typeof data.expiresAt !== 'number' || data.expiresAt <= now) {
      localStorage.removeItem(PREVIEW_KEY);
      return null;
    }
    const grantToken = typeof data.grantToken === 'string' && data.grantToken.trim() ? data.grantToken.trim() : null;
    return { code, expiresAt: data.expiresAt, grantToken };
  } catch {
    return null;
  }
}

export function readHolidayAdminPreview(now = Date.now()): HolidayAdminPreview | null {
  const parsed = parseStored(now);
  if (!parsed) return null;
  if (parsed.grantToken) {
    if (parsed.grantToken !== trustedGrantToken) return null;
    return { code: parsed.code, expiresAt: parsed.expiresAt };
  }
  if (!hasAdminToken()) return null;
  return { code: parsed.code, expiresAt: parsed.expiresAt };
}

/** Bản xem trước do cửa hàng giữ sau khi admin mở tab 188.com.vn. Cần gọi API xác nhận lại. */
export function readHolidayPreviewGrant(now = Date.now()): { code: HolidayThemeId; expiresAt: number; token: string } | null {
  const parsed = parseStored(now);
  if (!parsed?.grantToken) return null;
  return { code: parsed.code, expiresAt: parsed.expiresAt, token: parsed.grantToken };
}

export function startHolidayAdminPreview(code: HolidayThemeId, now = Date.now()): HolidayAdminPreview | null {
  if (!hasAdminToken()) return null;
  const next = { code, expiresAt: now + HOLIDAY_PREVIEW_MS };
  localStorage.setItem(PREVIEW_KEY, JSON.stringify(next));
  return next;
}

export function rememberHolidayPreviewGrant(
  code: HolidayThemeId,
  expiresAt: number,
  token: string,
): HolidayAdminPreview {
  const grantToken = token.trim();
  trustedGrantToken = grantToken;
  const next = { code, expiresAt };
  localStorage.setItem(PREVIEW_KEY, JSON.stringify({ ...next, grantToken }));
  return next;
}

export async function acceptHolidayPreviewGrant(
  code: HolidayThemeId,
  token: string,
): Promise<HolidayAdminPreview | null> {
  const trimmed = token.trim();
  if (!trimmed) return null;
  try {
    const res = await fetch(
      `${getApiBaseUrl()}/holiday-theme/preview?token=${encodeURIComponent(trimmed)}`,
      { cache: 'no-store', headers: { Accept: 'application/json' } },
    );
    if (!res.ok) return null;
    const data = (await res.json()) as { code?: unknown; expires_at?: unknown };
    const returned = typeof data.code === 'string' ? data.code : null;
    if (returned !== code || !isHolidayThemeId(returned)) return null;
    const exp = typeof data.expires_at === 'number' ? data.expires_at : Number(data.expires_at);
    if (!Number.isFinite(exp)) return null;
    const expiresAt = exp > 1e12 ? exp : exp * 1000;
    if (expiresAt <= Date.now()) return null;
    return rememberHolidayPreviewGrant(code, expiresAt, trimmed);
  } catch {
    return null;
  }
}

export function clearHolidayAdminPreview() {
  trustedGrantToken = null;
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
