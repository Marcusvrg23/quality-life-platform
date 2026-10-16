{% autoescape off %}/* Quality Life service worker (docs/specs/13-pwa-lembretes.md).
   Caches only the public offline page, the icon and hashed static files.
   App pages, authenticated responses and non-GET requests are never stored.
   Shows the generic push notifications sent by the server. */
'use strict';
const CACHE = '{{ cache_name }}';
const PRECACHE = {{ precache }};
const OFFLINE_URL = PRECACHE[0];
const STATIC_PREFIX = '{{ static_url }}';
// Names written by ManifestStaticFilesStorage: file.<12 hex>.ext (immutable).
const HASHED_STATIC = /\.[0-9a-f]{12}\.(css|js|png|svg|webp|jpe?g|woff2?)$/;

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE).then(cache => cache.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
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
  if (request.mode === 'navigate') {
    // Always the network; a page is never stored, only replaced when offline.
    event.respondWith(
      fetch(request).catch(() => caches.match(OFFLINE_URL).then(hit => hit || Response.error()))
    );
    return;
  }
  if (PRECACHE.includes(url.pathname)) {
    event.respondWith(fetch(request).catch(() => caches.match(request).then(hit => hit || Response.error())));
    return;
  }
  if (url.pathname.startsWith(STATIC_PREFIX) && HASHED_STATIC.test(url.pathname) && !request.headers.has('range')) {
    event.respondWith(
      caches.match(request).then(hit => hit || fetch(request).then(response => {
        if (response.status === 200) {
          const copy = response.clone();
          caches.open(CACHE).then(cache => cache.put(request, copy)).catch(() => {});
        }
        return response;
      }))
    );
  }
});

// Web Push from the server (wellbeing/notifications.py). The payload is always
// generic (title, body, same-origin url); without one a neutral text is shown.
self.addEventListener('push', event => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch (error) {
    payload = {};
  }
  if (!payload || typeof payload !== 'object') payload = {};
  const title = typeof payload.title === 'string' && payload.title ? payload.title : 'Quality Life';
  const body = typeof payload.body === 'string' ? payload.body : 'Você tem uma novidade no app.';
  const url = typeof payload.url === 'string' ? payload.url : '/';
  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon: PRECACHE[1],
      badge: PRECACHE[1],
      tag: typeof payload.tag === 'string' ? payload.tag : 'ql-notificacao',
      data: { url },
    })
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const data = event.notification.data || {};
  const target = new URL(data.url || '/', self.location.origin);
  const url = target.origin === self.location.origin ? target.href : self.location.origin + '/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(windows => {
      const open = windows.find(client => 'navigate' in client && 'focus' in client);
      if (!open) return self.clients.openWindow(url);
      return open.navigate(url)
        .then(client => (client || open).focus())
        .catch(() => self.clients.openWindow(url));
    })
  );
});
{% endautoescape %}
