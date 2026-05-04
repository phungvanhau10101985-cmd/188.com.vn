'use client';

export type FacebookCapiPayload = {
  event_name: string;
  event_id?: string;
  event_time?: number;
  action_source?: string;
  /** URL nguồn — mặc định `location.href` nếu không gửi */
  event_source_url?: string;
  custom_data?: Record<string, unknown>;
  user_data?: Record<string, unknown>;
};

function readCookieRaw(name: string): string | null {
  if (typeof document === 'undefined') return null;
  const hit = document.cookie.split('; ').find((row) => row.startsWith(`${name}=`));
  if (!hit) return null;
  const v = hit.slice(name.length + 1);
  try {
    return decodeURIComponent(v);
  } catch {
    return v;
  }
}

/** fbp / fbc tăng khớp Pixel ↔ CAPI */
function browserMetaCookiesUserData(): Record<string, string> | undefined {
  const fbp = readCookieRaw('_fbp');
  const fbc = readCookieRaw('_fbc');
  const o: Record<string, string> = {};
  if (fbp) o.fbp = fbp;
  if (fbc) o.fbc = fbc;
  return Object.keys(o).length ? o : undefined;
}

export function newMetaEventId(prefix: string): string {
  const p = prefix.replace(/[^a-zA-Z0-9_]/g, '').slice(0, 16) || 'e';
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return `${p}_${crypto.randomUUID()}`;
    }
  } catch {
    /* ignore */
  }
  return `${p}_${Date.now()}_${Math.random().toString(36).slice(2, 14)}`;
}

/**
 * Gửi CAPI qua route Next (`/api/facebook-capi`) — Bearer chỉ có trên server, không lộ ra trình duyệt.
 */
export async function sendFacebookCapiFromBrowser(
  payload: FacebookCapiPayload,
  opts?: { keepalive?: boolean }
): Promise<void> {
  if (typeof window === 'undefined') return;
  const fromCookies = browserMetaCookiesUserData();
  const mergedUser: Record<string, unknown> = {
    ...(fromCookies || {}),
    ...(payload.user_data && typeof payload.user_data === 'object' ? payload.user_data : {}),
  };
  const user_data = Object.keys(mergedUser).length ? mergedUser : undefined;
  const body: FacebookCapiPayload = {
    ...payload,
    action_source: payload.action_source || 'website',
    event_source_url: payload.event_source_url ?? window.location.href,
    user_data,
  };
  try {
    await fetch(`${window.location.origin}/api/facebook-capi`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(body),
      keepalive: opts?.keepalive === true,
    });
  } catch {
    /* fire-and-forget */
  }
}
