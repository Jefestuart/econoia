// Últimas notícias de economia em português, via RSS público das próprias fontes.
// Só repassa título, fonte, horário e link para a matéria original (nada de texto da matéria).
// O resultado fica em cache em cache por 10 minutos.
const FONTES = [
  { nome: "InfoMoney", url: "https://www.infomoney.com.br/feed/" },
  { nome: "G1 Economia", url: "https://g1.globo.com/rss/g1/economia/" },
  { nome: "Agência Brasil", url: "https://agenciabrasil.ebc.com.br/rss/economia/feed.xml" },
];
const MAX_ITENS = 8;

const ent = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " " };
export function limpa(s = "") {
  return s
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1")
    .replace(/<[^>]+>/g, "")
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(+n))
    .replace(/&#x([0-9a-f]+);/gi, (_, n) => String.fromCodePoint(parseInt(n, 16)))
    .replace(/&(\w+);/g, (m, n) => ent[n] ?? m)
    .replace(/\s+/g, " ")
    .trim();
}
export const tag = (xml, t) => { const m = xml.match(new RegExp(`<${t}[^>]*>([\\s\\S]*?)</${t}>`, "i")); return m ? limpa(m[1]) : ""; };

async function lerFonte({ nome, url }) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), 6000);
  try {
    const r = await fetch(url, { signal: ctl.signal, headers: { "User-Agent": "EconoIA/1.0 (+https://econoia.com.br)" } });
    if (!r.ok) return [];
    const xml = await r.text();
    const itens = xml.match(/<item[\s>][\s\S]*?<\/item>/gi) || [];
    return itens.slice(0, 10).map((it) => {
      const titulo = tag(it, "title");
      let link = tag(it, "link") || tag(it, "guid");
      const data = Date.parse(tag(it, "pubDate") || tag(it, "dc:date")) || 0;
      if (!/^https?:\/\//i.test(link)) link = "";
      return { titulo, link, fonte: nome, data };
    }).filter((n) => n.titulo && n.link);
  } catch { return []; } finally { clearTimeout(timer); }
}

export async function onRequestGet() {
  const listas = await Promise.all(FONTES.map(lerFonte));
  const vistos = new Set();
  const noticias = listas.flat()
    .sort((a, b) => b.data - a.data)
    .filter((n) => { const k = n.titulo.toLowerCase(); if (vistos.has(k)) return false; vistos.add(k); return true; })
    .slice(0, MAX_ITENS);
  return new Response(JSON.stringify({ atualizado: Date.now(), noticias }), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": noticias.length ? "public, max-age=600" : "no-store",
    },
  });
}
