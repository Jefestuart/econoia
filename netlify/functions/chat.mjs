// Chat da EconoIA: recebe a conversa do site e pergunta ao Gemini.
// A chave fica escondida aqui no servidor (variável GEMINI_API_KEY no Netlify).
// Se um modelo estiver lotado ou aposentado, tenta o próximo da lista automaticamente.
const MODELOS = ["gemini-3.8-flash", "gemini-flash-latest", "gemini-3.8-flash-lite", "gemini-flash-lite-latest"];
const PRAZO_TOTAL_MS = 22000;

export default async (req) => {
  if (req.method !== "POST") return new Response("Use POST", { status: 405 });
  const key = Netlify.env.get("GEMINI_API_KEY");
  if (!key) return json({ error: "Chave do Gemini não configurada no Netlify (GEMINI_API_KEY)." }, 500);
  const models = [...new Set([Netlify.env.get("GEMINI_MODEL"), ...MODELOS].filter(Boolean))];

  let body;
  try { body = await req.json(); } catch { return json({ error: "Pedido inválido." }, 400); }
  const system = String(body.system || "").slice(0, 20000);
  const turns = (Array.isArray(body.turns) ? body.turns : []).slice(-12)
    .map(t => ({ role: t.role === "assistant" ? "model" : "user", parts: [{ text: String(t.content || "").slice(0, 4000) }] }));
  if (!turns.length || turns[turns.length - 1].role !== "user") return json({ error: "Faça uma pergunta." }, 400);

  const payload = JSON.stringify({
    systemInstruction: { parts: [{ text: system }] },
    contents: turns,
    generationConfig: { temperature: 0.4, maxOutputTokens: 1200 },
  });

  const inicio = Date.now();
  let ultimoStatus = 0, ultimaMsg = "";
  for (const model of models) {
    const resta = PRAZO_TOTAL_MS - (Date.now() - inicio);
    if (resta < 3000) break;
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), Math.min(resta, 15000));
    try {
      const r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-goog-api-key": key },
        body: payload,
        signal: ctrl.signal,
      });
      const j = await r.json().catch(() => ({}));
      if (r.ok) {
        const text = (j.candidates?.[0]?.content?.parts || []).map(p => p.text || "").join("").trim();
        if (text) return json({ text, model });
        ultimoStatus = 502; ultimaMsg = "resposta vazia";
        continue;
      }
      ultimoStatus = r.status; ultimaMsg = j.error?.message || "";
      // 400/403 = problema na chave ou no pedido: não adianta trocar de modelo
      if (r.status === 400 || r.status === 401 || r.status === 403) break;
    } catch (e) {
      ultimoStatus = 504; ultimaMsg = "tempo esgotado";
    } finally {
      clearTimeout(timer);
    }
  }

  const amigavel =
    ultimoStatus === 429 ? "O limite gratuito do Gemini foi atingido. Tente de novo em 1 minuto." :
    ultimoStatus === 503 || ultimoStatus === 504 || ultimoStatus >= 500 ? "Os servidores do Gemini estão lotados agora. Tente de novo em alguns segundos." :
    ultimoStatus === 400 || ultimoStatus === 403 ? "A chave do Gemini foi recusada. Confira a variável GEMINI_API_KEY no Netlify." :
    "Não consegui responder agora. Tente de novo.";
  return json({ error: amigavel, detalhe: ultimaMsg, retry: ultimoStatus === 429 || ultimoStatus >= 500 }, 503);
};

const json = (o, status = 200) => new Response(JSON.stringify(o), { status, headers: { "Content-Type": "application/json" } });

export const config = { path: "/api/chat" };
