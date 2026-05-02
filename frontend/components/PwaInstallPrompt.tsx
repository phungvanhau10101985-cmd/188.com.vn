"use client";

import { useCallback, useEffect, useState } from "react";
import { usePathname } from "next/navigation";

const STORAGE_KEY = "188_pwa_install_dismissed_at";
const COOLDOWN_DAYS = 14;
/** Đợi người dùng làm quen trang trước khi gợi ý cài */
const SHOW_AFTER_MS = 22000;

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

function isStandaloneDisplay(): boolean {
  if (typeof window === "undefined") return true;
  if (window.matchMedia("(display-mode: standalone)").matches) return true;
  const nav = navigator as Navigator & { standalone?: boolean };
  return Boolean(nav.standalone);
}

function isIOS(): boolean {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent || "";
  if (/iPad|iPhone|iPod/i.test(ua)) return true;
  return navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1;
}

function isLikelyInAppBrowser(): boolean {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent || "";
  return /FBAN|FBAV|FB_IAB|Instagram|Line\//i.test(ua);
}

function dismissedRecently(): boolean {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return false;
    const t = Number(raw);
    if (!Number.isFinite(t)) return false;
    const elapsed = Date.now() - t;
    return elapsed < COOLDOWN_DAYS * 86400000;
  } catch {
    return false;
  }
}

function persistDismiss() {
  try {
    localStorage.setItem(STORAGE_KEY, String(Date.now()));
  } catch {
    /* noop */
  }
}

export default function PwaInstallPrompt() {
  const pathname = usePathname();
  const [gateOpen, setGateOpen] = useState(false);
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [visible, setVisible] = useState(false);
  const [installing, setInstalling] = useState(false);

  const dismiss = useCallback(() => {
    persistDismiss();
    setVisible(false);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (isStandaloneDisplay()) return;
    if (isLikelyInAppBrowser()) return;
    if (dismissedRecently()) return;

    const onBip = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e as BeforeInstallPromptEvent);
      setGateOpen(true);
    };
    window.addEventListener("beforeinstallprompt", onBip);

    const t = window.setTimeout(() => setGateOpen(true), SHOW_AFTER_MS);
    return () => {
      window.removeEventListener("beforeinstallprompt", onBip);
      window.clearTimeout(t);
    };
  }, []);

  useEffect(() => {
    if (!gateOpen) return;
    if (isStandaloneDisplay()) return;
    if (isLikelyInAppBrowser()) return;
    if (dismissedRecently()) return;

    const showChromeInstall = deferredPrompt != null;
    const showIosSteps = isIOS();
    if (showChromeInstall || showIosSteps) setVisible(true);
  }, [gateOpen, deferredPrompt]);

  const handleInstallClick = async () => {
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
      dismiss();
    }
  };

  const hideOnRoute =
    pathname != null &&
    (pathname.startsWith("/auth") || pathname.startsWith("/admin"));

  if (hideOnRoute || !visible) return null;

  const showNativeInstall = deferredPrompt != null;

  return (
    <div
      className="fixed z-[100] left-2 right-2 md:left-auto md:right-5 md:max-w-md md:w-full bottom-[calc(4.25rem+env(safe-area-inset-bottom,0px))] md:bottom-6 motion-safe:transition-[opacity,transform] motion-safe:duration-300 motion-safe:ease-out"
      role="dialog"
      aria-labelledby="pwa-install-title"
      aria-describedby="pwa-install-desc"
    >
      <div className="rounded-2xl bg-white shadow-xl ring-1 ring-black/[0.08] overflow-hidden">
        <div className="flex items-start gap-3 p-4">
          <div className="shrink-0 w-11 h-11 rounded-xl bg-[#ea580c]/10 flex items-center justify-center">
            <svg className="w-6 h-6 text-[#ea580c]" viewBox="0 0 24 24" fill="none" aria-hidden>
              <path
                d="M12 3L4 9v12h16V9l-8-6z"
                stroke="currentColor"
                strokeWidth={1.75}
                strokeLinejoin="round"
              />
              <path d="M9 21V12h6v9" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" />
            </svg>
          </div>
          <div className="min-w-0 flex-1 pt-0.5">
            <p id="pwa-install-title" className="font-semibold text-gray-900 text-[15px] leading-snug">
              Cài đặt 188.COM.VN
            </p>
            <p id="pwa-install-desc" className="text-sm text-gray-600 mt-1 leading-relaxed">
              {showNativeInstall ? (
                <>
                  Thêm lối tắt lên màn hình để mở nhanh, gọn hơn và dùng như app.
                </>
              ) : (
                <>
                  Trên Safari / Chrome iOS: nhấn{" "}
                  <span className="font-medium text-gray-800">Chia sẻ</span>
                  <span className="mx-0.5 align-middle inline-flex" aria-hidden>
                    <svg
                      className="w-4 h-4 inline text-[#007AFF]"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth={2}
                    >
                      <path d="M12 3v12M8 9l4-4 4 4" strokeLinecap="round" strokeLinejoin="round" />
                      <path d="M5 15v4a2 2 0 002 2h10a2 2 0 002-2v-4" strokeLinecap="round" />
                    </svg>
                  </span>
                  rồi chọn{" "}
                  <span className="font-medium text-gray-800">Thêm vào Màn hình chính</span>.
                </>
              )}
            </p>
          </div>
          <button
            type="button"
            onClick={dismiss}
            className="shrink-0 -mr-1 -mt-1 p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100"
            aria-label="Đóng"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="flex gap-2 px-4 pb-4 pt-0">
          <button
            type="button"
            onClick={dismiss}
            className="flex-1 py-2.5 px-3 rounded-xl border border-gray-200 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            Để sau
          </button>
          {showNativeInstall ? (
            <button
              type="button"
              onClick={handleInstallClick}
              disabled={installing}
              className="flex-1 py-2.5 px-3 rounded-xl bg-[#ea580c] text-white text-sm font-semibold hover:bg-[#c2410c] disabled:opacity-60"
            >
              {installing ? "Đang mở…" : "Cài đặt"}
            </button>
          ) : (
            <button
              type="button"
              onClick={dismiss}
              className="flex-1 py-2.5 px-3 rounded-xl bg-[#ea580c] text-white text-sm font-semibold hover:bg-[#c2410c]"
            >
              Đã hiểu
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
