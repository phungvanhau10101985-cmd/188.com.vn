import { getApiBaseUrl } from '@/lib/api-base';

const seenAt = new Map<string, number>();
const DEDUPE_MS = 60_000;

export type SiteErrorReport = {
  message?: string;
  stack?: string;
  digest?: string;
  path?: string;
};

function isNoise(message: string, stack: string): boolean {
  const blob = `${message}\n${stack}`.toLowerCase();
  return (
    blob.includes('resizeobserver loop') ||
    blob.includes('script error.') ||
    blob.includes('chrome-extension://') ||
    blob.includes('moz-extension://') ||
    blob.includes('aborterror') ||
    blob.includes('site-errors/report') ||
    blob.includes('java object is gone') ||
    blob.includes('webkit.messagehandlers') ||
    blob.includes('zalojsv2') ||
    blob.includes('loading chunk') ||
    blob.includes('chunkloaderror') ||
    blob.includes("failed to read the 'localstorage' property") ||
    blob.includes('access is denied for this document')
  );
}

/** Gửi lỗi trình duyệt về API. Lỗi lặp trong 60 giây chỉ gửi một lần. */
export function reportSiteError(input: SiteErrorReport): void {
  if (typeof window === 'undefined') return;
  const message = (input.message || '').trim();
  const stack = input.stack || '';
  if (!message || isNoise(message, stack)) return;
  const path = (input.path || `${window.location.pathname}${window.location.search}`).slice(0, 500);
  const key = `${message.slice(0, 180)}|${path}`;
  const now = Date.now();
  if (now - (seenAt.get(key) || 0) < DEDUPE_MS) return;
  seenAt.set(key, now);

  const body = JSON.stringify({
    message: message.slice(0, 2000),
    stack: stack.slice(0, 8000),
    path,
    digest: (input.digest || '').slice(0, 80),
    kind: 'web',
  });
  const url = `${getApiBaseUrl()}/site-errors/report`;
  try {
    void fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
      keepalive: true,
      credentials: 'omit',
    }).catch(() => undefined);
  } catch {
    /* không làm gián đoạn trang */
  }
}
