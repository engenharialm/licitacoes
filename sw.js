// App instalável (PWA) do portal de licitações da LM.
// Guarda só a "casca" do site (página, mapa, ícones) para abrir rápido; os dados vêm sempre da nuvem.
const VERSAO = "lm-licitacoes-v2";
const CASCA = ["./", "index.html", "manifest.webmanifest", "logo-lm.png", "logo-pdca.png", "mg-mapa.json", "municipios-mg.json",
  "icon-192.png", "icon-512.png", "icon-maskable-512.png", "apple-touch-icon.png", "favicon-32.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(VERSAO).then(c => c.addAll(CASCA)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(nomes => Promise.all(nomes.filter(n => n !== VERSAO).map(n => caches.delete(n))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", e => {
  const req = e.request;
  const url = new URL(req.url);
  // banco de dados, PNCP, fontes e bibliotecas externas: sempre direto da internet
  if (req.method !== "GET" || url.origin !== self.location.origin) return;

  // a página: tenta a versão nova primeiro (as atualizações chegam na hora); sem internet, usa a guardada
  if (req.mode === "navigate" || url.pathname.endsWith("/") || url.pathname.endsWith("index.html")) {
    e.respondWith(fetch(req)
      .then(resp => { const copia = resp.clone(); caches.open(VERSAO).then(c => c.put(req, copia)); return resp; })
      .catch(() => caches.match(req).then(r => r || caches.match("index.html"))));
    return;
  }

  // ícones, mapa e lista de municípios: usa o guardado e atualiza por trás
  e.respondWith(caches.match(req).then(guardado => {
    const rede = fetch(req).then(resp => {
      if (resp.ok) { const copia = resp.clone(); caches.open(VERSAO).then(c => c.put(req, copia)); }
      return resp;
    }).catch(() => guardado);
    return guardado || rede;
  }));
});
