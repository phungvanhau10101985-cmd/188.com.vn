import { apiClient } from '@/lib/api-client';

export function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = atob(base64);
  return Uint8Array.from([...rawData].map((c) => c.charCodeAt(0)));
}

/** Quét cờ để các tab/component biết làm mới số thông báo */
export function dispatchNotificationsRefresh() {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new Event('188-notifications-refresh'));
}

/**
 * Đăng ký endpoint push lên server khi quyền đã granted (không hỏi quyền).
 * Gọi lại an toàn sau đăng nhập / đổi thiết bị.
 */
export async function syncPushSubscription(): Promise<{ ok: boolean; reason?: string }> {
  if (typeof window === 'undefined') return { ok: false, reason: 'no-window' };
  if (!localStorage.getItem('access_token')) return { ok: false, reason: 'no-auth' };
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    return { ok: false, reason: 'unsupported' };
  }
  if (typeof Notification === 'undefined' || Notification.permission !== 'granted') {
    return { ok: false, reason: 'not-granted' };
  }

  try {
    const vapid = await apiClient.getPushVapidKey();
    if (!vapid?.public_key) return { ok: false, reason: 'no-vapid' };

    const reg = await navigator.serviceWorker.ready;
    let sub = await reg.pushManager.getSubscription();
    if (!sub) {
      sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapid.public_key) as unknown as BufferSource,
      });
    }
    const j = sub.toJSON();
    if (!j.endpoint || !j.keys?.p256dh || !j.keys?.auth) return { ok: false, reason: 'bad-sub' };

    await apiClient.registerPushSubscription({
      endpoint: j.endpoint,
      keys: { p256dh: j.keys.p256dh, auth: j.keys.auth },
      user_agent: typeof navigator !== 'undefined' ? navigator.userAgent : undefined,
    });
    dispatchNotificationsRefresh();
    return { ok: true };
  } catch {
    return { ok: false, reason: 'error' };
  }
}

/** Hỏi quyền (cần thao tác người dùng trên một số trình duyệt) rồi đăng ký */
export async function requestPermissionAndSyncPush(): Promise<{ ok: boolean; reason?: string }> {
  if (typeof window === 'undefined') return { ok: false, reason: 'no-window' };
  if (!('Notification' in window)) return { ok: false, reason: 'unsupported' };

  const cur = Notification.permission;
  let perm = cur;
  if (cur === 'default') {
    perm = await Notification.requestPermission();
  }
  if (perm !== 'granted') return { ok: false, reason: perm };

  return syncPushSubscription();
}
