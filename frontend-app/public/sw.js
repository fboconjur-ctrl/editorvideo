// Service worker mínimo: só existe pra deixar o app instalável ("Adicionar
// à tela de início") no Android/Chrome. Não faz cache agressivo porque o
// app depende do backend local rodando na mesma rede (Tailscale) — não faz
// sentido fingir que funciona offline.
//
// IMPORTANTE: a página (index.html) NUNCA pode ser cache-first. Cada build
// do Vite gera arquivos JS/CSS com hash novo no nome, e o index.html
// referencia esses hashes — se a página em si ficasse presa em cache, uma
// atualização do app deixaria o index.html velho apontando pra arquivos
// que não existem mais, dando tela em branco (já aconteceu numa versão
// anterior deste arquivo). Por isso: HTML sempre busca da rede primeiro;
// só os arquivos com hash em /assets/ (imutáveis por natureza) usam
// cache-first.
const CACHE_NAME = "video-editor-shell-v2";

self.addEventListener("install", () => {
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
  const { request } = event;
  if (request.method !== "GET" || request.url.includes("/api/")) {
    return;
  }

  const isHashedAsset = request.url.includes("/assets/");
  if (isHashedAsset) {
    event.respondWith(
      caches.match(request).then((cached) => cached || fetch(request).then((res) => {
        caches.open(CACHE_NAME).then((cache) => cache.put(request, res.clone())).catch(() => {});
        return res;
      }))
    );
    return;
  }

  // Navegação/HTML/manifest: sempre tenta a rede primeiro, só cai pro
  // cache se estiver offline de verdade.
  event.respondWith(
    fetch(request).catch(() => caches.match(request))
  );
});
