// Web Push 수신 (§10.1). 페이로드: { title, body, url } — backend/app/workers/notifier.py
self.addEventListener("push", (e) => {
  const d = e.data ? e.data.json() : {};
  e.waitUntil(
    self.registration.showNotification(d.title || "결로 알림", { body: d.body, tag: d.url, data: d }).then(() =>
      self.clients.matchAll().then((cs) => cs.forEach((c) => c.postMessage(d))),
    ),
  );
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  e.waitUntil(self.clients.openWindow(e.notification.data?.url || "/"));
});
