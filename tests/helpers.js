// Cache em memória que imita o caches.default do Cloudflare nos testes.
export function cacheFalso() {
  const m = new Map();
  return {
    async match(req) { const v = m.get(req.url); return v === undefined ? undefined : new Response(v); },
    async put(req, res) { m.set(req.url, await res.text()); },
  };
}

export function pedido(url, { method = "POST", origem = "https://econoia.com.br", ip = "1.2.3.4", body } = {}) {
  const headers = { "Content-Type": "application/json", "CF-Connecting-IP": ip };
  if (origem) headers.Origin = origem;
  return new Request(url, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
}
