'use client';

import { normalizeProductImageUrl } from '@/lib/product-gallery-merge';

const reportedKeys = new Set<string>();

function key(productId: number, url: string) {
  return `${productId}\n${url}`;
}

/** Báo ảnh không tải được — Next server gọi backend xác minh 404 rồi gỡ URL khỏi DB (cần BROKEN_MEDIA_PURGE_SECRET). */
export function reportUnreachableProductMedia(productId: number, rawUrl: string): void {
  const id = typeof productId === 'number' && Number.isFinite(productId) ? productId : NaN;
  const u = normalizeProductImageUrl(rawUrl.trim()) || rawUrl.trim();
  if (!Number.isFinite(id) || id < 1 || u.length < 8) return;
  const k = key(id, u);
  if (reportedKeys.has(k)) return;
  reportedKeys.add(k);
  fetch('/api/report-broken-product-media', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ productId: id, url: u }),
    keepalive: true,
  }).catch(() => {
    reportedKeys.delete(k);
  });
}
