/** Dữ liệu mã nhúng public từ API (SSR layout). */

import { getApiBaseUrl } from '@/lib/api-base';

/** Khớp backend `GoogleAdsWebConversions` — send_to AW-xxxx/label từ admin. */
export type GoogleAdsWebConversionsPublic = {
  pdp?: string;
  add_to_cart?: string;
  begin_checkout?: string;
  deposit_page?: string;
  purchase?: string;
};

export type PublicSiteEmbeds = {
  head: string[];
  body_open: string[];
  body_close: string[];
  /** Từ API — mã AW- trong admin (google/ads). Nếu có, gtag send_to chỉ dùng danh sách này. */
  googleAdsAwIds?: string[];
  /** Từ API — object send_to theo từng bược funnel; ưu tiên hơn NEXT_PUBLIC_* khi API có trường này. */
  googleAdsWebConversions?: GoogleAdsWebConversionsPublic;
  /** true khi chỉ có trường cũ `google_ads_pdp_conversion_send_to` — chỉ ép PDP từ admin, các bước khác vẫn dùng NEXT_PUBLIC_* */
  googleAdsWebConversionsLegacyPdpOnly?: boolean;
  /** Merchant Center ID — Google Customer Reviews opt-in; null/undefined = tắt. */
  googleCustomerReviewsMerchantId?: number | null;
};

const empty: PublicSiteEmbeds = { head: [], body_open: [], body_close: [] };

function parseWebConversionsFromJson(data: Record<string, unknown>): GoogleAdsWebConversionsPublic | undefined {
  const raw = data.google_ads_web_conversions;
  if (raw == null || typeof raw !== 'object' || Array.isArray(raw)) return undefined;
  const o = raw as Record<string, unknown>;
  const pick = (k: string) => String(o[k] ?? '').trim();
  return {
    pdp: pick('pdp'),
    add_to_cart: pick('add_to_cart'),
    begin_checkout: pick('begin_checkout'),
    deposit_page: pick('deposit_page'),
    purchase: pick('purchase'),
  };
}

export async function fetchPublicSiteEmbeds(): Promise<PublicSiteEmbeds> {
  const base = getApiBaseUrl();
  try {
    const res = await fetch(`${base}/embed-codes/public`, {
      next: { revalidate: 120 },
    });
    if (!res.ok) return empty;
    const data = (await res.json()) as Record<string, unknown>;
    const hasAwKey = 'google_ads_aw_ids' in data;
    const rawAw = data.google_ads_aw_ids;
    const googleAdsAwIds = hasAwKey
      ? Array.isArray(rawAw)
        ? rawAw
            .map((x) => String(x ?? '').trim().toUpperCase())
            .filter((s) => /^AW-\d+$/.test(s))
        : []
      : undefined;

    let googleAdsWebConversions = parseWebConversionsFromJson(data);
    let googleAdsWebConversionsLegacyPdpOnly = false;
    if (!googleAdsWebConversions && 'google_ads_pdp_conversion_send_to' in data) {
      const legacy = String(data.google_ads_pdp_conversion_send_to ?? '').trim();
      googleAdsWebConversions = { pdp: legacy };
      googleAdsWebConversionsLegacyPdpOnly = true;
    }

    const gcrRaw = data.google_customer_reviews_merchant_id;
    const gcrParsed =
      typeof gcrRaw === 'number'
        ? gcrRaw
        : Number.parseInt(String(gcrRaw ?? ''), 10);
    const googleCustomerReviewsMerchantId =
      Number.isFinite(gcrParsed) && gcrParsed > 0 ? gcrParsed : null;

    return {
      head: Array.isArray(data.head) ? data.head.filter(Boolean) : [],
      body_open: Array.isArray(data.body_open) ? data.body_open.filter(Boolean) : [],
      body_close: Array.isArray(data.body_close) ? data.body_close.filter(Boolean) : [],
      ...(googleAdsAwIds !== undefined ? { googleAdsAwIds } : {}),
      ...(googleAdsWebConversions !== undefined ? { googleAdsWebConversions } : {}),
      ...(googleAdsWebConversionsLegacyPdpOnly ? { googleAdsWebConversionsLegacyPdpOnly: true } : {}),
      ...(googleCustomerReviewsMerchantId != null ? { googleCustomerReviewsMerchantId } : {}),
    };
  } catch {
    return empty;
  }
}
