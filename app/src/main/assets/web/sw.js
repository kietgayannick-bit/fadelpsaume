/* Service worker minimal : requis par Chrome pour installer l'application. Tout passe par le réseau. */
self.addEventListener('install', function () { self.skipWaiting(); });
self.addEventListener('activate', function (e) { e.waitUntil(self.clients.claim()); });
self.addEventListener('fetch', function () { /* réseau uniquement */ });
