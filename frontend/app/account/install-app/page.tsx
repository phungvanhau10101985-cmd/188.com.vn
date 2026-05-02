'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
};

function isStandaloneDisplay(): boolean {
  if (typeof window === 'undefined') return false;
  if (window.matchMedia('(display-mode: standalone)').matches) return true;
  const nav = navigator as Navigator & { standalone?: boolean };
  return Boolean(nav.standalone);
}

function isIOS(): boolean {
  if (typeof navigator === 'undefined') return false;
  const ua = navigator.userAgent || '';
  if (/iPad|iPhone|iPod/i.test(ua)) return true;
  return navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1;
}

export default function AccountInstallAppPage() {
  const [standalone, setStandalone] = useState(false);
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [installing, setInstalling] = useState(false);

  useEffect(() => {
    setStandalone(isStandaloneDisplay());

    const onBip = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e as BeforeInstallPromptEvent);
    };
    window.addEventListener('beforeinstallprompt', onBip);
    return () => window.removeEventListener('beforeinstallprompt', onBip);
  }, []);

  const handleInstall = useCallback(async () => {
    if (!deferredPrompt) return;
    setInstalling(true);
    try {
      await deferredPrompt.prompt();
      await deferredPrompt.userChoice.catch(() => {});
    } catch {
      /* noop */
    } finally {
      setInstalling(false);
      setDeferredPrompt(null);
      setStandalone(isStandaloneDisplay());
    }
  }, [deferredPrompt]);

  const ios = isIOS();

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4 md:p-6 max-w-2xl">
      <h1 className="text-xl font-bold text-gray-900 mb-1">Cài đặt app 188.COM.VN</h1>
      <p className="text-sm text-gray-600 mb-6">
        Thêm shortcut lên màn hình để mở nhanh, xem đơn hàng và nhận thông báo giống app trên điện thoại.
      </p>

      {standalone ? (
        <div className="rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-900 mb-6">
          Bạn đang mở 188.COM.VN ở chế độ <strong>đã cài / PWA</strong>. Không cần thao tác thêm.
        </div>
      ) : null}

      {!standalone && ios ? (
        <div className="rounded-xl border border-orange-100 bg-orange-50/60 px-4 py-4 text-sm text-gray-800 mb-6 space-y-3">
          <p className="font-semibold text-gray-900">Trên iPhone / iPad (Safari hoặc Chrome)</p>
          <ol className="list-decimal list-inside space-y-2 text-gray-700">
            <li>
              Nhấn nút <strong className="text-gray-900">Chia sẻ</strong>{' '}
              <svg
                className="w-4 h-4 inline align-text-bottom text-[#007AFF] mx-0.5"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                aria-hidden
              >
                <path d="M12 3v12M8 9l4-4 4 4" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M5 15v4a2 2 0 002 2h10a2 2 0 002-2v-4" strokeLinecap="round" />
              </svg>{' '}
              (cuối thanh Safari hoặc menu Chrome).
            </li>
            <li>
              Chọn <strong className="text-gray-900">Thêm vào Màn hình chính</strong>.
            </li>
            <li>Xác nhận — icon app sẽ xuất hiện trên màn hình.</li>
          </ol>
          <p className="text-xs text-amber-900/90 bg-amber-100/80 rounded-lg px-3 py-2 border border-amber-200/80">
            Thông báo đẩy trên iOS hoạt động tốt nhất khi mở bằng icon app (iOS 16.4+).
          </p>
        </div>
      ) : null}

      {!standalone && !ios ? (
        <div className="rounded-xl border border-gray-200 bg-gray-50 px-4 py-4 text-sm text-gray-800 mb-6 space-y-3">
          <p className="font-semibold text-gray-900">Trên Android / Chrome / Edge</p>
          {deferredPrompt ? (
            <button
              type="button"
              onClick={handleInstall}
              disabled={installing}
              className="w-full md:w-auto min-h-[44px] px-5 rounded-xl bg-[#ea580c] text-white font-semibold hover:bg-[#c2410c] disabled:opacity-60"
            >
              {installing ? 'Đang mở…' : 'Cài đặt app'}
            </button>
          ) : (
            <ul className="list-disc list-inside space-y-2 text-gray-700">
              <li>Mở menu trình duyệt <strong>⋮</strong> hoặc <strong>⋯</strong>.</li>
              <li>
                Chọn <strong>Cài đặt ứng dụng</strong> / <strong>Install app</strong> hoặc{' '}
                <strong>Thêm vào màn hình chính</strong> (tùy bản Chrome).
              </li>
              <li>Nếu không thấy: vào website qua Chrome HTTPS và ghé lại trang này — một lúc sau có thể hiện nút cài ở trên.</li>
            </ul>
          )}
        </div>
      ) : null}

      <div className="flex flex-wrap gap-3 pt-2 border-t border-gray-100">
        <Link href="/account" className="text-sm font-medium text-[#ea580c] hover:text-[#c2410c]">
          ← Về trang cá nhân
        </Link>
      </div>
    </div>
  );
}
