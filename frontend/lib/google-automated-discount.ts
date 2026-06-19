/**
 * Google Shopping — Chiết khấu tự động (Automated discounts).
 * JWT pv2 trong URL → xác thực backend → hiển thị & khóa giá trên PDP / giỏ / checkout.
 * https://support.google.com/merchants/answer/15152429
 */

import { getApiBaseUrl, ngrokFetchHeaders } from '@/lib/api-base';

const STORAGE_KEY = '188_google_automated_discount_v1';
const SESSION_MS = 30 * 60 * 1000;
const CART_LOCK_MS = 48 * 60 * 60 * 1000;

export const GOOGLE_AUTOMATED_DISCOUNT_UPDATED_EVENT = '188-google-automated-discount-updated';

function notifyGoogleAutomatedDiscountUpdated(): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new Event(GOOGLE_AUTOMATED_DISCOUNT_UPDATED_EVENT));
}

function offerIdsMatch(a: string | null | undefined, b: string | null | undefined): boolean {
  const left = String(a || '').trim();
  const right = String(b || '').trim();
  if (!left || !right) return false;
  return left === right || left.toLowerCase() === right.toLowerCase();
}

export type GoogleAutomatedDiscountRecord = {
  offerId: string;
  price: number;
  priorPrice: number | null;
  currency: string;
  token: string;
  sessionExpiresAt: number;
  cartLockExpiresAt: number;
  verifiedAt: number;
};

export type GoogleAutomatedDiscountVerifyResponse = {
  valid: boolean;
  price: number;
  prior_price?: number | null;
  currency: string;
  offer_id: string;
  merchant_id: string;
  expires_at: number;
};

function readStore(): Record<string, GoogleAutomatedDiscountRecord> {
  if (typeof window === 'undefined') return {};
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, GoogleAutomatedDiscountRecord>;
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function writeStore(store: Record<string, GoogleAutomatedDiscountRecord>) {
  if (typeof window === 'undefined') return;
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  } catch {
    /* ignore quota */
  }
}

export function extractPv2FromSearch(search: string): string | null {
  try {
    const token = new URLSearchParams(search).get('pv2');
    return token?.trim() || null;
  } catch {
    return null;
  }
}

export function extractPv2FromHref(href: string): string | null {
  try {
    const u = new URL(href, typeof window !== 'undefined' ? window.location.origin : 'https://188.com.vn');
    return extractPv2FromSearch(u.search);
  } catch {
    return null;
  }
}

export async function verifyGoogleAutomatedDiscountToken(
  token: string,
  offerId?: string | null,
): Promise<GoogleAutomatedDiscountVerifyResponse> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/google-merchant/automated-discount/verify`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...ngrokFetchHeaders(),
    },
    body: JSON.stringify({
      token,
      offer_id: offerId || undefined,
    }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof data?.detail === 'string' ? data.detail : 'Không xác thực được giá chiết khấu Google.';
    throw new Error(detail);
  }
  return data as GoogleAutomatedDiscountVerifyResponse;
}

export function saveGoogleAutomatedDiscount(
  verified: GoogleAutomatedDiscountVerifyResponse,
  token: string,
): GoogleAutomatedDiscountRecord {
  const now = Date.now();
  const jwtExpMs = verified.expires_at * 1000;
  const record: GoogleAutomatedDiscountRecord = {
    offerId: verified.offer_id,
    price: verified.price,
    priorPrice: verified.prior_price ?? null,
    currency: verified.currency,
    token,
    verifiedAt: now,
    sessionExpiresAt: Math.min(now + SESSION_MS, jwtExpMs),
    cartLockExpiresAt: Math.min(now + CART_LOCK_MS, jwtExpMs),
  };
  const store = readStore();
  store[record.offerId] = record;
  writeStore(store);
  notifyGoogleAutomatedDiscountUpdated();
  return record;
}

export function touchGoogleAutomatedDiscountSession(offerId: string): void {
  const store = readStore();
  const rec = store[offerId];
  if (!rec) return;
  const now = Date.now();
  rec.sessionExpiresAt = Math.min(now + SESSION_MS, rec.cartLockExpiresAt);
  store[offerId] = rec;
  writeStore(store);
}

export function markGoogleAutomatedDiscountCartLock(offerId: string): void {
  const store = readStore();
  const rec = store[offerId];
  if (!rec) return;
  const now = Date.now();
  const lockUntil = now + CART_LOCK_MS;
  rec.cartLockExpiresAt = Math.max(rec.cartLockExpiresAt, lockUntil);
  rec.sessionExpiresAt = Math.max(rec.sessionExpiresAt, rec.cartLockExpiresAt);
  store[offerId] = rec;
  writeStore(store);
}

export function getGoogleAutomatedDiscountForOffer(offerId: string | null | undefined): GoogleAutomatedDiscountRecord | null {
  const id = String(offerId || '').trim();
  if (!id) return null;
  const store = readStore();
  const direct = store[id];
  if (direct) {
    const active = validateActiveRecord(direct, id, store);
    if (active) return active;
  }
  for (const [key, rec] of Object.entries(store)) {
    if (!offerIdsMatch(key, id)) continue;
    const active = validateActiveRecord(rec, key, store);
    if (active) return active;
  }
  return null;
}

function validateActiveRecord(
  rec: GoogleAutomatedDiscountRecord,
  storeKey: string,
  store: Record<string, GoogleAutomatedDiscountRecord>,
): GoogleAutomatedDiscountRecord | null {
  const now = Date.now();
  if (now > rec.cartLockExpiresAt) {
    delete store[storeKey];
    writeStore(store);
    return null;
  }
  if (now > rec.sessionExpiresAt && now <= rec.cartLockExpiresAt) {
    return null;
  }
  return rec;
}

export function getGoogleAutomatedDiscountForProduct(
  product: { product_id?: string | null; code?: string | null },
): GoogleAutomatedDiscountRecord | null {
  const feedId = String(product.product_id || '').trim();
  if (feedId) {
    const hit = getGoogleAutomatedDiscountForOffer(feedId);
    if (hit) return hit;
  }
  const code = String(product.code || '').trim();
  if (code) {
    const hit = getGoogleAutomatedDiscountForOffer(code);
    if (hit) return hit;
  }
  return null;
}

export function getGoogleAutomatedDiscountCartLock(offerId: string | null | undefined): GoogleAutomatedDiscountRecord | null {
  const id = String(offerId || '').trim();
  if (!id) return null;
  const store = readStore();
  const rec = store[id];
  if (!rec) return null;
  if (Date.now() > rec.cartLockExpiresAt) {
    delete store[id];
    writeStore(store);
    return null;
  }
  return rec;
}

export function getActiveGoogleAutomatedDiscountToken(offerId: string | null | undefined): string | null {
  const rec = getGoogleAutomatedDiscountForOffer(offerId) ?? getGoogleAutomatedDiscountCartLock(offerId);
  return rec?.token ?? null;
}

export type ProductDisplayPricingLike = {
  displayPrice: number;
  compareAt: number | null;
  compareUnitPrice: number | null;
  savingsAmount: number;
  listPrice?: number;
};

export function applyGoogleAutomatedDiscountToPricing<T extends ProductDisplayPricingLike>(
  productOfferId: string | null | undefined,
  base: T,
  product?: { product_id?: string | null; code?: string | null },
): T {
  const rec =
    (product ? getGoogleAutomatedDiscountForProduct(product) : null) ??
    getGoogleAutomatedDiscountForOffer(productOfferId);
  if (!rec) return base;
  const displayPrice = rec.price;
  const compareAt =
    rec.priorPrice != null && rec.priorPrice > displayPrice
      ? rec.priorPrice
      : base.compareAt != null && base.compareAt > displayPrice
        ? base.compareAt
        : base.listPrice != null && base.listPrice > displayPrice
          ? base.listPrice
          : null;
  return {
    ...base,
    displayPrice,
    compareAt,
    compareUnitPrice: compareAt,
    savingsAmount: compareAt != null ? Math.max(0, compareAt - displayPrice) : base.savingsAmount,
  };
}

export async function capturePv2FromLocation(
  locationSearch: string,
  offerId?: string | null,
): Promise<GoogleAutomatedDiscountRecord | null> {
  const token = extractPv2FromSearch(locationSearch);
  if (!token) return null;
  const verified = await verifyGoogleAutomatedDiscountToken(token, offerId || undefined);
  return saveGoogleAutomatedDiscount(verified, token);
}
