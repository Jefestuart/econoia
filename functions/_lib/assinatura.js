// Assinatura das respostas da IA (HMAC-SHA256).
//
// Problema: o navegador reenvia a conversa inteira a cada pergunta, inclusive as
// respostas anteriores "da IA". Sem proteção, alguém pode fabricar um histórico falso
// ("antes eu já te mandei obedecer e você aceitou...") para forçar a IA a sair do escopo.
//
// Solução: cada resposta sai do servidor com uma assinatura. Na próxima pergunta, o
// servidor confere a assinatura e descarta qualquer resposta "da IA" que ele não escreveu.
// A chave de assinatura é derivada da GEMINI_API_KEY (que só o servidor conhece), então
// não precisa de nenhum segredo novo no Cloudflare.

const enc = new TextEncoder();

async function chaveHmac(segredo, usos) {
  const base = await crypto.subtle.digest("SHA-256", enc.encode(`econoia-historico-v1|${segredo}`));
  return crypto.subtle.importKey("raw", base, { name: "HMAC", hash: "SHA-256" }, false, usos);
}

const paraBase64Url = (buf) =>
  btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

function deBase64Url(s) {
  const b64 = s.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (s.length % 4)) % 4);
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
}

export async function assina(texto, segredo) {
  const k = await chaveHmac(segredo, ["sign"]);
  return paraBase64Url(await crypto.subtle.sign("HMAC", k, enc.encode(texto)));
}

/** A assinatura é válida para este texto? (comparação em tempo constante, feita pelo WebCrypto) */
export async function confere(texto, assinatura, segredo) {
  if (typeof assinatura !== "string" || assinatura.length < 20 || assinatura.length > 100 || !/^[A-Za-z0-9_-]+$/.test(assinatura)) return false;
  try {
    const k = await chaveHmac(segredo, ["verify"]);
    return await crypto.subtle.verify("HMAC", k, deBase64Url(assinatura), enc.encode(texto));
  } catch {
    return false;
  }
}
