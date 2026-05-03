/* PWA: cache tối thiểu, ưu tiên mạng; xử lý thông báo Web Push (tài khoản) */
const CACHE = "188-static-v2";

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET" || !event.request.url.startsWith("http")) {
    return;
  }
  event.respondWith(
    fetch(event.request).catch(async () => {
      const cached = await caches.match("/offline");
      if (cached) return cached;
      return new Response("Offline", { status: 503, headers: { "Content-Type": "text/plain; charset=utf-8" } });
    })
  );
});

self.addEventListener("push", (event) => {
  let data = { title: "188.COM.VN", body: "Bạn có thông báo mới", url: "/account/notifications" };
  try {
    if (event.data) {
      const t = event.data.text();
      if (t) data = { ...data, ...JSON.parse(t) };
    }
  } catch (e) {
    /* dùng mặc định */
  }
  const title = data.title || "188.COM.VN";
  /** Logo đầy màu cho khay thông báo (không dùng làm badge Android — xem comment dưới). */
  const iconUrl =
    data.icon ||
    "https://188comvn.b-cdn.net/site/20260502/logo_1x1_0584d3f73e4a.png";
  const options = {
    body: data.body || "",
    icon: iconUrl,
    // Không đặt `badge`: Android đưa badge lên status bar dạng silhouette đơn sắc.
    // Gán logo màu/CDN vào badge → thường thành ô vuông trắng nhỏ.
    data: { url: data.url || "/account/notifications" },
  };
  event.waitUntil(
    (async () => {
      try {
        const clients = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
        clients.forEach((c) => {
          try {
            c.postMessage({ type: "NOTIFICATIONS_REFRESH" });
          } catch (e) {
            /* noop */
          }
        });
      } catch (e) {
        /* noop */
      }
      await self.registration.showNotification(title, options);
    })()
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/account/notifications";
  const abs = new URL(url, self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      for (const c of list) {
        if ("focus" in c) {
          c.focus();
          c.postMessage({ type: "NOTIF_OPEN", url: abs });
          return;
        }
      }
      if (self.clients.openWindow) {
        return self.clients.openWindow(abs);
      }
    })
  );
});
