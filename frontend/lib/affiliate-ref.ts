const REF_COOKIE = '188_affiliate_ref';
const REF_ATTR_KEY = '188_affiliate_attr_done';

function cookieMaxAgeDays(): number {
  const raw = process.env.NEXT_PUBLIC_AFFILIATE_REF_COOKIE_DAYS;
  const n = raw ? Number(raw) : 30;
  return Number.isFinite(n) && n > 0 ? n : 30;
}

export function captureReferralFromUrl(search: string): void {
  if (typeof document === 'undefined') return;
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
  const ref = (params.get('ref') || '').trim().toUpperCase();
  if (!ref) return;
  const maxAge = cookieMaxAgeDays() * 86400;
  document.cookie = `${REF_COOKIE}=${encodeURIComponent(ref)}; path=/; max-age=${maxAge}; SameSite=Lax`;
}

export function getStoredReferralCode(): string | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${REF_COOKIE}=([^;]*)`));
  if (!match) return null;
  try {
    return decodeURIComponent(match[1]).trim().toUpperCase() || null;
  } catch {
    return null;
  }
}

export function markReferralAttributed(): void {
  try {
    sessionStorage.setItem(REF_ATTR_KEY, '1');
  } catch {
    /* noop */
  }
}

export function shouldTryAttributeReferral(): boolean {
  try {
    return sessionStorage.getItem(REF_ATTR_KEY) !== '1';
  } catch {
    return true;
  }
}

export function clearReferralAfterAttribute(): void {
  try {
    document.cookie = `${REF_COOKIE}=; path=/; max-age=0; SameSite=Lax`;
  } catch {
    /* noop */
  }
}

const DEFAULT_SITE_ORIGIN = 'https://188.com.vn';

function siteOrigin(): string {
  if (typeof window !== 'undefined' && window.location.origin) {
    return window.location.origin;
  }
  const raw = process.env.NEXT_PUBLIC_SITE_URL || process.env.NEXT_PUBLIC_FRONTEND_BASE_URL || DEFAULT_SITE_ORIGIN;
  return raw.replace(/\/$/, '');
}

/** Ghép `?ref=` (hoặc `&ref=`) vào URL bất kỳ — dùng khi affiliate copy/share link trang hiện tại. */
export function appendReferralToUrl(url: string, referralCode: string): string {
  const code = (referralCode || '').trim().toUpperCase();
  const trimmed = (url || '').trim();
  if (!code || !trimmed) return trimmed;
  try {
    const parsed = trimmed.startsWith('http://') || trimmed.startsWith('https://')
      ? new URL(trimmed)
      : new URL(trimmed, siteOrigin());
    parsed.searchParams.set('ref', code);
    return parsed.toString();
  } catch {
    const joiner = trimmed.includes('?') ? '&' : '?';
    return `${trimmed}${joiner}ref=${encodeURIComponent(code)}`;
  }
}
