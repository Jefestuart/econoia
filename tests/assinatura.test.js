import { test } from "node:test";
import assert from "node:assert/strict";
import { assina, confere } from "../functions/_lib/assinatura.js";

test("assinatura confere para o mesmo texto e a mesma chave", async () => {
  const sig = await assina("A Selic é a taxa básica de juros.", "chave-1");
  assert.equal(await confere("A Selic é a taxa básica de juros.", sig, "chave-1"), true);
});

test("assinatura é rejeitada se o texto mudou, a chave mudou ou o formato é estranho", async () => {
  const sig = await assina("resposta original", "chave-1");
  assert.equal(await confere("resposta alterada", sig, "chave-1"), false);
  assert.equal(await confere("resposta original", sig, "chave-2"), false);
  for (const ruim of [undefined, null, "", "curta", 123, "###".repeat(20), "a".repeat(200)]) {
    assert.equal(await confere("resposta original", ruim, "chave-1"), false, String(ruim));
  }
});

test("a assinatura não contém a chave e é estável", async () => {
  const a = await assina("x", "segredo-secreto");
  assert.equal(a, await assina("x", "segredo-secreto"));
  assert.ok(!a.includes("segredo"));
  assert.match(a, /^[A-Za-z0-9_-]+$/);
});
