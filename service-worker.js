// EconoIA — service worker
// Estratégia: a "casca" do site (HTML, ícones) é guardada em cache para abrir
// rápido e funcionar offline. Já os dados ao vivo e as chamadas de IA vão
// SEMPRE à rede primeiro (nunca servir economia/IA desatualizada do cache).

const CACHE = "econoia-v5";

// Arquivos da casca do app que valem guardar para abrir offline.
const SHELL = [
  "/",
  "/index.html",
  "/favicon.svg",
  "/favicon-32.png",
  "/apple-touch-icon.png",
  "/manifest.json"
];

// Instala: guarda a casca.
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL))
  );
  self.skipWaiting();
});

// Ativa: limpa caches antigos de versões anteriores.
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);

  // Só mexemos em GET do próprio site.
  if (req.method !== "GET" || url.origin !== location.origin) return;

  // Dados ao vivo e funções (IA/Gemini, IBGE, BCB): rede primeiro, cache como
  // último recurso se estiver offline.
  const aoVivo =
    url.pathname.startsWith("/api/") ||
    url.pathname.startsWith("/.netlify/functions/") ||
    url.pathname.startsWith("/data/");

  if (aoVivo) {
    event.respondWith(
      fetch(req)
        .then((resp) => {
          const copia = resp.clone();
          caches.open(CACHE).then((c) => c.put(req, copia));
          return resp;
        })
        .catch(() => caches.match(req))
    );
    return;
  }

  // Páginas HTML: rede primeiro (sempre a versão nova), cache só offline.
  if (req.mode === "navigate" || url.pathname === "/" || url.pathname.endsWith(".html")) {
    event.respondWith(
      fetch(req)
        .then((resp) => {
          const copia = resp.clone();
          caches.open(CACHE).then((c) => c.put(req, copia));
          return resp;
        })
        .catch(() => caches.match(req).then((r) => r || caches.match("/")))
    );
    return;
  }

  // Resto (ícones, manifesto): cache primeiro, rede como reserva.
  event.respondWith(
    caches.match(req).then((cached) => cached || fetch(req))
  );
});
