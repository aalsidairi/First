/* LeavePortal Service Worker — basic offline shell cache */
const CACHE = 'leave-portal-v1';

const PRECACHE = [
  '/',
  '/static/css/style.css',
  '/static/js/main.js',
  '/static/manifest.json',
  '/static/icons/icon-192.svg',
  '/static/icons/icon-512.svg',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js'
];

/* Install — pre-cache shell assets */
self.addEventListener('install', function (e) {
  self.skipWaiting();
  e.waitUntil(
    caches.open(CACHE).then(function (cache) {
      return cache.addAll(PRECACHE).catch(function () { /* non-fatal */ });
    })
  );
});

/* Activate — remove stale caches */
self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys.filter(function (k) { return k !== CACHE; })
            .map(function (k) { return caches.delete(k); })
      );
    }).then(function () { return self.clients.claim(); })
  );
});

/* Fetch — network-first for HTML/API, cache-first for static assets */
self.addEventListener('fetch', function (e) {
  var url = new URL(e.request.url);

  /* Always go network-first for page navigation and API calls */
  if (e.request.mode === 'navigate' || url.pathname.startsWith('/api/')) {
    e.respondWith(
      fetch(e.request).catch(function () {
        return caches.match('/') || new Response(
          '<h1>You are offline</h1><p>Please reconnect to use Leave Portal.</p>',
          { headers: { 'Content-Type': 'text/html' } }
        );
      })
    );
    return;
  }

  /* Cache-first for static assets */
  if (url.pathname.startsWith('/static/') || url.hostname.includes('jsdelivr.net')) {
    e.respondWith(
      caches.match(e.request).then(function (cached) {
        return cached || fetch(e.request).then(function (response) {
          var clone = response.clone();
          caches.open(CACHE).then(function (cache) { cache.put(e.request, clone); });
          return response;
        });
      })
    );
    return;
  }

  /* Default: network */
  e.respondWith(fetch(e.request));
});
