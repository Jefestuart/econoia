// Ferramentas que a IA pode chamar. Todas SÓ LEEM os dados que a própria EconoIA já publica
// (data/series.json e data/modelos.json, atualizados pelos robôs do GitHub Actions).
// Nenhuma escreve, apaga, envia nada ou acessa endereço informado pelo usuário:
// o nome do arquivo e o endereço são fixos aqui, e tudo que a IA pede é validado antes.

const BASE = "https://raw.githubusercontent.com/Jefestuart/econoia/main/data/";
const TTL_MS = 5 * 60 * 1000;
const MAX_SAIDA = 7000; // caracteres devolvidos à IA por chamada
export const MAX_RODADAS = 3; // quantas vezes a IA pode pedir ferramentas por pergunta

export const DECLARACOES = [{
  functionDeclarations: [
    {
      name: "listar_series",
      description: "Lista as séries do catálogo da EconoIA (id, nome, tema, unidade, frequência). Use para descobrir o id de uma série antes de consultá-la.",
    },
    {
      name: "consultar_serie",
      description: "Devolve os últimos valores de uma série do catálogo (Banco Central, IBGE, FRED, Ipea), a previsão SARIMA de 12 meses com faixa de 80% e a sazonalidade, quando existirem.",
      parameters: {
        type: "object",
        properties: {
          id: { type: "string", description: "Id da série, como aparece em listar_series (ex.: ipca, selic, dolar, desemprego)." },
          ultimos: { type: "integer", description: "Quantos valores recentes devolver (1 a 60). Padrão: 12." },
        },
        required: ["id"],
      },
    },
    {
      name: "consultar_modelo",
      description: "Devolve as previsões de inflação da EconoIA. 'ipca' ou 'igpm': previsão SARIMA e VAR de 12 meses, acumulado em 12 meses, faixas e backtest. 'var': causalidade de Granger entre dólar, IGP-M, IPCA e Selic.",
      parameters: {
        type: "object",
        properties: { modelo: { type: "string", enum: ["ipca", "igpm", "var"] } },
        required: ["modelo"],
      },
    },
  ],
}];

const memo = new Map();
async function carrega(arquivo, { fetchFn = fetch, agora = Date.now() } = {}) {
  const guardado = memo.get(arquivo);
  if (guardado && agora - guardado.t < TTL_MS) return guardado.v;
  const r = await fetchFn(`${BASE}${arquivo}`, { cf: { cacheTtl: 300 } });
  if (!r.ok) throw new Error(`dados indisponíveis (${r.status})`);
  const v = await r.json();
  memo.set(arquivo, { t: agora, v });
  return v;
}
export const limpaMemoria = () => memo.clear();

const arredonda = (x) => (typeof x === "number" ? Math.round(x * 10000) / 10000 : x);

function listarSeries(series) {
  return {
    atualizado: series.atualizado,
    series: series.ordem.filter((id) => series.series[id]).map((id) => {
      const s = series.series[id];
      return { id, nome: s.nome, tema: s.tema, unidade: s.unidade, frequencia: s.freq };
    }),
  };
}

function consultarSerie(series, { id, ultimos }) {
  if (typeof id !== "string" || !/^[a-z0-9_]{1,40}$/.test(id) || !Object.hasOwn(series.series, id)) {
    return { erro: "Série não encontrada. Use listar_series para ver os ids válidos." };
  }
  const s = series.series[id];
  const n = Math.min(60, Math.max(1, Number.isFinite(+ultimos) ? Math.trunc(+ultimos) : 12));
  const dados = (s.dados || []).slice(-n);
  const saida = {
    id, nome: s.nome, tema: s.tema, unidade: s.unidade, frequencia: s.freq,
    fonte: s.fonte, descricao: s.descricao, atualizado: series.atualizado,
    dados,
  };
  const a = s.analise;
  if (a?.previsao?.length) {
    saida.previsao = {
      modelo: a.modelo, modelado_como: a.modelado_como,
      colunas: ["período", "ponto", "limite inferior 80%", "limite superior 80%"],
      meses: a.previsao.slice(0, 12).map((l) => l.map(arredonda)),
    };
  }
  if (a?.sazonal_efeito?.length === 12) {
    saida.sazonalidade = { efeito_medio_jan_a_dez: a.sazonal_efeito.map(arredonda), p_valor_teste_F: a.sazonal_p };
  }
  return saida;
}

function consultarModelo(modelos, { modelo }) {
  if (modelo === "var") {
    const v = modelos.var || {};
    return {
      atualizado: modelos.atualizado, nome: v.nome, variaveis: v.variaveis, amostra: v.amostra,
      observacoes: v.observacoes, granger: v.granger,
      nota: "Causalidade de Granger: p baixo (< 0,05) indica que o passado da variável 'causa' ajuda a prever a variável 'efeito'.",
    };
  }
  if (!["ipca", "igpm"].includes(modelo) || !modelos.series?.[modelo]) {
    return { erro: "Modelo não encontrado. Use 'ipca', 'igpm' ou 'var'." };
  }
  const m = modelos.series[modelo];
  return { atualizado: modelos.atualizado, ...m, historico: (m.historico || []).slice(-12) };
}

/**
 * Executa uma ferramenta pedida pela IA. Nunca lança erro: devolve {erro} para a IA explicar.
 * `args` vem da IA (que por sua vez leu texto do usuário), então é tratado como não confiável.
 */
export async function executaFerramenta(nome, args, deps = {}) {
  try {
    const a = args && typeof args === "object" && !Array.isArray(args) ? args : {};
    let saida;
    if (nome === "listar_series") saida = listarSeries(await carrega("series.json", deps));
    else if (nome === "consultar_serie") saida = consultarSerie(await carrega("series.json", deps), a);
    else if (nome === "consultar_modelo") saida = consultarModelo(await carrega("modelos.json", deps), a);
    else return { erro: "Ferramenta desconhecida." };
    const texto = JSON.stringify(saida);
    if (texto.length <= MAX_SAIDA) return saida;
    // Resposta grande demais: corta o histórico em vez de estourar o contexto da IA.
    if (Array.isArray(saida.dados)) return { ...saida, dados: saida.dados.slice(-12), aviso: "dados cortados nos 12 últimos" };
    return { erro: "Resultado grande demais; peça um recorte menor." };
  } catch (e) {
    return { erro: "Não consegui ler os dados agora." };
  }
}
