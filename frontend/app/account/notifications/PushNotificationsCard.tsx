'use client';

import { useState, useEffect, useCallback } from 'react';
import { syncPushSubscription, requestPermissionAndSyncPush } from '@/lib/web-push-subscribe';
import { apiClient } from '@/lib/api-client';
import { useToast } from '@/components/ToastProvider';

function isStandalonePwa(): boolean {
  if (typeof window === 'undefined') return false;
  if (window.matchMedia('(display-mode: standalone)').matches) return true;
  const nav = navigator as Navigator & { standalone?: boolean };
  return Boolean(nav.standalone);
}

export default function PushNotificationsCard() {
  const { pushToast } = useToast();
  const [busy, setBusy] = useState(false);
  const [perm, setPerm] = useState<NotificationPermission | 'unsupported'>('default');
  const [serverPush, setServerPush] = useState<boolean | null>(null);

  const refreshPerm = useCallback(() => {
    if (typeof Notification === 'undefined') setPerm('unsupported');
    else setPerm(Notification.permission);
  }, []);

  useEffect(() => {
    refreshPerm();
    let cancelled = false;
    apiClient
      .getPushVapidKey()
      .then(() => {
        if (!cancelled) setServerPush(true);
      })
      .catch(() => {
        if (!cancelled) setServerPush(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshPerm]);

  const handleEnable = async () => {
    setBusy(true);
    try {
      const r = await requestPermissionAndSyncPush();
      refreshPerm();
      if (r.ok) {
        pushToast({ title: 'Đã bật thông báo đẩy trên thiết bị này', variant: 'success', durationMs: 2800 });
        return;
      }
      if (r.reason === 'denied') {
        pushToast({
          title: 'Đã từ chối thông báo',
          description: 'Vào cài đặt trình duyệt hoặc hệ thống để bật lại cho trang này.',
          variant: 'info',
          durationMs: 4500,
        });
        return;
      }
      if (r.reason === 'no-vapid' || serverPush === false) {
        pushToast({
          title: 'Chưa bật đẩy trên máy chủ',
          description: 'Liên hệ quản trị để cấu hình VAPID.',
          variant: 'info',
          durationMs: 4000,
        });
        return;
      }
      pushToast({
        title: 'Chưa đăng ký được',
        description: 'Thử trình duyệt Chrome hoặc Safari mới; kiểm tra HTTPS.',
        variant: 'error',
        durationMs: 3800,
      });
    } finally {
      setBusy(false);
    }
  };

  const handleResync = async () => {
    setBusy(true);
    try {
      const r = await syncPushSubscription();
      refreshPerm();
      if (r.ok) {
        pushToast({ title: 'Đã đồng bộ thông báo đẩy', variant: 'success', durationMs: 2200 });
      } else if (r.reason === 'not-granted') {
        pushToast({ title: 'Cần cho phép thông báo', variant: 'info', durationMs: 2800 });
      } else {
        pushToast({ title: 'Chưa đồng bộ được', variant: 'info', durationMs: 2600 });
      }
    } finally {
      setBusy(false);
    }
  };

  const swOk = typeof window !== 'undefined' && 'serviceWorker' in navigator && 'PushManager' in window;

  if (perm === 'unsupported' || !swOk) {
    return (
      <div className="mb-6 rounded-xl border border-gray-200 bg-gray-50 p-4 text-sm text-gray-600">
        <p className="font-medium text-gray-800">Thông báo đẩy</p>
        <p className="mt-1">Trình duyệt hoặc thiết bị này không hỗ trợ thông báo đẩy.</p>
      </div>
    );
  }

  const granted = perm === 'granted';

  return (
    <div className="mb-6 rounded-xl border border-orange-100 bg-gradient-to-br from-orange-50/90 to-white p-4 shadow-sm">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="font-semibold text-gray-900">Thông báo trên app / điện thoại</p>
          <p className="mt-1 text-sm text-gray-600 leading-relaxed">
            Bật để nhận đẩy đơn hàng, khuyến mãi và tin hệ thống giống app — ngay khi có thông báo trong tài khoản.
          </p>
          {!isStandalonePwa() && (
            <p className="mt-2 text-xs text-amber-800/90 bg-amber-50 border border-amber-100 rounded-lg px-2.5 py-1.5">
              <strong>iPhone/iPad:</strong> thêm 188.COM.VN vào <strong>Màn hình chính</strong> rồi mở bằng icon app để đẩy hoạt động ổn định (iOS 16.4+).
            </p>
          )}
          {serverPush === false && (
            <p className="mt-2 text-xs text-red-700">Máy chủ chưa cấu hình VAPID — liên hệ kỹ thuật để kích hoạt đẩy.</p>
          )}
        </div>
        <div className="flex flex-col sm:flex-row gap-2 shrink-0">
          {!granted ? (
            <button
              type="button"
              onClick={handleEnable}
              disabled={busy || serverPush === false}
              className="min-h-[44px] px-4 rounded-xl bg-[#ea580c] text-white text-sm font-semibold hover:bg-[#c2410c] disabled:opacity-50"
            >
              {busy ? 'Đang xử lý…' : 'Bật thông báo đẩy'}
            </button>
          ) : (
            <button
              type="button"
              onClick={handleResync}
              disabled={busy}
              className="min-h-[44px] px-4 rounded-xl border border-orange-200 bg-white text-[#ea580c] text-sm font-semibold hover:bg-orange-50 disabled:opacity-50"
            >
              {busy ? 'Đang đồng bộ…' : 'Đồng bộ lại thiết bị'}
            </button>
          )}
        </div>
      </div>
      {granted && (
        <p className="mt-3 text-xs text-green-700 flex items-center gap-1.5">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-green-500" aria-hidden />
          Đã cho phép thông báo — khách sẽ nhận đẩy cho mọi tin gửi tới tài khoản.
        </p>
      )}
    </div>
  );
}
