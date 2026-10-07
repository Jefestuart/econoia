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

// Dados de exemplo no formato de data/series.json e data/modelos.json (versão pequena).
export const SERIES = {
  atualizado: "2026-10-06T17:40+00:00",
  ordem: ["ipca", "selic"],
  series: {
    ipca: {
      nome: "IPCA", tema: "Inflação", unidade: "% no mês", freq: "mensal",
      descricao: "Inflação oficial.", fonte: "Banco Central (SGS 433)",
      dados: [["2026-06", 0.16], ["2026-07", 0.07], ["2026-08", -0.32]],
      analise: {
        modelo: "SARIMA(1,0,0)(1,0,1)12", modelado_como: "a própria série",
        sazonal_efeito: [0.0659, 0.2546, 0.1633, 0.0226, -0.0614, -0.1341, -0.2054, -0.3081, -0.0661, 0.0486, 0.0079, 0.2119],
        sazonal_p: 0.0001,
        previsao: [["2026-09", 0.1085123, -0.2682, 0.4409]],
      },
    },
    selic: { nome: "Selic meta", tema: "Juros", unidade: "% ao ano", freq: "mensal", dados: [["2026-08", 14.5]] },
  },
};
export const MODELOS_JSON = {
  atualizado: "2026-10-06T16:53+00:00",
  series: { ipca: { nome: "IPCA", ultimos_12: 4.22, historico: Array.from({ length: 36 }, (_, i) => [`m${i}`, i]), modelos: { sarima: { nome: "SARIMA", previsao: [] } } } },
  var: { nome: "VAR(4)", variaveis: ["Dólar"], amostra: "set/11 a ago/26", observacoes: 176, granger: [{ causa: "Dólar", efeito: "IPCA", F: 3.2, p: 0.015 }], irf: { enorme: "x" } },
};

