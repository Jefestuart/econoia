import { test, afterEach } from "node:test";
import assert from "node:assert/strict";
import { onRequestGet } from "../functions/data/[arquivo].js";

const fetchOriginal = globalThis.fetch;
afterEach(() => { globalThis.fetch = fetchOriginal; });

test("serve data.json e modelos.json direto do GitHub", async () => {
  const pedidos = [];
  globalThis.fetch = async (url) => { pedidos.push(String(url)); return new Response('{"ok":true}'); };
  for (const arquivo of ["data.json", "modelos.json"]) {
    const r = await onRequestGet({ params: { arquivo } });
    assert.equal(r.status, 200);
    assert.deepEqual(await r.json(), { ok: true });
  }
  assert.match(pedidos[1], /raw\.githubusercontent\.com\/Jefestuart\/econoia\/main\/data\/modelos\.json$/);
});

test("outros arquivos não vêm do GitHub: seguem como arquivos do próprio site", async () => {
  globalThis.fetch = async () => { throw new Error("não deveria buscar no GitHub"); };
  const servidos = [];
  const env = { ASSETS: { fetch: async (req) => { servidos.push(new URL(req.url).pathname); return new Response("arquivo local"); } } };
  for (const arquivo of ["local.json", "segredo.env"]) {
    const request = new Request(`https://econoia.com.br/data/${arquivo}`);
    const r = await onRequestGet({ params: { arquivo }, request, env });
    assert.equal(await r.text(), "arquivo local");
  }
  assert.deepEqual(servidos, ["/data/local.json", "/data/segredo.env"]);
});
