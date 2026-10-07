import { test } from "node:test";
import assert from "node:assert/strict";
import { onRequestGet } from "../functions/data/arquivo/[[caminho]].js";

const roda = async (caminho) => {
  const urls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (u) => { urls.push(String(u)); return new Response('{"ok":1}'); };
  try {
    const r = await onRequestGet({ params: { caminho } });
    return { r, urls };
  } finally { globalThis.fetch = original; }
};

test("serve o índice e as cópias do ramo dados-arquivo", async () => {
  const a = await roda(["indice.json"]);
  assert.equal(a.r.status, 200);
  assert.equal(a.urls[0], "https://raw.githubusercontent.com/Jefestuart/econoia/dados-arquivo/indice.json");
  const b = await roda(["2026-10-06", "series.json"]);
  assert.equal(b.r.status, 200);
  assert.match(b.r.headers.get("Cache-Control"), /max-age=86400/);
  assert.match(b.r.headers.get("Content-Type"), /json/);
});

test("recusa qualquer caminho fora do formato, sem sequer buscar", async () => {
  for (const c of [["..", "main", "x.json"], ["2026-10-06", "data.json"], ["2026-10-06"], ["2026-10-06", "series.json", "x"],
    ["2026-1-6", "series.json"], ["indice.json", "x"], [], [""], ["%2e%2e", "series.json"], undefined]) {
    const { r, urls } = await roda(c);
    assert.equal(r.status, 404, JSON.stringify(c));
    assert.equal(urls.length, 0);
  }
});

test("se o GitHub não tiver o arquivo, devolve 404", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response("x", { status: 404 });
  try {
    const r = await onRequestGet({ params: { caminho: ["2026-10-06", "series.json"] } });
    assert.equal(r.status, 404);
  } finally { globalThis.fetch = original; }
});
