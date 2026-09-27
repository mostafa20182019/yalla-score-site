/* Yalla Score service worker - WEB PUSH ONLY (2026-09-27).
 *
 * It shows a notification when push_send.py sends one, and opens the article
 * when it is tapped. That is all it does, on purpose:
 *
 *   NO fetch handler, NO cache. A caching service worker is the classic way a
 *   static site ends up serving yesterday's pages to the people who visit it
 *   most - and this site rebuilds every 15 minutes. Without a fetch handler
 *   every request goes to the network exactly as it did before this file
 *   existed.
 *
 * It is registered only when a reader taps the bell (push_js.html), never on
 * page load.
 */
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("push", (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (_) { d = {}; }
  const opts = {
    body: d.body || "",
    icon: d.icon || "/assets/icon-192.png",
    badge: d.badge || "/assets/badge-96.png",
    dir: "rtl",
    lang: "ar",
    tag: d.tag || "yalla-news",       // a second push for the same piece replaces the first
    data: { url: d.url || "/" },
  };
  if (d.image) opts.image = d.image;
  e.waitUntil(self.registration.showNotification(d.title || "يلا سكور", opts));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "/";
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((wins) => {
    for (const w of wins) {
      if (w.url === url && "focus" in w) return w.focus();
    }
    return self.clients.openWindow(url);
  }));
});

/* The push service can rotate a subscription (expiry, key change). Re-subscribe
 * with the same server key and tell the Worker, or the reader silently stops
 * getting notifications. The old endpoint dies on its own: push_send.py drops
 * an endpoint the first time it answers 404/410. */
self.addEventListener("pushsubscriptionchange", (e) => {
  const old = e.oldSubscription;
  const key = old && old.options && old.options.applicationServerKey;
  if (!key) return;
  e.waitUntil(self.registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key })
    .then((sub) => fetch("/push/subscribe", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(sub.toJSON()),
    })).catch(() => {}));
});
