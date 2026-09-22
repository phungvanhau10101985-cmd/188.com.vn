export type VnSharePlatform = 'facebook' | 'zalo' | 'messenger' | 'tiktok' | 'copy';

export type VnSharePlatformMeta = {
  id: VnSharePlatform;
  label: string;
  hint?: string;
  /** Màu nền icon — dùng inline style (không phụ thuộc Tailwind JIT). */
  bg: string;
  color: string;
};

export const VN_SHARE_PLATFORMS: VnSharePlatformMeta[] = [
  { id: 'facebook', label: 'Facebook', bg: '#1877F2', color: '#fff' },
  { id: 'zalo', label: 'Zalo', bg: '#0068FF', color: '#fff' },
  { id: 'messenger', label: 'Messenger', bg: 'linear-gradient(135deg, #00B2FF 0%, #006AFF 100%)', color: '#fff' },
  { id: 'tiktok', label: 'TikTok', hint: 'Copy link', bg: '#111111', color: '#fff' },
  { id: 'copy', label: 'Copy link', bg: '#f3f4f6', color: '#1f2937' },
];

function isMobileUa(): boolean {
  if (typeof navigator === 'undefined') return false;
  return /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
}

function isAndroidUa(): boolean {
  if (typeof navigator === 'undefined') return false;
  return /Android/i.test(navigator.userAgent);
}

function isIosUa(): boolean {
  if (typeof navigator === 'undefined') return false;
  return /iPhone|iPad|iPod/i.test(navigator.userAgent);
}

export function buildVnShareHref(platform: Exclude<VnSharePlatform, 'copy' | 'tiktok'>, url: string): string {
  const encodedUrl = encodeURIComponent(url);
  switch (platform) {
    case 'facebook':
      return `https://www.facebook.com/sharer/sharer.php?u=${encodedUrl}`;
    case 'zalo':
      return `https://zalo.me/share?url=${encodedUrl}`;
    case 'messenger':
      if (isMobileUa()) {
        return `fb-messenger://share/?link=${encodedUrl}`;
      }
      return `https://www.facebook.com/dialog/send?link=${encodedUrl}&redirect_uri=${encodedUrl}&display=popup`;
    default:
      return url;
  }
}

/** Deep link / Android intent — mở app đã cài. */
function buildVnShareAppHref(
  platform: Exclude<VnSharePlatform, 'copy' | 'tiktok'>,
  url: string,
): string | null {
  const encodedUrl = encodeURIComponent(url);
  const web = buildVnShareHref(platform, url);
  const encodedWeb = encodeURIComponent(web);

  if (platform === 'facebook') {
    if (isAndroidUa()) {
      return `intent://www.facebook.com/sharer/sharer.php?u=${encodedUrl}#Intent;scheme=https;package=com.facebook.katana;S.browser_fallback_url=${encodedWeb};end`;
    }
    if (isIosUa()) {
      return `fb://sharer/sharer.php?u=${encodedUrl}`;
    }
    return null;
  }

  if (platform === 'zalo') {
    if (isAndroidUa()) {
      return `intent://share?url=${encodedUrl}#Intent;scheme=zalo;package=com.zing.zalo;S.browser_fallback_url=${encodedWeb};end`;
    }
    if (isIosUa()) {
      return `zalo://share?url=${encodedUrl}`;
    }
    return null;
  }

  if (platform === 'messenger') {
    if (isAndroidUa()) {
      return `intent://share/?link=${encodedUrl}#Intent;scheme=fb-messenger;package=com.facebook.orca;S.browser_fallback_url=${encodedWeb};end`;
    }
    if (isIosUa()) {
      return `fb-messenger://share/?link=${encodedUrl}`;
    }
    return null;
  }

  return null;
}

function openWebShare(href: string) {
  const popup = window.open(href, '_blank', 'noopener,noreferrer,width=560,height=640');
  if (!popup) window.location.href = href;
}

function openAppThenFallback(appHref: string, webHref: string) {
  let handedOff = false;
  const onHidden = () => {
    if (document.hidden) handedOff = true;
  };
  document.addEventListener('visibilitychange', onHidden);
  window.addEventListener('pagehide', onHidden, { once: true });

  window.location.href = appHref;

  window.setTimeout(() => {
    document.removeEventListener('visibilitychange', onHidden);
    if (handedOff || document.hidden) return;
    openWebShare(webHref);
  }, 1100);
}

type ToastFn = (toast: {
  title: string;
  description?: string;
  variant: 'success' | 'error' | 'info';
  durationMs?: number;
}) => void;

async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
    throw new Error('clipboard-unavailable');
  } catch {
    try {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.position = 'fixed';
      ta.style.left = '-9999px';
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand('copy');
      document.body.removeChild(ta);
      return ok;
    } catch {
      return false;
    }
  }
}

/**
 * Mở share sheet hệ thống (app đã cài: Zalo, Facebook, Messenger…).
 * `true` = đã xử lý (kể cả user hủy). `false` = cần sheet tùy chỉnh.
 */
export async function tryNativeShare(url: string, title?: string): Promise<boolean> {
  const trimmed = (url || '').trim();
  if (!trimmed) return false;
  if (typeof navigator === 'undefined' || typeof navigator.share !== 'function') return false;

  const payload: ShareData = {
    title: title || '188.com.vn',
    url: trimmed,
  };
  if (title) payload.text = title;

  try {
    if (navigator.canShare && !navigator.canShare(payload)) return false;
    await navigator.share(payload);
    return true;
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') return true;
    if (err instanceof Error && err.name === 'AbortError') return true;
    return false;
  }
}

export async function shareViaVnPlatform(
  platform: VnSharePlatform,
  url: string,
  title: string | undefined,
  pushToast: ToastFn,
): Promise<void> {
  const trimmed = (url || '').trim();
  if (!trimmed) {
    pushToast({ title: 'Không có link để chia sẻ', variant: 'error' });
    return;
  }

  if (platform === 'copy' || platform === 'tiktok') {
    const ok = await copyText(trimmed);
    if (ok) {
      pushToast({
        title: platform === 'tiktok' ? 'Đã copy link' : 'Đã copy link giới thiệu',
        description: platform === 'tiktok' ? 'Dán link vào TikTok, bio hoặc tin nhắn.' : undefined,
        variant: 'success',
        durationMs: 2800,
      });
    } else {
      pushToast({ title: 'Không copy được link', variant: 'error' });
    }
    return;
  }

  const webHref = buildVnShareHref(platform, trimmed);
  if (isMobileUa()) {
    const appHref = buildVnShareAppHref(platform, trimmed);
    if (appHref) {
      openAppThenFallback(appHref, webHref);
      return;
    }
    window.location.href = webHref;
    return;
  }

  openWebShare(webHref);
  if (title && platform === 'facebook') {
    void title;
  }
}
