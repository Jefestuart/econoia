// Chat da EconoIA: recebe a conversa do site e pergunta ao Gemini.
// A chave fica escondida aqui no servidor (variável GEMINI_API_KEY no Netlify).
export default async (req) => {
  if (req.method !== "POST") return new Response("Use POST", { status: 405 });
  const key = Netlify.env.get("GEMINI_API_KEY");
  // Tenta o modelo configurado e, se o Google tiver aposentado, os próximos da lista.
  const models = [Netlify.env.get("GEMINI_MODEL"), "gemini-3.8-flash", "gemini-flash-latest"].filter(Boolean);
  if (!key) return json({ error: "Chave do Gemini não configurada no Netlify (GEMINI_API_KEY)." }, 500);

  let body;
  try { body = await req.json(); } catch { return json({ error: "Pedido inválido." }, 400); }
  const system = String(body.system || "").slice(0, 20000);
  const turns = (Array.isArray(body.turns) ? body.turns : []).slice(-12)
    .map(t => ({ role: t.role === "assistant" ? "model" : "user", parts: [{ text: String(t.content || "").slice(0, 4000) }] }));
  if (!turns.length || turns[turns.length - 1].role !== "user") return json({ error: "Faça uma pergunta." }, 400);

  const payload = JSON.stringify({
    systemInstruction: { parts: [{ text: system }] },
    contents: turns,
    generationConfig: { temperature: 0.4, maxOutputTokens: 1500 },
  });
  let r, j = {};
  for (const model of models) {
    r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-goog-api-key": key },
      body: payload,
    });
    j = await r.json().catch(() => ({}));
    if (r.ok) break;
    const m = (j.error?.message || "").toLowerCase();
    if (!(r.status === 404 || m.includes("no longer available") || m.includes("not found"))) break;
  }
  if (!r.ok) {
    const msg = r.status === 429 ? "Limite gratuito do Gemini atingido. Tente em alguns minutos." : (j.error?.message || "Erro no Gemini.");
    return json({ error: msg }, r.status);
  }
  const text = (j.candidates?.[0]?.content?.parts || []).map(p => p.text || "").join("").trim();
  return json({ text: text || "Não consegui gerar uma resposta. Tente reformular." });
};

const json = (o, status = 200) => new Response(JSON.stringify(o), { status, headers: { "Content-Type": "application/json" } });

export const config = { path: "/api/chat" };
