const CACHE_NAME = "moneytrack-shell-v3";
const SHELL_FILES = [
  "/static/manifest.json",
  "/static/icon-192.png",
  "/static/icon-512.png",
  "/static/offline.html",
  "/static/offline-db.js"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(SHELL_FILES))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) =>
        Promise.all(
          keys.filter((key) => key.startsWith("moneytrack-shell-") && key !== CACHE_NAME)
            .map((key) => caches.delete(key))
        )
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);

  if (request.method !== "GET" || url.origin !== self.location.origin) return;

  // Для перехода по страницам при сетевой ошибке показываем офлайн-оболочку.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(async () => {
        const offlinePage = await caches.match("/static/offline.html");
        return offlinePage || Response.error();
      })
    );
    return;
  }

  // Только публичные статические файлы. Финансовые страницы и API не кэшируем.
  if (
    url.pathname.startsWith("/static/") &&
    !url.pathname.includes("..")
  ) {
    event.respondWith(
      fetch(request).then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
        }
        return response;
      }).catch(async () => {
        const cached = await caches.match(request);
        return cached || Response.error();
      })
    );
  }
});
