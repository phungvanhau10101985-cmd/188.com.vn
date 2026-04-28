"use client";

import { useEffect, useRef } from "react";
import { apiClient } from "@/lib/api-client";

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = atob(base64);
  return Uint8Array.from([...rawData].map((c) => c.charCodeAt(0)));
}

/**
 * Đăng ký service worker (PWA) + Web Push (khi đã đăng nhập, có VAPID trên server).
 * iOS: PWA cài màn hình chính có từ 16.4+; thông báo đẩy phụ thuộc Apple/Safari.
 */
export default function PwaPushRegister() {
  const done = useRef(false);

  useEffect(() => {
    if (typeof window === "undefined" || !("serviceWorker" in navigator)) return;

    const regSw = () =>
      navigator.serviceWorker
        .register("/sw.js", { scope: "/" })
        .catch((e) => console.warn("[PWA] SW register:", e));

    regSw();

    const tryPush = async () => {
      if (done.current) return;
      const token = localStorage.getItem("access_token");
      if (!token) return;
      if (!("PushManager" in window)) return;

      const perm = await Notification.requestPermission();
      if (perm !== "granted") return;

      let vapid: { public_key: string };
      try {
        vapid = await apiClient.getPushVapidKey();
      } catch {
        return;
      }
      if (!vapid?.public_key) return;

      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapid.public_key) as unknown as BufferSource,
      });
      const j = sub.toJSON();
      if (!j.endpoint || !j.keys?.p256dh || !j.keys?.auth) return;

      try {
        await apiClient.registerPushSubscription({
          endpoint: j.endpoint,
          keys: { p256dh: j.keys.p256dh, auth: j.keys.auth },
          user_agent: typeof navigator !== "undefined" ? navigator.userAgent : undefined,
        });
        done.current = true;
      } catch (e) {
        console.warn("[PWA] push subscribe:", e);
      }
    };

    const t = setTimeout(tryPush, 2000);
    const onStorage = (e: StorageEvent) => {
      if (e.key === "access_token" && e.newValue) tryPush();
    };
    window.addEventListener("storage", onStorage);
    const onVis = () => {
      if (document.visibilityState === "visible") tryPush();
    };
    document.addEventListener("visibilitychange", onVis);
    let n = 0;
    const iv = setInterval(() => {
      n += 1;
      tryPush();
      if (n >= 24) clearInterval(iv);
    }, 5000);
    return () => {
      clearTimeout(t);
      clearInterval(iv);
      window.removeEventListener("storage", onStorage);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);

  return null;
}
