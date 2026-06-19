/** Google Customer Reviews — opt-in khảo sát sau đơn hàng (Merchant Center). */

export const GCR_SHOW_ORDER_SESSION_PREFIX = '188_gcr_show_order_';
export const GCR_HANDLED_ORDER_SESSION_PREFIX = '188_gcr_handled_order_';

export type GoogleCustomerReviewsHandledOutcome = 'accepted' | 'declined';

export function isGoogleCustomerReviewsHandled(orderId: number): boolean {
  if (typeof sessionStorage === 'undefined' || !Number.isFinite(orderId)) return false;
  try {
    return sessionStorage.getItem(`${GCR_HANDLED_ORDER_SESSION_PREFIX}${orderId}`) != null;
  } catch {
    return false;
  }
}

export function markGoogleCustomerReviewsHandled(
  orderId: number,
  outcome: GoogleCustomerReviewsHandledOutcome,
): void {
  if (typeof sessionStorage === 'undefined' || !Number.isFinite(orderId)) return;
  try {
    sessionStorage.setItem(`${GCR_HANDLED_ORDER_SESSION_PREFIX}${orderId}`, outcome);
    sessionStorage.removeItem(`${GCR_SHOW_ORDER_SESSION_PREFIX}${orderId}`);
  } catch {
    /* private mode */
  }
}

export function markGoogleCustomerReviewsForOrder(orderId: number): void {
  if (typeof sessionStorage === 'undefined' || !Number.isFinite(orderId)) return;
  try {
    sessionStorage.setItem(`${GCR_SHOW_ORDER_SESSION_PREFIX}${orderId}`, '1');
  } catch {
    /* private mode */
  }
}

export function shouldShowGoogleCustomerReviewsForOrder(
  orderId: number,
  createdAt?: string | null,
  maxAgeHours = 48,
): boolean {
  if (isGoogleCustomerReviewsHandled(orderId)) return false;

  if (typeof sessionStorage !== 'undefined') {
    try {
      if (sessionStorage.getItem(`${GCR_SHOW_ORDER_SESSION_PREFIX}${orderId}`) === '1') {
        return true;
      }
    } catch {
      /* ignore */
    }
  }
  if (!createdAt) return false;
  const t = new Date(createdAt).getTime();
  if (!Number.isFinite(t)) return false;
  return Date.now() - t < maxAgeHours * 60 * 60 * 1000;
}

const POST_DEPOSIT_ORDER_STATUSES = new Set([
  'deposit_paid',
  'confirmed',
  'processing',
  'shipping',
  'delivered',
  'completed',
]);

function depositPaidAmount(order: { deposit_paid?: number | string | null }): number {
  const v = order.deposit_paid;
  if (v == null) return 0;
  if (typeof v === 'number') return Number.isFinite(v) && v > 0 ? v : 0;
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

/**
 * Đơn cần cọc: chỉ hiện khảo sát sau khi đã cọc (hoặc đơn không cọc: ngay sau đặt hàng).
 */
export function isOrderEligibleForGoogleReviewsOptIn(order: {
  requires_deposit?: boolean;
  status?: string;
  deposit_paid?: number | string | null;
}): boolean {
  const status = (order.status || '').trim();
  if (status === 'cancelled') return false;
  if (!order.requires_deposit) return true;
  if (depositPaidAmount(order) > 0) return true;
  return POST_DEPOSIT_ORDER_STATUSES.has(status);
}

export function clearGoogleCustomerReviewsShowFlag(orderId: number): void {
  if (typeof sessionStorage === 'undefined') return;
  try {
    sessionStorage.removeItem(`${GCR_SHOW_ORDER_SESSION_PREFIX}${orderId}`);
  } catch {
    /* ignore */
  }
}

function maskEmail(email: string): string {
  const trimmed = email.trim();
  const at = trimmed.indexOf('@');
  if (at <= 0) return trimmed;
  const local = trimmed.slice(0, at);
  const domain = trimmed.slice(at + 1);
  if (local.length <= 2) return `${local[0] ?? ''}***@${domain}`;
  return `${local.slice(0, 2)}***@${domain}`;
}

/** Kiểu hiển thị popup Google — dùng hộp giữa màn hình (desktop & mobile), tránh BOTTOM_TRAY che footer. */
export function googleCustomerReviewsOptInStyle(): string {
  return 'CENTER_DIALOG';
}

export function isLikelyMobileViewport(): boolean {
  if (typeof window === 'undefined') return false;
  return window.matchMedia('(max-width: 767px)').matches;
}

export function googleCustomerReviewsPromptDelayMs(): number {
  return isLikelyMobileViewport() ? 1200 : 900;
}

export { maskEmail as maskEmailForGoogleCustomerReviews };

/** ISO 3166-1 alpha-2 — mặc định giao trong Việt Nam. */
export function deliveryCountryForGoogleReviews(_order?: { customer_address?: string | null }): string {
  return 'VN';
}

export function estimatedDeliveryDateForGoogleReviews(order: {
  estimated_delivery?: string | null;
  created_at?: string | null;
}): string {
  const raw = order.estimated_delivery || order.created_at;
  const base = raw ? new Date(raw) : new Date();
  const d = Number.isFinite(base.getTime()) ? base : new Date();
  if (!order.estimated_delivery) {
    d.setDate(d.getDate() + 7);
  }
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}
