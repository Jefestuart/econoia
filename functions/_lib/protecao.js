// Proteção do chat contra abuso: só aceita pedidos vindos do próprio site
// e limita quantas perguntas cada endereço IP pode fazer por minuto e por dia.
// Assim ninguém consegue usar a chave do Gemini em loop por fora do site.

export const ORIGENS_PERMITIDAS = [
  /^https:\/\/(www\.)?econoia\.com\.br$/,
  /^https:\/\/([a-z0-9-]+\.)?econoia\.pages\.dev$/,
  /^https:\/\/econoia-br\.netlify\.app$/,
  /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/,
];

export const LIMITES = [
  { nome: "minuto", janelaSeg: 60, max: 8 },
  { nome: "dia", janelaSeg: 86400, max: 120 },
];

/** O pedido veio de uma página do próprio site? (navegadores sempre mandam Origin em POST) */
export function origemPermitida(req) {
  const origem = req.headers.get("Origin");
  if (!origem) return false;
  return ORIGENS_PERMITIDAS.some((re) => re.test(origem));
}

/** IP de quem pediu, informado pelo Cloudflare. */
export function ipDe(req) {
  return req.headers.get("CF-Connecting-IP") || req.headers.get("X-Forwarded-For")?.split(",")[0].trim() || "desconhecido";
}

/**
 * Conta o pedido e diz se ainda está dentro do limite.
 * Usa o cache do Cloudflare como contador (gratuito, sem banco de dados).
 * O contador vale por data center, então é uma barreira contra abuso, não uma contagem exata.
 * `cache` e `agora` podem ser trocados nos testes.
 */
export async function dentroDoLimite(ip, { cache = globalThis.caches?.default, agora = Date.now(), limites = LIMITES } = {}) {
  if (!cache) return { ok: true };
  for (const { nome, janelaSeg, max } of limites) {
    const janela = Math.floor(agora / 1000 / janelaSeg);
    const chave = new Request(`https://limite.econoia.internal/${nome}/${encodeURIComponent(ip)}/${janela}`);
    const atual = await cache.match(chave);
    const usados = atual ? parseInt(await atual.text(), 10) || 0 : 0;
    if (usados >= max) {
      const resta = janelaSeg - (Math.floor(agora / 1000) % janelaSeg);
      return { ok: false, limite: nome, tenteEmSeg: resta };
    }
    await cache.put(chave, new Response(String(usados + 1), {
      headers: { "Cache-Control": `max-age=${janelaSeg}` },
    }));
  }
  return { ok: true };
}
