// SaathiAI service worker — offline shell for navigations ONLY.
// v2: never intercept JS/CSS/chunks (those must always load fresh from network,
// or a stale/mismatched bundle crashes the app on installed PWAs like iPad).
const CACHE = "saathi-os-v2";

self.addEventListener("install", (e) => {
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  // ONLY handle top-level page navigations. Everything else (JS, CSS, chunks,
  // API, images) passes straight through to the network — no stale bundles.
  if (req.method !== "GET" || req.mode !== "navigate") return;
  e.respondWith(
    fetch(req)
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
        return res;
      })
      .catch(() => caches.match(req).then((r) => r || caches.match("/")))
  );
});
