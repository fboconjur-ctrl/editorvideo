// Service worker mínimo: só existe pra deixar o app instalável ("Adicionar
// à tela de início") no Android/Chrome. Não faz cache agressivo porque o
// app depende do backend local rodando na mesma rede (Tailscale) — não faz
// sentido fingir que funciona offline.
const CACHE_NAME = "video-editor-shell-v1";
const SHELL_FILES = ["/", "/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_FILES)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  // Só a casca da página usa cache-first; tudo que é /api/* sempre vai
  // direto pro backend (nunca deve responder com dado velho do cache).
  if (event.request.method !== "GET" || event.request.url.includes("/api/")) {
    return;
  }
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
