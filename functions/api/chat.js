// Chat da EconoIA: recebe a conversa do site e pergunta ao Gemini.
// A chave fica escondida aqui no servidor (variável GEMINI_API_KEY no Cloudflare).
// Se um modelo estiver lotado ou aposentado, tenta o próximo da lista automaticamente.
//
// Camadas de proteção (nesta ordem): origem do pedido, limite por IP, tamanho e formato da entrada,
// regras da IA fixas no servidor (o navegador não manda instruções), assinatura das respostas
// antigas (histórico falso é descartado) e ferramentas só de leitura.
import { origemPermitida, ipDe, dentroDoLimite } from "../_lib/protecao.js";
import { montaSistema, TAREFAS_LATEX, tarefaDeSistemaAntigo, dadosDeSistemaAntigo } from "../_lib/instrucoes.js";
import { assina, confere } from "../_lib/assinatura.js";
import { DECLARACOES, executaFerramenta, MAX_RODADAS } from "../_lib/ferramentas.js";

const MODELOS = ["gemini-3.8-flash", "gemini-flash-latest", "gemini-3.8-flash-lite", "gemini-flash-lite-latest"];
const PRAZO_TOTAL_MS = 22000;
const MAX_CORPO = 100000;         // caracteres do pedido inteiro
const MAX_TURNOS = 12;            // mensagens do histórico que seguem para a IA
const MAX_TOTAL_CHARS = 30000;    // soma do histórico (corta as mais antigas)
const MAX_CHARS = { chat: 4000, latex: 7000 };
const MAX_CHARS_RESPOSTA_ANTIGA = 12000;
const TTL_CACHE_S = 600;          // perguntas repetidas (primeira pergunta de uma conversa) ficam 10 min no cache

export async function onRequestPost({ request: req, env }) {
  if (!origemPermitida(req)) return json({ error: "Pedido recusado: use o chat pelo site da EconoIA." }, 403);
  const limite = await dentroDoLimite(ipDe(req));
  if (!limite.ok) {
    const msg = limite.limite === "minuto"
      ? `Muitas perguntas seguidas. Espere ${limite.tenteEmSeg} segundos e tente de novo.`
      : "Você atingiu o limite de perguntas de hoje. Volte amanhã!";
    return json({ error: msg, retry: false }, 429, { "Retry-After": String(limite.tenteEmSeg) });
  }

  const key = env.GEMINI_API_KEY;
  if (!key) {
    console.error("chat: GEMINI_API_KEY não configurada");
    return json({ error: "O chat está em manutenção. Tente de novo mais tarde." }, 500);
  }
  const models = [...new Set([env.GEMINI_MODEL, ...MODELOS].filter(Boolean))];

  // ---- entrada: tamanho, formato e modo ----
  let raw;
  try { raw = await req.text(); } catch { return json({ error: "Pedido inválido." }, 400); }
  if (raw.length > MAX_CORPO) return json({ error: "Pedido grande demais." }, 413);
  let body;
  try { body = JSON.parse(raw); } catch { return json({ error: "Pedido inválido." }, 400); }
  if (!body || typeof body !== "object" || Array.isArray(body)) return json({ error: "Pedido inválido." }, 400);

  const pedidoModo = definePedido(body);
  if (!pedidoModo) return json({ error: "Pedido inválido." }, 400);
  const { modo, tarefa, contexto } = pedidoModo;

  const turns = await montaTurnos(body.turns, { modo, segredo: key });
  if (!turns.length || turns[turns.length - 1].role !== "user") return json({ error: "Faça uma pergunta." }, 400);

  const sistema = montaSistema({ modo, tarefa, contexto });

  // ---- cache de perguntas repetidas (só a primeira pergunta de uma conversa, sem histórico) ----
  const cache = globalThis.caches?.default;
  let chaveCache = null;
  if (cache && modo === "chat" && turns.length === 1) {
    const impressao = await sha256(`${sistema}\n---\n${turns[0].parts[0].text.toLowerCase().replace(/\s+/g, " ").trim()}`);
    chaveCache = new Request(`https://cache.econoia.internal/resposta/${impressao}`);
    try {
      const guardada = await cache.match(chaveCache);
      if (guardada) {
        const { text, model } = await guardada.json();
        if (text) return json({ text, sig: await assina(text, key), model, cache: true });
      }
    } catch { /* cache indisponível: segue sem ele */ }
  }

  // ---- pergunta ao Gemini, trocando de modelo se um estiver lotado ----
  const inicio = Date.now();
  let ultimoStatus = 0, ultimaMsg = "";
  for (const model of models) {
    const r = await perguntaAoModelo({ model, key, sistema, contents: turns, inicio, comFerramentas: modo === "chat" });
    if (r.text) {
      if (chaveCache) {
        try {
          await cache.put(chaveCache, new Response(JSON.stringify({ text: r.text, model }), {
            headers: { "Cache-Control": `max-age=${TTL_CACHE_S}` },
          }));
        } catch { /* sem cache, sem problema */ }
      }
      return json({ text: r.text, sig: await assina(r.text, key), model });
    }
    ultimoStatus = r.status; ultimaMsg = r.msg;
    if (r.status === 400 || r.status === 401 || r.status === 403) break; // problema na chave ou no pedido: trocar de modelo não ajuda
    if (r.prazoEsgotado) break;
  }

  // Detalhes técnicos só vão para o registro do Cloudflare, nunca para quem usa o site.
  console.error("chat: falha no Gemini", JSON.stringify({ status: ultimoStatus, msg: String(ultimaMsg).slice(0, 300) }));
  const amigavel =
    ultimoStatus === 429 ? "O limite gratuito do Gemini foi atingido. Tente de novo em 1 minuto." :
    ultimoStatus === 503 || ultimoStatus === 504 || ultimoStatus >= 500 ? "Os servidores do Gemini estão lotados agora. Tente de novo em alguns segundos." :
    ultimoStatus === 400 || ultimoStatus === 401 || ultimoStatus === 403 ? "O chat está em manutenção. Tente de novo mais tarde." :
    "Não consegui responder agora. Tente de novo.";
  return json({ error: amigavel, retry: ultimoStatus === 429 || ultimoStatus >= 500 }, 503);
}

/**
 * Descobre o que o navegador está pedindo e descarta qualquer instrução vinda dele.
 * Formato novo: { modo: "chat", contexto, turns } ou { modo: "latex", tarefa, turns }.
 * Formato antigo (aba aberta antes da atualização): { system, turns }, onde só aproveitamos
 * os dados e o nome da tarefa; as instruções são sempre as do servidor.
 */
export function definePedido(body) {
  const { modo, tarefa } = body;
  if (modo === "latex") return typeof tarefa === "string" && Object.hasOwn(TAREFAS_LATEX, tarefa) ? { modo: "latex", tarefa } : null;
  if (modo === "chat") return { modo: "chat", contexto: typeof body.contexto === "string" ? body.contexto : "" };
  if (modo !== undefined) return null;
  if (typeof body.system !== "string") return null;
  const antiga = tarefaDeSistemaAntigo(body.system);
  if (antiga) return { modo: "latex", tarefa: antiga };
  if (body.system.startsWith("Você é a EconoIA")) return { modo: "chat", contexto: dadosDeSistemaAntigo(body.system) };
  return null;
}

/**
 * Limpa o histórico: só texto, no máximo MAX_TURNOS mensagens, e respostas "da IA" só valem
 * se tiverem a nossa assinatura. Mensagens seguidas do mesmo autor viram uma só.
 */
export async function montaTurnos(brutos, { modo, segredo }) {
  const lista = (Array.isArray(brutos) ? brutos : []).slice(-MAX_TURNOS);
  const limpos = [];
  for (const t of lista) {
    if (!t || typeof t !== "object" || typeof t.content !== "string") continue;
    if (t.role === "assistant") {
      if (modo !== "chat" || t.content.length > MAX_CHARS_RESPOSTA_ANTIGA) continue;
      if (!(await confere(t.content, t.sig, segredo))) continue;
      limpos.push({ role: "model", text: t.content.slice(0, MAX_CHARS.chat) });
    } else {
      limpos.push({ role: "user", text: t.content.slice(0, MAX_CHARS[modo]) });
    }
  }
  // junta mensagens seguidas do mesmo autor (a API exige alternância)
  const juntos = [];
  for (const t of limpos) {
    const ult = juntos[juntos.length - 1];
    if (ult && ult.role === t.role) ult.text += "\n\n" + t.text;
    else juntos.push({ ...t });
  }
  // se o total passar do limite, fica o que é mais recente (a mensagem mais nova sempre entra, cortada se preciso)
  const escolhidos = [];
  let restante = MAX_TOTAL_CHARS;
  for (let i = juntos.length - 1; i >= 0; i--) {
    const { role, text } = juntos[i];
    if (text.length > restante && i !== juntos.length - 1) break;
    const parte = text.length > restante ? text.slice(-restante) : text;
    escolhidos.unshift({ role, text: parte });
    restante -= parte.length;
  }
  return escolhidos
    .filter((t) => t.text.trim())
    .map((t) => ({ role: t.role, parts: [{ text: t.text }] }));
}

/**
 * Faz uma pergunta a UM modelo, atendendo pedidos de ferramenta da IA (no máximo MAX_RODADAS).
 * Devolve { text } ou { status, msg }.
 */
async function perguntaAoModelo({ model, key, sistema, contents, inicio, comFerramentas }) {
  let conversa = contents;
  let ferramentas = comFerramentas;
  for (let rodada = 0; ; rodada++) {
    const resta = PRAZO_TOTAL_MS - (Date.now() - inicio);
    if (resta < 3000) return { status: 504, msg: "prazo esgotado", prazoEsgotado: true };
    const usaFerramentas = ferramentas && rodada < MAX_RODADAS; // na última rodada a IA é obrigada a responder em texto
    const payload = {
      systemInstruction: { parts: [{ text: sistema }] },
      contents: conversa,
      generationConfig: { temperature: 0.4, maxOutputTokens: 1200 },
    };
    if (usaFerramentas) payload.tools = DECLARACOES;

    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), Math.min(resta, 15000));
    let r, j;
    try {
      r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-goog-api-key": key },
        body: JSON.stringify(payload),
        signal: ctrl.signal,
      });
      j = await r.json().catch(() => ({}));
    } catch {
      return { status: 504, msg: "tempo esgotado" };
    } finally {
      clearTimeout(timer);
    }

    if (!r.ok) {
      // Se o Gemini recusou o pedido com ferramentas (400), tenta de novo sem elas antes de desistir.
      if (r.status === 400 && usaFerramentas) { ferramentas = false; rodada--; continue; }
      return { status: r.status, msg: j.error?.message || "" };
    }

    const partes = j.candidates?.[0]?.content?.parts || [];
    const pedidos = partes.filter((p) => p.functionCall);
    if (pedidos.length && usaFerramentas) {
      const respostas = await Promise.all(pedidos.map(async (p, i) => ({
        functionResponse: {
          name: p.functionCall.name,
          response: { resultado: i < 4 ? await executaFerramenta(p.functionCall.name, p.functionCall.args) : { erro: "Muitas ferramentas de uma vez." } },
        },
      })));
      conversa = [...conversa, { role: "model", parts: partes }, { role: "user", parts: respostas }];
      continue;
    }
    const text = partes.filter((p) => !p.thought).map((p) => p.text || "").join("").trim();
    return text ? { text } : { status: 502, msg: "resposta vazia" };
  }
}

async function sha256(texto) {
  const h = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(texto));
  return [...new Uint8Array(h)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

const json = (o, status = 200, extra = {}) =>
  new Response(JSON.stringify(o), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", ...extra },
  });
