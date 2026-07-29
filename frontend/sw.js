const CACHE = 'carwash-one-v16';
const STATIC_ASSETS = [
  '/site/',
  '/site/static/css/theme.css',
  '/site/static/css/site-v2.css',
  '/site/static/css/interactions-v9.css',
  '/site/static/css/hero-inspection-v15.css',
  '/site/static/js/api.js',
  '/site/static/js/interactions-v9.js',
  '/site/static/js/hero-inspection-v15.js',
  '/site/static/img/logo.png',
  '/site/static/img/hero-markii-premium.png',
  '/site/static/img/car-body-mask.svg'
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(STATIC_ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (url.pathname.startsWith('/site/static/')) {
    event.respondWith(
      caches.match(request).then(cached => cached || fetch(request).then(response => {
        const copy = response.clone();
        caches.open(CACHE).then(cache => cache.put(request, copy));
        return response;
      }))
    );
    return;
  }

  if (request.mode === 'navigate' && url.pathname.startsWith('/site/')) {
    event.respondWith(fetch(request).catch(() => caches.match('/site/')));
  }
});
