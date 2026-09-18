import { getApiBaseUrl } from '@/lib/api-base';
import { cdnUrl } from '@/lib/cdn-url';

/**
 * Logo / favicon / PWA / OG — ảnh vuông trên Bunny Pull Zone (đồng bộ file local `favicon.png` + `app/icon.png`).
 */
export const APP_WEB_ICON_URL = cdnUrl('/site/20260502/logo_1x1_0584d3f73e4a.png');

export type CurrentAppWebIcon = {
  icon_url: string;
  default_icon_url: string;
  is_sale: boolean;
  kind?: 'sale' | null;
  campaign_key?: string | null;
  date_key?: string | null;
  discount_percent?: number | null;
  event_date?: string | null;
  event_label?: string | null;
  phase?: string | null;
  version?: number | null;
};

const ICON_MEM_TTL_MS = 60_000;
let iconMemCache: { expiresAt: number; value: CurrentAppWebIcon } | null = null;
let iconInflight: Promise<CurrentAppWebIcon> | null = null;

function fallbackIcon(): CurrentAppWebIcon {
  return {
    icon_url: APP_WEB_ICON_URL,
    default_icon_url: APP_WEB_ICON_URL,
    is_sale: false,
  };
}

export async function fetchCurrentAppWebIcon(): Promise<CurrentAppWebIcon> {
  if (process.env.NEXT_PHASE === 'phase-production-build') {
    return fallbackIcon();
  }
  const now = Date.now();
  const hit = iconMemCache;
  if (hit && hit.expiresAt > now) {
    return hit.value;
  }
  if (iconInflight) {
    return iconInflight;
  }
  const base = getApiBaseUrl();
  iconInflight = (async () => {
    try {
      const res = await fetch(`${base}/marketing-icons/current`, {
        next: { revalidate: 120 },
        signal: AbortSignal.timeout(8000),
      });
      if (!res.ok) return fallbackIcon();
      const data = (await res.json()) as CurrentAppWebIcon;
      const iconUrl = String(data.icon_url || '').trim() || APP_WEB_ICON_URL;
      const value: CurrentAppWebIcon = {
        ...data,
        icon_url: iconUrl,
        default_icon_url: String(data.default_icon_url || '').trim() || APP_WEB_ICON_URL,
        is_sale: Boolean(data.is_sale),
      };
      iconMemCache = { expiresAt: Date.now() + ICON_MEM_TTL_MS, value };
      return value;
    } catch {
      return fallbackIcon();
    } finally {
      iconInflight = null;
    }
  })();
  return iconInflight;
}

export async function resolveAppWebIconUrl(): Promise<string> {
  const current = await fetchCurrentAppWebIcon();
  return current.icon_url || APP_WEB_ICON_URL;
}
