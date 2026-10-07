// Arquivo diário dos dados: /data/arquivo/indice.json e /data/arquivo/AAAA-MM-DD/{series,modelos}.json.
// As cópias ficam no ramo `dados-arquivo` do GitHub (o robô grava lá, longe do ramo principal).
// Só aceita caminhos nesses formatos exatos; qualquer outra coisa dá 404.
const BASE = "https://raw.githubusercontent.com/Jefestuart/econoia/dados-arquivo/";
const VALIDO = /^(indice\.json|\d{4}-\d{2}-\d{2}\/(series|modelos)\.json)$/;

export async function onRequestGet({ params }) {
  const partes = Array.isArray(params.caminho) ? params.caminho : [params.caminho || ""];
  const caminho = partes.join("/");
  if (!VALIDO.test(caminho)) return new Response("Não encontrado", { status: 404 });
  const r = await fetch(BASE + caminho, { cf: { cacheTtl: 300 } });
  const imutavel = caminho !== "indice.json"; // cópia de um dia não muda depois
  return new Response(r.ok ? r.body : "Não encontrado", {
    status: r.ok ? 200 : 404,
    headers: {
      "Content-Type": r.ok ? "application/json; charset=utf-8" : "text/plain; charset=utf-8",
      "Cache-Control": r.ok ? (imutavel ? "public, max-age=86400" : "public, max-age=300") : "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}
