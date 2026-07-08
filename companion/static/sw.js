// PWA service worker: cache the static shell, never cache API or photos.
const CACHE = 'companion-v1';
const SHELL = [
  '/', '/css/app.css', '/manifest.webmanifest',
  '/js/app.js', '/js/api.js', '/js/store.js', '/js/chat.js',
  '/js/composer.js', '/js/settings.js', '/js/onboarding.js',
  '/icons/icon-192.png', '/icons/icon-512.png',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.pathname.startsWith('/api')
      || url.pathname.startsWith('/photos') || url.pathname.startsWith('/generated')
      || url.pathname.startsWith('/uploads')) {
    return; // network only
  }
  e.respondWith(
    caches.match(e.request).then((hit) => hit || fetch(e.request))
  );
});
