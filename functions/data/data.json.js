// Os dados vêm direto do GitHub, sempre a versão mais nova (o robô atualiza a cada 30 min).
export async function onRequestGet() {
  const r = await fetch("https://raw.githubusercontent.com/Jefestuart/econoia/main/data/data.json", { cf: { cacheTtl: 60 } });
  return new Response(r.body, {
    status: r.status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "public, max-age=60" },
  });
}
