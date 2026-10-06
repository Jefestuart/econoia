"""Catálogo de indicadores da EconoIA: baixa as séries históricas mensais e, para cada uma,
calcula a sazonalidade e uma previsão SARIMA de 12 meses (módulo "Prever o futuro").

Fontes: Banco Central (SGS), Fed de St. Louis (FRED) e Ipea (Ipeadata). Todas públicas e gratuitas.
Saída: data/series.json. Uma série que falhar mantém a última versão boa.
"""
import csv
import datetime
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request

import numpy as np
from scipy import stats

sys.path.insert(0, os.path.dirname(__file__))
import modelos as M  # noqa: E402

INICIO = datetime.date(2003, 1, 1)
UA = {"User-Agent": "EconoIA/1.0 (+https://econoia.com.br)"}

# transf: como virar série mensal ("mensal" = já é mensal; "media" = média dos dias do mês;
#         "yoy" = variação em 12 meses de um índice)
# modelar: como o SARIMA enxerga a série ("nivel" = a própria série, já oscila em torno de uma média;
#          "dif" = variação mês a mês; "logdif" = variação % mês a mês). A previsão volta para o nível.
S = lambda id_, nome, tema, cod, un, desc, transf="mensal", modelar="nivel", prever=True: {  # noqa: E731
    "id": id_, "nome": nome, "tema": tema, "origem": "sgs", "codigo": cod, "unidade": un,
    "descricao": desc, "transf": transf, "modelar": modelar, "prever": prever}
F = lambda id_, nome, cod, un, desc, transf="mensal", modelar="dif", fonte="FRED": {  # noqa: E731
    "id": id_, "nome": nome, "tema": "Mundo", "origem": "fred", "codigo": cod, "unidade": un,
    "descricao": desc, "transf": transf, "modelar": modelar, "prever": True, "fonte": fonte}

CATALOGO = [
    # ---------------- Inflação
    S("ipca", "IPCA", "Inflação", 433, "% no mês", "Inflação oficial do Brasil, medida pelo IBGE. É a referência da meta do Banco Central."),
    S("ipca15", "IPCA-15", "Inflação", 7478, "% no mês", "Prévia do IPCA, com coleta do dia 16 do mês anterior ao dia 15 do mês de referência."),
    S("inpc", "INPC", "Inflação", 188, "% no mês", "Inflação das famílias com renda de 1 a 5 salários mínimos. Corrige o salário mínimo e benefícios."),
    S("igpm", "IGP-M", "Inflação", 189, "% no mês", "Índice da FGV muito usado em contratos de aluguel. Pesa muito preços no atacado e câmbio."),
    S("igpdi", "IGP-DI", "Inflação", 190, "% no mês", "Irmão do IGP-M, com período de coleta no mês fechado."),
    S("incc", "INCC", "Inflação", 192, "% no mês", "Custo da construção civil (materiais e mão de obra). Corrige contratos de imóveis na planta."),
    S("difusao", "Difusão do IPCA", "Inflação", 21379, "% dos itens", "Parcela dos itens do IPCA que subiram de preço no mês. Mostra se a alta é concentrada ou espalhada."),
    S("nucleo_ex0", "Núcleo EX0", "Inflação", 11427, "% no mês", "IPCA sem alimentos no domicílio e preços administrados. Núcleos tiram o que é muito volátil."),
    S("nucleo_ex3", "Núcleo EX3", "Inflação", 27839, "% no mês", "IPCA sem alimentos, energia e itens voláteis. Um dos núcleos mais acompanhados pelo Copom."),
    S("nucleo_ms", "Núcleo MS", "Inflação", 4466, "% no mês", "Médias aparadas com suavização: corta os extremos de cada mês."),
    S("nucleo_dp", "Núcleo DP", "Inflação", 16122, "% no mês", "Dupla ponderação: dá menos peso aos itens que mais oscilam."),
    S("nucleo_p55", "Núcleo P55", "Inflação", 28751, "% no mês", "Percentil 55 da distribuição das variações do IPCA."),
    S("ipca_servicos", "IPCA serviços", "Inflação", 10844, "% no mês", "Preços de serviços (aluguel, escola, salão, restaurante). Reage ao mercado de trabalho."),
    S("ipca_industriais", "IPCA bens industriais", "Inflação", 27863, "% no mês", "Produtos industrializados. Sensível ao câmbio e a preços de matérias-primas."),
    S("ipca_administrados", "IPCA administrados", "Inflação", 4449, "% no mês", "Preços definidos por contrato ou governo: energia, combustíveis, ônibus, plano de saúde."),
    S("ipca_livres", "IPCA livres", "Inflação", 11428, "% no mês", "Preços definidos pelo mercado. É onde os juros agem mais diretamente."),
    # ---------------- Juros
    S("selic", "Selic meta", "Juros", 432, "% ao ano", "Taxa básica de juros definida pelo Copom a cada 45 dias.", transf="media", modelar="dif"),
    S("selic_efetiva", "Selic efetiva", "Juros", 4189, "% ao ano", "Taxa média de fato praticada nas operações entre bancos com títulos públicos.", modelar="dif"),
    S("cdi", "CDI", "Juros", 4389, "% ao ano", "Taxa dos empréstimos entre bancos. Referência de CDBs e fundos de renda fixa.", transf="media", modelar="dif"),
    S("tr", "TR", "Juros", 7811, "% no mês", "Taxa Referencial. Compõe o rendimento da poupança e do FGTS."),
    S("poupanca", "Poupança", "Juros", 25, "% no mês", "Rendimento mensal da caderneta de poupança.", transf="media"),
    # ---------------- Câmbio e setor externo
    S("dolar", "Dólar", "Câmbio e setor externo", 3698, "R$", "Dólar comercial PTAX de venda, média do mês.", modelar="logdif"),
    S("euro", "Euro", "Câmbio e setor externo", 21620, "R$", "Euro PTAX de venda, média do mês.", transf="media", modelar="logdif"),
    S("reservas", "Reservas internacionais", "Câmbio e setor externo", 3546, "US$ milhões", "Moeda estrangeira guardada pelo Banco Central. Funciona como colchão contra crises cambiais.", modelar="logdif"),
    S("idp", "Investimento direto no país", "Câmbio e setor externo", 22885, "US$ milhões no mês", "Dinheiro estrangeiro que entra para abrir ou comprar empresas no Brasil."),
    S("transacoes", "Transações correntes", "Câmbio e setor externo", 22701, "US$ milhões no mês", "Saldo do Brasil com o exterior em bens, serviços e rendas. Negativo = o país gasta mais do que recebe."),
    # ---------------- Atividade
    S("ibcbr", "IBC-Br", "Atividade", 24364, "índice (2002 = 100)", "Prévia mensal do PIB feita pelo Banco Central, com ajuste sazonal.", modelar="logdif"),
    S("pim", "Produção industrial", "Atividade", 21859, "índice (2022 = 100)", "Produção da indústria geral (IBGE/PIM-PF), sem ajuste sazonal: dá para ver o efeito de férias e feriados.", modelar="logdif"),
    S("varejo", "Vendas no varejo", "Atividade", 1455, "índice (2022 = 100)", "Volume de vendas do comércio varejista restrito (IBGE/PMC), sem ajuste sazonal: dá para ver o pico de dezembro.", modelar="logdif"),
    # ---------------- Trabalho e renda
    S("desemprego", "Desemprego", "Trabalho e renda", 24369, "% da força de trabalho", "Taxa de desocupação da PNAD Contínua (IBGE), em trimestres móveis.", modelar="dif"),
    S("salario_minimo", "Salário mínimo", "Trabalho e renda", 1619, "R$", "Valor nominal do salário mínimo nacional.", modelar="logdif", prever=False),
    {"id": "salario_minimo_real", "nome": "Salário mínimo real", "tema": "Trabalho e renda", "origem": "ipea",
     "codigo": "GAC12_SALMINRE12", "unidade": "R$ de hoje",
     "descricao": "Salário mínimo corrigido pela inflação, em reais de hoje (Ipea). Mostra o poder de compra ao longo do tempo.",
     "transf": "mensal", "modelar": "logdif", "prever": True},
    {"id": "gini", "nome": "Índice de Gini", "tema": "Trabalho e renda", "origem": "ipea",
     "codigo": "auto:Gini", "unidade": "índice (0 a 100)", "freq": "anual",
     "descricao": "Desigualdade de renda no Brasil: 0 seria todos com a mesma renda, 100 seria uma pessoa com toda a renda. Série anual (Ipea, com dados do IBGE).",
     "transf": "anual", "modelar": "nivel", "prever": False},
    # ---------------- Contas públicas
    S("divida_bruta", "Dívida bruta", "Contas públicas", 13762, "% do PIB", "Dívida bruta do governo geral. Principal indicador de solvência acompanhado pelo mercado.", modelar="dif"),
    S("dlsp", "Dívida líquida", "Contas públicas", 4513, "% do PIB", "Dívida líquida do setor público: a dívida bruta menos os créditos do governo.", modelar="dif"),
    # ---------------- Mundo
    F("cpi_eua", "Inflação dos EUA (CPI)", "CPIAUCSL", "% em 12 meses", "Índice de preços ao consumidor americano, variação em 12 meses.", transf="yoy"),
    F("fed", "Juro do Fed", "FEDFUNDS", "% ao ano", "Taxa básica dos Estados Unidos, que influencia o dólar e o fluxo de capital no mundo todo."),
    F("treasury10", "Treasury 10 anos", "GS10", "% ao ano", "Juro do título de 10 anos do governo americano. Referência de risco para o mundo."),
    F("bce", "Juro do BCE", "ECBMRRFR", "% ao ano", "Taxa principal de refinanciamento do Banco Central Europeu.", transf="media"),
    F("minerio", "Minério de ferro", "PIORECRUSDM", "US$/tonelada", "Preço internacional do minério de ferro, principal produto da Vale (FMI).", modelar="logdif"),
    F("brent", "Petróleo Brent", "POILBREUSDM", "US$/barril", "Preço do petróleo de referência internacional (FMI).", modelar="logdif"),
]

FONTES = {"sgs": "Banco Central (SGS {c})", "fred": "FRED/Fed de St. Louis ({c})", "ipea": "Ipeadata/Ipea ({c})"}
IPEA = "http://www.ipeadata.gov.br/api/odata4"


# ======================================================================= download

def _get(url, timeout=60, tentativas=5):
    """Busca com novas tentativas: o Banco Central recusa (429/5xx) quando recebe pedidos demais seguidos."""
    for i in range(tentativas):
        time.sleep(0.4)
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code == 404 or i == tentativas - 1 or (e.code < 500 and e.code != 429):
                raise
        except (urllib.error.URLError, TimeoutError):
            if i == tentativas - 1:
                raise
        time.sleep(3 * (i + 1))


def baixar_sgs(codigo):
    """Séries diárias têm limite de 10 anos por consulta: busca em blocos de 5 anos."""
    hoje = datetime.date.today()
    pontos = {}
    ini = INICIO
    while ini <= hoje:
        fim = min(datetime.date(ini.year + 5, 1, 1) - datetime.timedelta(days=1), hoje)
        url = (f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json"
               f"&dataInicial={ini:%d/%m/%Y}&dataFinal={fim:%d/%m/%Y}")
        dados = None
        for tentativa in range(4):
            try:
                dados = json.loads(_get(url))
                break
            except urllib.error.HTTPError as e:
                if e.code == 404:  # bloco sem dados (série começa depois)
                    dados = []
                    break
                raise
            except json.JSONDecodeError:
                # o SGS às vezes responde uma página de erro no lugar do JSON: tenta de novo,
                # e se persistir, falha (para manter a versão anterior em vez de salvar a série cortada)
                time.sleep(5 * (tentativa + 1))
        if dados is None:
            raise ValueError(f"resposta inválida do SGS no bloco {ini:%Y}-{fim:%Y}")
        for d in dados:
            try:
                pontos[datetime.datetime.strptime(d["data"], "%d/%m/%Y").date()] = float(d["valor"])
            except (ValueError, TypeError):
                continue
        ini = fim + datetime.timedelta(days=1)
    if not pontos:
        raise ValueError("série vazia")
    return pontos


def baixar_fred(codigo):
    txt = _get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={codigo}&cosd={INICIO.year - 1}-01-01")
    pontos = {}
    for linha in csv.DictReader(io.StringIO(txt)):
        chave_data = "observation_date" if "observation_date" in linha else "DATE"
        try:
            pontos[datetime.date.fromisoformat(linha[chave_data])] = float(linha[codigo])
        except (ValueError, KeyError):
            continue
    if not pontos:
        raise ValueError("série vazia")
    return pontos


def baixar_ipea(codigo):
    """Valores de uma série do Ipeadata. Em séries regionais, fica só com o total do Brasil."""
    dados = json.loads(_get(f"{IPEA}/ValoresSerie(SERCODIGO='{codigo}')"))["value"]
    pontos = {}
    for d in dados:
        if d.get("NIVNOME") not in (None, "", "Brasil") or d.get("VALVALOR") is None:
            continue
        pontos[datetime.date.fromisoformat(d["VALDATA"][:10])] = float(d["VALVALOR"])
    if not pontos:
        raise ValueError("série vazia")
    return pontos


def ipea_descobrir(termo):
    """Acha no catálogo do Ipeadata a série ativa e anual mais recente cujo nome contém o termo
    (usado para o Gini, que tem várias versões ao longo das pesquisas do IBGE)."""
    # baixa o catálogo inteiro e filtra aqui: não depende da sintaxe de filtro da API
    catalogo = json.loads(_get(f"{IPEA}/Metadados", timeout=180))["value"]
    cands = [m for m in catalogo if termo.lower() in (m.get("SERNOME") or "").lower()
             and (m.get("PERNOME") or "").lower().startswith("anual") and m.get("SERSTATUS") == "A"]
    print(f"     {termo}: {len(cands)} séries candidatas no Ipeadata")
    for m in sorted(cands, key=lambda m: (m.get("SERMAXDATA") or "", -len(m.get("SERNOME") or "")), reverse=True):
        try:
            pontos = baixar_ipea(m["SERCODIGO"])
        except Exception:  # noqa: BLE001 - tenta a próxima candidata
            continue
        if len(pontos) >= 10:
            print(f"     {termo}: usando {m['SERCODIGO']} ({m['SERNOME']}, {m.get('FNTSIGLA')})")
            return m["SERCODIGO"], pontos
    raise ValueError(f"nenhuma série anual ativa com '{termo}' no Ipeadata")


def para_mensal(pontos, transf):
    """Converte pontos (data → valor) em lista ordenada [(mês, valor)]."""
    por_mes = {}
    for d, v in sorted(pontos.items()):
        por_mes.setdefault(d.replace(day=1), []).append(v)
    if transf == "anual":  # séries anuais: um ponto por ano, histórico completo
        por_ano = {}
        for d, v in sorted(pontos.items()):
            por_ano[d.year] = v
        return [(datetime.date(a, 1, 1), v) for a, v in sorted(por_ano.items())]
    if transf == "media":
        serie = [(m, float(np.mean(v))) for m, v in sorted(por_mes.items())]
    else:
        serie = [(m, v[-1]) for m, v in sorted(por_mes.items())]
    if transf == "yoy":
        idx = dict(serie)
        serie = [(m, (v / idx[m.replace(year=m.year - 1)] - 1) * 100)
                 for m, v in serie if m.replace(year=m.year - 1) in idx]
    return [(m, v) for m, v in serie if m >= INICIO]


# ======================================================================= análise

def sazonalidade(meses, x):
    """Efeito médio de cada mês (desvio em relação à média) e teste F das dummies de mês."""
    x = np.asarray(x, float)
    meses = np.asarray(meses)
    media = x.mean()
    efeito = [float(x[meses == m].mean() - media) if np.any(meses == m) else 0.0 for m in range(1, 13)]
    grupos = [x[meses == m] for m in range(1, 13) if np.sum(meses == m) >= 2]
    p = float(stats.f_oneway(*grupos).pvalue) if len(grupos) == 12 else 1.0
    return efeito, p


def transformar(nivel, modelar):
    nivel = np.asarray(nivel, float)
    if modelar == "dif":
        return np.diff(nivel)
    if modelar == "logdif":
        return np.diff(np.log(nivel)) * 100
    return nivel


def integrar(ultimo, sims, modelar):
    """Volta das variações previstas para o nível da série."""
    if modelar == "dif":
        return ultimo + np.cumsum(sims, axis=-1)
    if modelar == "logdif":
        return ultimo * np.exp(np.cumsum(sims, axis=-1) / 100)
    return sims


def prever_serie(datas, valores, modelar, rng):
    x = transformar(valores, modelar)
    datas_x = datas[1:] if modelar != "nivel" else datas
    x, datas_x = x[-M.JANELA:], datas_x[-M.JANELA:]
    meses = np.array([d.month for d in datas_x])
    efeito, p_saz = sazonalidade(meses, x)
    mod = M.sarima_escolher(x)
    sims = integrar(valores[-1], M.sarima_simular(mod, x, n_sim=1000, rng=rng), modelar)
    ponto = integrar(valores[-1], M.sarima_prever(mod, x), modelar)
    q = np.percentile(sims, [10, 90], axis=0)
    ult = datas[-1]
    prev = [[f"{ult.year + (ult.month + j) // 12}-{(ult.month + j) % 12 + 1:02d}",
             round(float(ponto[j]), 4), round(float(q[0][j]), 4), round(float(q[1][j]), 4)]
            for j in range(M.HORIZONTE)]
    return {
        "modelo": M.sarima_nome(mod["ordem"]),
        "modelado_como": {"nivel": "a própria série", "dif": "variação mês a mês",
                          "logdif": "variação % mês a mês"}[modelar],
        "sazonal_efeito": [round(e, 4) for e in efeito], "sazonal_p": round(p_saz, 4),
        "previsao": prev,
    }


def processar(cfg, rng):
    codigo = cfg["codigo"]
    if cfg["origem"] == "sgs":
        pontos = baixar_sgs(codigo)
    elif cfg["origem"] == "fred":
        pontos = baixar_fred(codigo)
    elif codigo.startswith("auto:"):
        codigo, pontos = ipea_descobrir(codigo[5:])
    else:
        pontos = baixar_ipea(codigo)
    serie = para_mensal(pontos, cfg["transf"])
    anual = cfg.get("freq") == "anual"
    if len(serie) < (10 if anual else 60):
        raise ValueError(f"só {len(serie)} pontos")
    datas = [m for m, _ in serie]
    valores = np.array([v for _, v in serie])
    saida = {k: cfg[k] for k in ("nome", "tema", "unidade", "descricao")}
    saida["fonte"] = FONTES[cfg["origem"]].format(c=codigo)
    saida["freq"] = "anual" if anual else "mensal"
    saida["dados"] = [[f"{d:%Y}" if anual else f"{d:%Y-%m}", round(float(v), 4)] for d, v in serie]
    if cfg["prever"]:
        saida["analise"] = prever_serie(datas, valores, cfg["modelar"], rng)
    return saida


def main(saida="data/series.json"):
    rng = np.random.default_rng(M.SEMENTE)
    anterior = {}
    if os.path.exists(saida):
        try:
            anterior = json.load(open(saida, encoding="utf-8")).get("series", {})
        except Exception:  # noqa: BLE001
            anterior = {}
    series, falhas = {}, {}
    for cfg in CATALOGO:
        try:
            series[cfg["id"]] = processar(cfg, rng)
            s = series[cfg["id"]]
            print(f"OK   {cfg['id']:<20} {len(s['dados']):>4} meses  último {s['dados'][-1]}")
        except Exception as e:  # noqa: BLE001 - uma série ruim não derruba as outras
            falhas[cfg["id"]] = f"{type(e).__name__}: {e}"[:200]
            print(f"ERRO {cfg['id']:<20} {type(e).__name__}: {e}")
            if cfg["id"] in anterior:
                series[cfg["id"]] = anterior[cfg["id"]]
            continue
        # série que parou de ser atualizada há mais de 8 meses não entra
        chave = series[cfg["id"]]["dados"][-1][0]
        ult = datetime.date.fromisoformat(chave + ("-01-01" if len(chave) == 4 else "-01"))
        if (datetime.date.today() - ult).days > (1100 if len(chave) == 4 else 250):
            falhas[cfg["id"]] = f"desatualizada: último dado {ult:%Y-%m}"
            del series[cfg["id"]]
    temas = list(dict.fromkeys(c["tema"] for c in CATALOGO))
    out = {"atualizado": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes"),
           "temas": temas, "ordem": [c["id"] for c in CATALOGO if c["id"] in series],
           "series": series, "falhas": falhas}
    with open(saida, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"\n{len(series)} séries salvas, {len(falhas)} falhas: {list(falhas)}")


if __name__ == "__main__":
    main()
