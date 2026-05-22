export type VnSharePlatform = 'facebook' | 'zalo' | 'messenger' | 'tiktok' | 'copy';

export type VnSharePlatformMeta = {
  id: VnSharePlatform;
  label: string;
  hint?: string;
  bgClass: string;
  textClass?: string;
};

export const VN_SHARE_PLATFORMS: VnSharePlatformMeta[] = [
  { id: 'facebook', label: 'Facebook', bgClass: 'bg-[#1877F2]', textClass: 'text-white' },
  { id: 'zalo', label: 'Zalo', bgClass: 'bg-[#0068FF]', textClass: 'text-white' },
  { id: 'messenger', label: 'Messenger', bgClass: 'bg-gradient-to-br from-[#00B2FF] to-[#006AFF]', textClass: 'text-white' },
  { id: 'tiktok', label: 'TikTok', hint: 'Copy link', bgClass: 'bg-black', textClass: 'text-white' },
  { id: 'copy', label: 'Copy link', bgClass: 'bg-gray-100', textClass: 'text-gray-800' },
];

function isMobileUa(): boolean {
  if (typeof navigator === 'undefined') return false;
  return /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
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
        return `fb-messenger://share?link=${encodedUrl}`;
      }
      return `https://www.facebook.com/dialog/send?link=${encodedUrl}&redirect_uri=${encodedUrl}&display=popup`;
    default:
      return url;
  }
}

type ToastFn = (opts: {
  title: string;
  description?: string;
  variant?: 'success' | 'error' | 'info';
  durationMs?: number;
}) => void;

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
    try {
      await navigator.clipboard.writeText(trimmed);
      pushToast({
        title: platform === 'tiktok' ? 'Đã copy link' : 'Đã copy link giới thiệu',
        description: platform === 'tiktok' ? 'Dán link vào TikTok, bio hoặc tin nhắn.' : undefined,
        variant: 'success',
        durationMs: 2800,
      });
    } catch {
      pushToast({ title: 'Không copy được link', variant: 'error' });
    }
    return;
  }

  const href = buildVnShareHref(platform, trimmed);
  const popup = window.open(href, '_blank', 'noopener,noreferrer,width=560,height=640');
  if (!popup) {
    window.location.href = href;
  }

  if (title && platform === 'facebook') {
    void title;
  }
}
