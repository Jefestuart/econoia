import { test } from "node:test";
import assert from "node:assert/strict";
import { origemPermitida, ipDe, dentroDoLimite } from "../functions/_lib/protecao.js";
import { cacheFalso, pedido } from "./helpers.js";

test("aceita pedidos do próprio site", () => {
  for (const o of ["https://econoia.com.br", "https://www.econoia.com.br", "https://econoia.pages.dev",
    "https://abc123.econoia.pages.dev", "http://localhost:8788"]) {
    assert.equal(origemPermitida(pedido("https://x/api/chat", { origem: o })), true, o);
  }
});

test("recusa outras origens e pedidos sem origem", () => {
  for (const o of ["https://site-malicioso.com", "https://econoia.com.br.golpe.com", "http://econoia.com.br", null]) {
    assert.equal(origemPermitida(pedido("https://x/api/chat", { origem: o })), false, String(o));
  }
});

test("lê o IP informado pelo Cloudflare", () => {
  assert.equal(ipDe(pedido("https://x/", { ip: "9.9.9.9" })), "9.9.9.9");
});

test("limita por minuto e libera no minuto seguinte", async () => {
  const cache = cacheFalso();
  const limites = [{ nome: "minuto", janelaSeg: 60, max: 3 }];
  const agora = 1_700_000_000_000;
  for (let i = 0; i < 3; i++) assert.equal((await dentroDoLimite("1.1.1.1", { cache, agora, limites })).ok, true);
  const bloqueado = await dentroDoLimite("1.1.1.1", { cache, agora, limites });
  assert.equal(bloqueado.ok, false);
  assert.equal(bloqueado.limite, "minuto");
  assert.ok(bloqueado.tenteEmSeg > 0 && bloqueado.tenteEmSeg <= 60);
  // outro IP não é afetado
  assert.equal((await dentroDoLimite("2.2.2.2", { cache, agora, limites })).ok, true);
  // um minuto depois, libera
  assert.equal((await dentroDoLimite("1.1.1.1", { cache, agora: agora + 60_000, limites })).ok, true);
});

test("sem cache disponível, não bloqueia", async () => {
  assert.equal((await dentroDoLimite("1.1.1.1", { cache: null })).ok, true);
});
