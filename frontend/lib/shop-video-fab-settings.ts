import { getApiBaseUrl, ngrokFetchHeaders } from '@/lib/api-base';

/** Mặc định khớp backend (`bottom-36` + thanh nav mobile ≈ 144px, `bottom-4` / `right-4`, desktop `bottom-10` / `right-8`). */
export const DEFAULT_SHOP_VIDEO_FAB_SETTINGS: ShopVideoFabPublicSettings = {
  right_mobile_px: 16,
  bottom_mobile_px_no_nav: 16,
  bottom_mobile_px_with_nav: 144,
  right_desktop_px: 32,
  bottom_desktop_px: 40,
};

export interface ShopVideoFabPublicSettings {
  right_mobile_px: number;
  bottom_mobile_px_no_nav: number;
  bottom_mobile_px_with_nav: number;
  right_desktop_px: number;
  bottom_desktop_px: number;
}

const FAB_SETTINGS_TTL_MS = 60_000;
let fabSettingsMem: { expiresAt: number; value: ShopVideoFabPublicSettings } | null = null;
let fabSettingsInflight: Promise<ShopVideoFabPublicSettings> | null = null;

/** Không auth — gọi từ client FAB (fail → defaults). */
export async function fetchShopVideoFabPublicSettings(): Promise<ShopVideoFabPublicSettings> {
  const now = Date.now();
  if (fabSettingsMem && fabSettingsMem.expiresAt > now) {
    return fabSettingsMem.value;
  }
  if (fabSettingsInflight) return fabSettingsInflight;

  const url = `${getApiBaseUrl()}/shop-video-fab/public`;
  fabSettingsInflight = (async () => {
    try {
      const res = await fetch(url, {
        headers: { Accept: 'application/json', ...ngrokFetchHeaders() },
      });
      if (!res.ok) return DEFAULT_SHOP_VIDEO_FAB_SETTINGS;
      const data = (await res.json()) as Partial<ShopVideoFabPublicSettings>;
      const value: ShopVideoFabPublicSettings = {
        right_mobile_px: clampPx(data.right_mobile_px, DEFAULT_SHOP_VIDEO_FAB_SETTINGS.right_mobile_px),
        bottom_mobile_px_no_nav: clampPx(
          data.bottom_mobile_px_no_nav,
          DEFAULT_SHOP_VIDEO_FAB_SETTINGS.bottom_mobile_px_no_nav,
        ),
        bottom_mobile_px_with_nav: clampPx(
          data.bottom_mobile_px_with_nav,
          DEFAULT_SHOP_VIDEO_FAB_SETTINGS.bottom_mobile_px_with_nav,
        ),
        right_desktop_px: clampPx(data.right_desktop_px, DEFAULT_SHOP_VIDEO_FAB_SETTINGS.right_desktop_px),
        bottom_desktop_px: clampPx(data.bottom_desktop_px, DEFAULT_SHOP_VIDEO_FAB_SETTINGS.bottom_desktop_px),
      };
      fabSettingsMem = { expiresAt: Date.now() + FAB_SETTINGS_TTL_MS, value };
      return value;
    } catch {
      return DEFAULT_SHOP_VIDEO_FAB_SETTINGS;
    } finally {
      fabSettingsInflight = null;
    }
  })();
  return fabSettingsInflight;
}

function clampPx(raw: unknown, fallback: number): number {
  const n = typeof raw === 'number' ? raw : Number(raw);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(400, Math.max(0, Math.round(n)));
}
