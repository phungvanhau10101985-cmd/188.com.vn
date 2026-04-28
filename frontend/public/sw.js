/* PWA: cache tối thiểu, ưu tiên mạng; xử lý thông báo Web Push (tài khoản) */
const CACHE = "188-static-v1";

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
    fetch(event.request).catch(() => caches.match("/offline") || fetch(event.request))
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
  const options = {
    body: data.body || "",
    icon: "https://188comvn.b-cdn.net/logo188.png",
    badge: "https://188comvn.b-cdn.net/logo188.png",
    data: { url: data.url || "/account/notifications" },
  };
  event.waitUntil(self.registration.showNotification(title, options));
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
