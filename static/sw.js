const CACHE_NAME = "moneytrack-shell-v10";

const SHELL_FILES = [
  "/static/manifest.json",
  "/static/icon-192.png",
  "/static/icon-512.png",
  "/static/offline.html",
  "/static/offline-db.js",
  "/static/offline-sync.js",
  "/static/offline-forms.js"
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
      .then((keys) => Promise.all(
        keys
          .filter((key) =>
            key.startsWith("moneytrack-shell-") &&
            key !== CACHE_NAME
          )
          .map((key) => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);

  if (url.origin !== self.location.origin) return;
  if (request.method !== "GET") return;

  if (
    url.pathname.startsWith("/api/") ||
    url.pathname === "/sw.js"
  ) {
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith((async () => {
      const cache = await caches.open(CACHE_NAME);

      try {
        const response = await fetch(request);

        if (
          response.ok &&
          !response.redirected &&
          response.headers.get("content-type")?.includes("text/html") &&
          !["/login", "/register"].includes(url.pathname)
        ) {
          await cache.put(request, response.clone());
        }

        if (
          response.ok &&
          ["/login", "/logout"].includes(url.pathname)
        ) {
          const keys = await cache.keys();

          await Promise.all(
            keys
              .filter((key) => {
                const path = new URL(key.url).pathname;
                return path !== "/static/offline.html" &&
                  !path.startsWith("/static/");
              })
              .map((key) => cache.delete(key))
          );
        }

        return response;
      } catch (error) {
        const savedPage = await cache.match(request);

        if (savedPage) return savedPage;

        const homePage = await cache.match("/");

        if (homePage) return homePage;

        const offlinePage = await cache.match("/static/offline.html");

        if (offlinePage) return offlinePage;

        return new Response(
          "MoneyTrack недоступен офлайн. Откройте приложение с интернетом хотя бы один раз.",
          {
            status: 503,
            headers: { "Content-Type": "text/plain; charset=utf-8" }
          }
        );
      }
    })());

    return;
  }

  if (url.pathname.startsWith("/static/")) {
    event.respondWith((async () => {
      const cache = await caches.open(CACHE_NAME);

      try {
        const response = await fetch(request);

        if (response.ok) {
          await cache.put(request, response.clone());
        }

        return response;
      } catch (error) {
        const saved = await cache.match(request);

        if (saved) return saved;

        return new Response("", { status: 504 });
      }
    })());
  }
});
