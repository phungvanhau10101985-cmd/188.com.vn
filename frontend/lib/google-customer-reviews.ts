/** Google Customer Reviews — opt-in khảo sát sau đơn hàng (Merchant Center). */

export const GCR_SHOW_ORDER_SESSION_PREFIX = '188_gcr_show_order_';

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

export function clearGoogleCustomerReviewsShowFlag(orderId: number): void {
  if (typeof sessionStorage === 'undefined') return;
  try {
    sessionStorage.removeItem(`${GCR_SHOW_ORDER_SESSION_PREFIX}${orderId}`);
  } catch {
    /* ignore */
  }
}

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
