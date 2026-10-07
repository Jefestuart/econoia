import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { executaFerramenta, limpaMemoria } from "../functions/_lib/ferramentas.js";
import { SERIES, MODELOS_JSON } from "./helpers.js";

let urls;
const fetchFalso = async (url) => {
  urls.push(String(url));
  const u = String(url);
  if (u.endsWith("/series.json")) return new Response(JSON.stringify(SERIES));
  if (u.endsWith("/modelos.json")) return new Response(JSON.stringify(MODELOS_JSON));
  return new Response("nao", { status: 404 });
};
const roda = (nome, args) => executaFerramenta(nome, args, { fetchFn: fetchFalso });

beforeEach(() => { limpaMemoria(); urls = []; });

test("listar_series devolve o catálogo", async () => {
  const r = await roda("listar_series", {});
  assert.deepEqual(r.series.map((s) => s.id), ["ipca", "selic"]);
});

test("consultar_serie devolve dados, previsão e sazonalidade", async () => {
  const r = await roda("consultar_serie", { id: "ipca", ultimos: 2 });
  assert.equal(r.nome, "IPCA");
  assert.deepEqual(r.dados, [["2026-07", 0.07], ["2026-08", -0.32]]);
  assert.equal(r.previsao.meses[0][1], 0.1085);
  assert.equal(r.sazonalidade.efeito_medio_jan_a_dez.length, 12);
});

test("consultar_serie recusa ids fora do catálogo (inclusive tentativas de truque)", async () => {
  for (const id of ["nao_existe", "../secreto", "__proto__", "constructor", "IPCA", "", 5, null, { x: 1 }]) {
    const r = await roda("consultar_serie", { id });
    assert.ok(r.erro, String(id));
  }
});

test("a quantidade de valores é limitada", async () => {
  assert.equal((await roda("consultar_serie", { id: "ipca", ultimos: 9999 })).dados.length, 3);
  assert.equal((await roda("consultar_serie", { id: "ipca", ultimos: -5 })).dados.length, 1);
  assert.equal((await roda("consultar_serie", { id: "ipca", ultimos: "abc" })).dados.length, 3);
});

test("consultar_modelo devolve ipca e var, sem a parte pesada", async () => {
  const a = await roda("consultar_modelo", { modelo: "ipca" });
  assert.equal(a.historico.length, 12);
  const v = await roda("consultar_modelo", { modelo: "var" });
  assert.equal(v.granger[0].p, 0.015);
  assert.equal(v.irf, undefined);
  assert.ok((await roda("consultar_modelo", { modelo: "selic" })).erro);
});

test("ferramenta desconhecida e argumentos estranhos não derrubam nada", async () => {
  assert.ok((await roda("apagar_tudo", {})).erro);
  assert.ok((await roda("consultar_serie", null)).erro);
  assert.ok((await roda("consultar_serie", [1, 2])).erro);
});

test("só lê arquivos fixos do repositório e guarda em memória por alguns minutos", async () => {
  await roda("consultar_serie", { id: "ipca" });
  await roda("consultar_serie", { id: "selic" });
  assert.equal(urls.length, 1);
  assert.match(urls[0], /^https:\/\/raw\.githubusercontent\.com\/Jefestuart\/econoia\/main\/data\/series\.json$/);
});

test("se os dados estiverem fora do ar, devolve erro em vez de quebrar", async () => {
  const r = await executaFerramenta("listar_series", {}, { fetchFn: async () => new Response("x", { status: 500 }) });
  assert.ok(r.erro);
});
