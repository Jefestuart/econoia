import { test } from "node:test";
import assert from "node:assert/strict";
import { limpa, tag } from "../functions/api/news.js";

test("limpa CDATA, tags HTML e entidades", () => {
  assert.equal(limpa("<![CDATA[Selic <b>cai</b> &amp; dólar sobe]]>"), "Selic cai & dólar sobe");
  assert.equal(limpa("Infla&#231;&#xE3;o   em\n alta"), "Inflação em alta");
});

test("extrai o conteúdo de uma tag do RSS", () => {
  const item = "<item><title>Ibovespa sobe</title><link>https://exemplo.com/a</link></item>";
  assert.equal(tag(item, "title"), "Ibovespa sobe");
  assert.equal(tag(item, "link"), "https://exemplo.com/a");
  assert.equal(tag(item, "pubDate"), "");
});
