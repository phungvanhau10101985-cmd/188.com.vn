/**
 * Google Shopping — Chiết khấu tự động (Automated discounts).
 * JWT pv2 trong URL → xác thực backend → hiển thị & khóa giá trên PDP / giỏ / checkout.
 * https://support.google.com/merchants/answer/15152429
 */

import { getApiBaseUrl, ngrokFetchHeaders } from '@/lib/api-base';

const STORAGE_KEY = '188_google_automated_discount_v1';
const SESSION_MS = 30 * 60 * 1000;
const CART_LOCK_MS = 48 * 60 * 60 * 1000;

/** Khoá công khai Google — dùng chung mọi merchant (Automated discounts). */
const GOOGLE_AUTOMATED_DISCOUNT_PUBLIC_KEY_PEM = `-----BEGIN PUBLIC KEY-----
MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAERUlUpxshr67EO66ZTX0Fpog0LEHc
nUnlSsIrOfroxTLu2XnigBK/lfYRxzQWq9K6nqsSjjYeea0T12r+y3nvqg==
-----END PUBLIC KEY-----`;

let cachedGoogleDiscountPublicKey: CryptoKey | null | undefined;

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

function base64UrlToBytes(input: string): Uint8Array {
  const pad = input.length % 4 === 0 ? '' : '='.repeat(4 - (input.length % 4));
  const b64 = input.replace(/-/g, '+').replace(/_/g, '/') + pad;
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

function roundPriceForCurrency(amount: number, currency: string): number {
  const cur = String(currency || '').trim().toUpperCase();
  if (cur === 'VND') return Math.max(0, Math.round(amount));
  return Math.max(0, Math.round(amount * 100) / 100);
}

function readPriorPriceFromPayload(payload: Record<string, unknown>): number | null {
  if (payload.pp == null) return null;
  const pp = Number(payload.pp);
  return Number.isFinite(pp) && pp > 0 ? pp : null;
}

function derivePriorPriceFromDp(
  payload: Record<string, unknown>,
  discountedPrice: number,
  currency: string,
): number | null {
  if (payload.dp == null) return null;
  const dp = Number(payload.dp);
  if (!Number.isFinite(dp) || dp <= 0 || dp >= 100) return null;
  const factor = 1 - dp / 100;
  if (factor <= 0) return null;
  return roundPriceForCurrency(discountedPrice / factor, currency);
}

async function importGoogleDiscountPublicKey(): Promise<CryptoKey | null> {
  if (cachedGoogleDiscountPublicKey !== undefined) return cachedGoogleDiscountPublicKey;
  if (typeof window === 'undefined' || !window.crypto?.subtle) {
    cachedGoogleDiscountPublicKey = null;
    return null;
  }
  try {
    const b64 = GOOGLE_AUTOMATED_DISCOUNT_PUBLIC_KEY_PEM.replace(/-----[^-]+-----/g, '').replace(/\s/g, '');
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i);
    cachedGoogleDiscountPublicKey = await window.crypto.subtle.importKey(
      'spki',
      bytes.buffer,
      { name: 'ECDSA', namedCurve: 'P-256' },
      false,
      ['verify'],
    );
  } catch {
    cachedGoogleDiscountPublicKey = null;
  }
  return cachedGoogleDiscountPublicKey;
}

function buildVerifyResponseFromPayload(
  payload: Record<string, unknown>,
  offerId?: string | null,
): GoogleAutomatedDiscountVerifyResponse | null {
  const exp = Number(payload.exp);
  if (!Number.isFinite(exp) || exp <= Math.floor(Date.now() / 1000)) return null;

  const tokenOfferId = String(payload.o || '').trim();
  const expected = String(offerId || '').trim();
  if (expected && tokenOfferId && !offerIdsMatch(tokenOfferId, expected)) return null;

  const priceRaw = Number(payload.p);
  if (!Number.isFinite(priceRaw) || priceRaw <= 0) return null;

  const currency = String(payload.c || 'VND').trim().toUpperCase() || 'VND';
  const price = roundPriceForCurrency(priceRaw, currency);
  let priorPrice = readPriorPriceFromPayload(payload);
  if (priorPrice == null) priorPrice = derivePriorPriceFromDp(payload, price, currency);
  if (priorPrice != null) priorPrice = roundPriceForCurrency(priorPrice, currency);

  return {
    valid: true,
    price,
    prior_price: priorPrice,
    currency,
    offer_id: tokenOfferId,
    merchant_id: String(payload.m || '').trim(),
    expires_at: exp,
  };
}

/** Fallback khi API backend chưa sẵn sàng — xác thực chữ ký ES256 trực tiếp trên trình duyệt. */
export async function verifyGoogleAutomatedDiscountTokenClient(
  token: string,
  offerId?: string | null,
): Promise<GoogleAutomatedDiscountVerifyResponse | null> {
  const raw = token.trim();
  const parts = raw.split('.');
  if (parts.length !== 3) return null;

  let header: Record<string, unknown>;
  let payload: Record<string, unknown>;
  try {
    header = JSON.parse(new TextDecoder().decode(base64UrlToBytes(parts[0]))) as Record<string, unknown>;
    payload = JSON.parse(new TextDecoder().decode(base64UrlToBytes(parts[1]))) as Record<string, unknown>;
  } catch {
    return null;
  }
  if (header.alg !== 'ES256' || header.typ !== 'JWT') return null;

  const key = await importGoogleDiscountPublicKey();
  if (!key) return null;

  const signed = new TextEncoder().encode(`${parts[0]}.${parts[1]}`);
  const sig = base64UrlToBytes(parts[2]);
  const ok = await window.crypto.subtle.verify(
    { name: 'ECDSA', hash: 'SHA-256' },
    key,
    sig,
    signed,
  );
  if (!ok) return null;

  return buildVerifyResponseFromPayload(payload, offerId);
}

export async function verifyGoogleAutomatedDiscountToken(
  token: string,
  offerId?: string | null,
): Promise<GoogleAutomatedDiscountVerifyResponse> {
  const base = getApiBaseUrl();
  try {
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
    if (res.ok) {
      return data as GoogleAutomatedDiscountVerifyResponse;
    }
    if (res.status === 404 || res.status === 503) {
      const clientVerified = await verifyGoogleAutomatedDiscountTokenClient(token, offerId);
      if (clientVerified) return clientVerified;
    }
    const detail = typeof data?.detail === 'string' ? data.detail : 'Không xác thực được giá chiết khấu Google.';
    throw new Error(detail);
  } catch (err) {
    const clientVerified = await verifyGoogleAutomatedDiscountTokenClient(token, offerId);
    if (clientVerified) return clientVerified;
    if (err instanceof Error) throw err;
    throw new Error('Không xác thực được giá chiết khấu Google.');
  }
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
