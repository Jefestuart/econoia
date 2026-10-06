// Arquivos de dados vêm direto do GitHub, sempre a versão mais nova:
// o robô atualiza sem republicar o site (commits com [skip ci]).
const PERMITIDOS = new Set(["data.json", "modelos.json", "series.json"]);

export async function onRequestGet({ params, request, env }) {
  const arquivo = String(params.arquivo || "");
  // Outros arquivos da pasta (como a reserva local.json) seguem como arquivos normais do site.
  if (!PERMITIDOS.has(arquivo)) return env?.ASSETS ? env.ASSETS.fetch(request) : new Response("Não encontrado", { status: 404 });
  const r = await fetch(`https://raw.githubusercontent.com/Jefestuart/econoia/main/data/${arquivo}`, { cf: { cacheTtl: 60 } });
  return new Response(r.body, {
    status: r.status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "public, max-age=60" },
  });
}
