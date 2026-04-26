/**
 * OpenChat Local — Service Worker
 * Caches static assets for offline / fast PWA experience.
 */

const CACHE_NAME = 'openchat-v3';
const STATIC_ASSETS = [
    '/static/css/style.css',
    '/static/js/app.js',
    '/static/js/taskMode.js',
    '/static/manifest.json',
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) =>
            cache.addAll(STATIC_ASSETS).catch(() => {})
        )
    );
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
        )
    );
    self.clients.claim();
});

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // Only cache GET requests for static assets
    if (event.request.method !== 'GET') return;
    if (url.pathname.startsWith('/api/')) return;

    event.respondWith(
        caches.match(event.request).then((cached) => {
            // Network-first for HTML, cache-first for static files
            if (url.pathname === '/' || url.pathname.endsWith('.html')) {
                return fetch(event.request)
                    .then((res) => {
                        const clone = res.clone();
                        caches.open(CACHE_NAME).then(c => c.put(event.request, clone));
                        return res;
                    })
                    .catch(() => cached);
            }
            // Cache-first for CSS/JS
            if (cached) return cached;
            return fetch(event.request).then((res) => {
                if (res.ok) {
                    const clone = res.clone();
                    caches.open(CACHE_NAME).then(c => c.put(event.request, clone));
                }
                return res;
            });
        })
    );
});
