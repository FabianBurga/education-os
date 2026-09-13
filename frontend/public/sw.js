const CACHE_PREFIX = "education-os-pwa-shell";
const CACHE_NAME = `${CACHE_PREFIX}-m20-v1`;
const SHELL_URL = "/app/";
const STATIC_URLS = [
  "/app/manifest.webmanifest",
  "/app/icons/icon-192.png",
  "/app/icons/icon-512.png",
];

async function precacheShell() {
  const cache = await caches.open(CACHE_NAME);
  for (const url of STATIC_URLS) {
    try {
      await cache.add(url);
    } catch {
      // A single optional static asset must not prevent SW installation.
    }
  }

  const response = await fetch(SHELL_URL, { cache: "reload" });
  if (!response.ok) {
    throw new Error(`Unable to precache app shell: ${response.status}`);
  }
  const html = await response.clone().text();
  await cache.put(SHELL_URL, response);

  const assetUrls = new Set();
  const matcher = /(?:src|href)="([^"]+)"/g;
  for (const match of html.matchAll(matcher)) {
    const url = match[1];
    if (
      url.startsWith("/app/") &&
      !url.startsWith("/app/api/")
    ) {
      assetUrls.add(url);
    }
  }

  await Promise.all(
    [...assetUrls].map(async (url) => {
      try {
        await cache.add(url);
      } catch {
        // Runtime caching can recover an optional asset later.
      }
    }),
  );
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    precacheShell().then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const names = await caches.keys();
      await Promise.all(
        names
          .filter(
            (name) =>
              name.startsWith(CACHE_PREFIX) &&
              name !== CACHE_NAME,
          )
          .map((name) => caches.delete(name)),
      );
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") {
    return;
  }

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) {
    return;
  }

  // Privacy boundary: authenticated APIs and health endpoints are never
  // persisted in CacheStorage. Teacher data lives only in the partitioned
  // IndexedDB store controlled by the application.
  if (
    url.pathname.startsWith("/api/") ||
    url.pathname.startsWith("/health")
  ) {
    return;
  }

  if (!url.pathname.startsWith("/app")) {
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      (async () => {
        try {
          const response = await fetch(request);
          if (response.ok) {
            const cache = await caches.open(CACHE_NAME);
            await cache.put(SHELL_URL, response.clone());
          }
          return response;
        } catch {
          const cached = await caches.match(SHELL_URL);
          return cached || Response.error();
        }
      })(),
    );
    return;
  }

  event.respondWith(
    (async () => {
      const cached = await caches.match(request);
      if (cached) {
        return cached;
      }
      const response = await fetch(request);
      if (response.ok) {
        const cache = await caches.open(CACHE_NAME);
        await cache.put(request, response.clone());
      }
      return response;
    })(),
  );
});
