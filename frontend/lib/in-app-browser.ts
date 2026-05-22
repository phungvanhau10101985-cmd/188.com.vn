export type InAppBrowserKind = 'zalo' | 'facebook' | 'messenger' | 'instagram' | 'wechat' | 'generic';

const IN_APP_UA =
  /Zalo|ZaloIOS|ZaloAndroid|FBAN|FBAV|FB_IAB|FBIOS|FB4A|FBMD|MetaIAB|\[FB|Messenger|Instagram|IG_IAB|Line\/|MicroMessenger|Twitter|LinkedInApp|BytedanceWebview/i;

/** Nhận diện trình duyệt nhúng (Zalo, Facebook, Messenger, Instagram…). */
export function detectInAppBrowser(): InAppBrowserKind | null {
  if (typeof navigator === 'undefined') return null;
  const ua = navigator.userAgent || '';
  if (!IN_APP_UA.test(ua)) return null;

  if (/Zalo/i.test(ua)) return 'zalo';
  if (/Messenger|FBAN\/Messenger/i.test(ua)) return 'messenger';
  if (/Instagram|IG_IAB/i.test(ua)) return 'instagram';
  if (/FBAN|FBAV|FB_IAB|FBIOS|FB4A|MetaIAB|\[FB/i.test(ua)) return 'facebook';
  if (/MicroMessenger/i.test(ua)) return 'wechat';
  return 'generic';
}

export function isInAppBrowser(): boolean {
  return detectInAppBrowser() != null;
}

export function getInAppBrowserShortName(kind: InAppBrowserKind | null = detectInAppBrowser()): string {
  switch (kind) {
    case 'facebook':
      return 'Facebook';
    case 'messenger':
      return 'Messenger';
    case 'instagram':
      return 'Instagram';
    case 'zalo':
      return 'Zalo';
    case 'wechat':
      return 'WeChat';
    default:
      return 'app';
  }
}

export function getInAppBrowserSaveHint(kind: InAppBrowserKind | null = detectInAppBrowser()): string {
  const app = getInAppBrowserShortName(kind);
  if (kind === 'generic' || kind == null) {
    return 'Trình duyệt trong app không tải file tự động — giữ ngón tay trên ảnh → Lưu vào máy.';
  }
  return `${app} không tải file tự động — giữ ngón tay trên ảnh → Lưu vào máy.`;
}

export function isLikelyMobile(): boolean {
  if (typeof navigator === 'undefined') return false;
  return /Android|iPhone|iPad|iPod/i.test(navigator.userAgent || '');
}
