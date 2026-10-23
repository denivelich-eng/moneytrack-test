const CACHE_NAME = "moneytrack-shell-v4";
const SHELL_FILES = [
  "/",
  "/add",
  "/accounts",
  "/static/manifest.json",
  "/static/icon-192.png",
  "/static/icon-512.png",
  "/static/offline.html",
  "/static/offline-db.js",
  "/static/offline-sync.js"
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

  // Для страниц (Главная, Добавить, Счета)
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          // Сохраняем свежую версию страницы в кэш
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(async () => {
          // Если интернета нет, отдаем сохраненную версию страницы
          const cached = await caches.match(request);
          if (cached) return cached;
          // Если страницы нет в кэше, показываем offline.html
          return caches.match("/static/offline.html");
        })
    );
    return;
  }

  // Для статических файлов (картинки, скрипты)
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      fetch(request).then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
        }
        return response;
      }).catch(async () => {
        return await caches.match(request) || Response.error();
      })
    );
  }
});
