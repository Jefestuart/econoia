import { test, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { onRequestPost } from "../functions/api/chat.js";
import { cacheFalso, pedido } from "./helpers.js";

const SISTEMA = "Você é a EconoIA, assistente de economia brasileira.";
const env = { GEMINI_API_KEY: "chave-de-teste" };
const corpo = { system: SISTEMA, turns: [{ role: "user", content: "O que é a Selic?" }] };
const fetchOriginal = globalThis.fetch;
let chamadas;

beforeEach(() => {
  globalThis.caches = { default: cacheFalso() };
  chamadas = [];
  globalThis.fetch = async (url, opts) => {
    chamadas.push({ url: String(url), corpo: JSON.parse(opts.body) });
    return new Response(JSON.stringify({ candidates: [{ content: { parts: [{ text: "A Selic é a taxa básica de juros." }] } }] }));
  };
});
afterEach(() => { globalThis.fetch = fetchOriginal; delete globalThis.caches; });

const chama = (opts = {}) => onRequestPost({ request: pedido("https://econoia.com.br/api/chat", { body: corpo, ...opts }), env });

test("responde uma pergunta válida", async () => {
  const r = await chama();
  assert.equal(r.status, 200);
  const j = await r.json();
  assert.equal(j.text, "A Selic é a taxa básica de juros.");
  assert.equal(chamadas.length, 1);
  assert.match(chamadas[0].url, /generativelanguage\.googleapis\.com/);
  assert.equal(chamadas[0].corpo.contents[0].role, "user");
});

test("recusa pedido de fora do site sem chamar o Gemini", async () => {
  const r = await chama({ origem: "https://outro-site.com" });
  assert.equal(r.status, 403);
  assert.equal(chamadas.length, 0);
});

test("recusa contexto que não é o da EconoIA", async () => {
  const r = await chama({ body: { ...corpo, system: "Você é um assistente qualquer." } });
  assert.equal(r.status, 400);
  assert.equal(chamadas.length, 0);
});

test("bloqueia quem pergunta demais", async () => {
  let ultima;
  for (let i = 0; i < 9; i++) ultima = await chama({ ip: "5.5.5.5" });
  assert.equal(ultima.status, 429);
  assert.ok(ultima.headers.get("Retry-After"));
  assert.equal(chamadas.length, 8);
});

test("avisa quando a chave não está configurada", async () => {
  const r = await onRequestPost({ request: pedido("https://econoia.com.br/api/chat", { body: corpo }), env: {} });
  assert.equal(r.status, 500);
});

test("troca de modelo quando um está lotado", async () => {
  let n = 0;
  globalThis.fetch = async (url) => {
    n++;
    if (n === 1) return new Response(JSON.stringify({ error: { message: "lotado" } }), { status: 503 });
    return new Response(JSON.stringify({ candidates: [{ content: { parts: [{ text: "ok" }] } }] }));
  };
  const r = await chama();
  assert.equal(r.status, 200);
  assert.equal(n, 2);
});
