"use client";

import { useEffect } from "react";
import {
  syncPushSubscription,
  requestPermissionAndSyncPush,
  dispatchNotificationsRefresh,
} from "@/lib/web-push-subscribe";

const SESSION_AUTO_PROMPT_KEY = "188_auto_push_prompt_v1";

/**
 * Đăng ký service worker + đồng bộ Web Push khi khách đã đăng nhập và đã cho phép thông báo.
 * Một lần mỗi phiên: gợi ý hệ thống xin quyền (nếu đang default).
 */
export default function PwaPushRegister() {
  useEffect(() => {
    if (typeof window === "undefined" || !("serviceWorker" in navigator)) return;

    const regSw = () =>
      navigator.serviceWorker
        .register("/sw.js", { scope: "/" })
        .catch((e) => console.warn("[PWA] SW register:", e));

    const w = window;
    const ric = w.requestIdleCallback?.bind(w);
    let idleId: ReturnType<typeof requestIdleCallback> | undefined;
    let swTimeoutId: ReturnType<typeof setTimeout> | undefined;
    if (ric) idleId = ric(() => regSw(), { timeout: 6000 });
    else swTimeoutId = setTimeout(regSw, 400);

    const onSwMessage = (event: MessageEvent) => {
      if (event.data?.type === "NOTIFICATIONS_REFRESH") {
        dispatchNotificationsRefresh();
      }
    };
    navigator.serviceWorker.addEventListener("message", onSwMessage);

    const runGrantedSync = () => {
      const token = localStorage.getItem("access_token");
      if (!token) return;
      if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
      syncPushSubscription().catch(() => {});
    };

    /** Một lần / phiên: xin quyền tự động sau vài giây (sau khi vào site đã đăng nhập) */
    const maybeAutoPromptPermission = async () => {
      if (!localStorage.getItem("access_token")) return;
      if (typeof Notification === "undefined") return;
      if (Notification.permission !== "default") return;
      if (sessionStorage.getItem(SESSION_AUTO_PROMPT_KEY)) return;
      sessionStorage.setItem(SESSION_AUTO_PROMPT_KEY, "1");
      await requestPermissionAndSyncPush();
    };

    const tSync = setTimeout(runGrantedSync, 2500);
    const tPrompt = setTimeout(maybeAutoPromptPermission, 8000);

    const onStorage = (e: StorageEvent) => {
      if (e.key === "access_token" && e.newValue) {
        runGrantedSync();
        setTimeout(maybeAutoPromptPermission, 1500);
      }
      if (e.key === "access_token" && !e.newValue) {
        sessionStorage.removeItem(SESSION_AUTO_PROMPT_KEY);
      }
    };
    window.addEventListener("storage", onStorage);

    const onAuthSession = () => {
      runGrantedSync();
      setTimeout(maybeAutoPromptPermission, 1200);
    };
    window.addEventListener("188-auth-session-changed", onAuthSession);

    const onVis = () => {
      if (document.visibilityState === "visible") runGrantedSync();
    };
    document.addEventListener("visibilitychange", onVis);

    const iv = setInterval(runGrantedSync, 90000);

    return () => {
      if (idleId != null && w.cancelIdleCallback) w.cancelIdleCallback(idleId);
      if (swTimeoutId != null) clearTimeout(swTimeoutId);
      navigator.serviceWorker.removeEventListener("message", onSwMessage);
      clearTimeout(tSync);
      clearTimeout(tPrompt);
      clearInterval(iv);
      window.removeEventListener("storage", onStorage);
      window.removeEventListener("188-auth-session-changed", onAuthSession);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);

  return null;
}
