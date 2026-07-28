/**
 * Server-only: xác thực JWT pv2 từ URL quảng cáo Mua sắm (SSR PDP).
 * Gọi backend /google-merchant/automated-discount/verify — không dùng trên client.
 */

import { getApiBaseUrl } from '@/lib/api-base';
import type { GoogleAutomatedDiscountSsrPayload } from '@/lib/google-automated-discount';

function extractPv2FromSearchParams(
  searchParams: Record<string, string | string[] | undefined> | null | undefined,
): string | null {
  if (!searchParams) return null;
  const raw = searchParams.pv2;
  if (raw == null) return null;
  const token = Array.isArray(raw) ? raw[0] : raw;
  const trimmed = String(token || '').trim();
  return trimmed || null;
}

/**
 * Verify pv2 trên RSC. Trả null nếu thiếu token / lỗi / không khớp offer.
 */
export async function verifyPv2ForProductPage(
  searchParams: Record<string, string | string[] | undefined> | null | undefined,
  offerId: string | null | undefined,
): Promise<GoogleAutomatedDiscountSsrPayload | null> {
  const token = extractPv2FromSearchParams(searchParams);
  if (!token) return null;

  const base = getApiBaseUrl();
  try {
    const res = await fetch(`${base}/google-merchant/automated-discount/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        token,
        offer_id: String(offerId || '').trim() || undefined,
      }),
      cache: 'no-store',
    });
    if (!res.ok) return null;
    const data = (await res.json().catch(() => null)) as Record<string, unknown> | null;
    if (!data || data.valid === false) return null;

    const price = Number(data.price);
    if (!Number.isFinite(price) || price <= 0) return null;

    const offer_id = String(data.offer_id || '').trim();
    if (!offer_id) return null;

    const expires_at = Number(data.expires_at);
    if (!Number.isFinite(expires_at) || expires_at <= Math.floor(Date.now() / 1000)) return null;

    let prior_price: number | null = null;
    if (data.prior_price != null) {
      const pp = Number(data.prior_price);
      if (Number.isFinite(pp) && pp > 0) prior_price = pp;
    }

    return {
      price,
      prior_price,
      currency: String(data.currency || 'VND').trim().toUpperCase() || 'VND',
      offer_id,
      token,
      expires_at,
    };
  } catch {
    return null;
  }
}
