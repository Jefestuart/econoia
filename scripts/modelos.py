"""Modelos econométricos da EconoIA: previsão de inflação com avaliação honesta.

Para cada série (IPCA e IGP-M, variação mensal em %):
  1. Baixa o histórico completo no Banco Central (SGS), desde 2003.
  2. Estima um modelo autorregressivo com sazonalidade mensal, AR(p) + dummies de mês,
     por mínimos quadrados. A ordem p é escolhida pelo critério de Akaike (AIC).
  3. Prevê os próximos 12 meses. Os intervalos de 80% e 95% vêm de simulação por
     bootstrap dos resíduos (não supõe que os erros sejam normais).
  4. Faz um backtest de origem móvel: volta no tempo, reestima o modelo só com os
     dados disponíveis naquela data e compara a previsão com o que de fato aconteceu.
     O modelo é comparado com previsões ingênuas: se não ganhar delas, o site mostra isso.

Tudo é feito só com numpy, sem bibliotecas de econometria, para ficar transparente.
Saída: data/modelos.json, lido pelo site.
"""
import datetime
import json
import os
import urllib.request

import numpy as np

SERIES = [
    {"id": "ipca", "nome": "IPCA", "sgs": 433, "fonte": "IBGE, via SGS/Banco Central (série 433)"},
    {"id": "igpm", "nome": "IGP-M", "sgs": 189, "fonte": "FGV IBRE, via SGS/Banco Central (série 189)"},
]
INICIO = "01/01/2003"   # depois da crise de 2002, com o regime de metas de inflação consolidado
HORIZONTE = 12
P_MAX = 12
N_ORIGENS = 48          # backtest: 4 anos de previsões fora da amostra
N_SIM = 2000
SEMENTE = 2026


# ---------------------------------------------------------------- modelo AR(p) sazonal

def matriz(y, meses, p):
    """Monta X e alvo para y_t = c + Σ φ_i y_{t-i} + Σ d_m·1[mês=m] + e_t (m = 2..12)."""
    n = len(y)
    linhas, alvo = [], []
    for t in range(p, n):
        dummies = [1.0 if meses[t] == m else 0.0 for m in range(2, 13)]
        linhas.append([1.0] + [y[t - i] for i in range(1, p + 1)] + dummies)
        alvo.append(y[t])
    return np.array(linhas), np.array(alvo)


def ajustar(y, meses, p, inicio=None):
    """Estima por MQO. `inicio` fixa a primeira observação usada (para comparar AIC entre ordens)."""
    y = np.asarray(y, float)
    corte = 0 if inicio is None else inicio - p
    X, alvo = matriz(y[corte:], meses[corte:], p)
    beta, *_ = np.linalg.lstsq(X, alvo, rcond=None)
    resid = alvo - X @ beta
    n, k = X.shape
    sigma2 = float(resid @ resid / n)
    aic = n * np.log(sigma2) + 2 * k
    return {"p": p, "beta": beta, "resid": resid, "aic": float(aic), "n": n}


def escolher_ordem(y, meses, p_max=P_MAX):
    """Escolhe p de 1 a p_max pelo menor AIC, todos estimados na mesma amostra."""
    p_max = min(p_max, len(y) // 4)
    candidatos = [ajustar(y, meses, p, inicio=p_max) for p in range(1, p_max + 1)]
    melhor = min(candidatos, key=lambda m: m["aic"])
    return ajustar(y, meses, melhor["p"])  # reestima com a amostra toda


def _passo(beta, p, historico, mes):
    dummies = [1.0 if mes == m else 0.0 for m in range(2, 13)]
    x = np.array([1.0] + [historico[-i] for i in range(1, p + 1)] + dummies)
    return float(x @ beta)


def proximos_meses(ultimo_mes, h):
    return [((ultimo_mes + i - 1) % 12) + 1 for i in range(1, h + 1)]


def prever(modelo, y, ultimo_mes, h=HORIZONTE):
    """Previsão pontual recursiva para h meses."""
    hist = list(y)
    out = []
    for mes in proximos_meses(ultimo_mes, h):
        v = _passo(modelo["beta"], modelo["p"], hist, mes)
        out.append(v)
        hist.append(v)
    return np.array(out)


def simular(modelo, y, ultimo_mes, h=HORIZONTE, n_sim=N_SIM, rng=None):
    """Caminhos futuros com resíduos sorteados do próprio modelo (bootstrap)."""
    rng = rng or np.random.default_rng(SEMENTE)
    beta, p, resid = modelo["beta"], modelo["p"], modelo["resid"]
    meses = proximos_meses(ultimo_mes, h)
    caminhos = np.empty((n_sim, h))
    base = list(y[-p:])
    choques = rng.choice(resid, size=(n_sim, h), replace=True)
    for s in range(n_sim):
        hist = base.copy()
        for j, mes in enumerate(meses):
            v = _passo(beta, p, hist, mes) + choques[s, j]
            caminhos[s, j] = v
            hist.append(v)
    return caminhos


def acumulado(mensal_pct):
    """Acumula variações mensais em %: Π(1 + x/100) − 1, em %."""
    m = np.asarray(mensal_pct, float) / 100.0
    return (np.prod(1.0 + m, axis=-1) - 1.0) * 100.0


# ---------------------------------------------------------------- backtest

def rmse(erros):
    e = np.asarray(erros, float)
    return float(np.sqrt(np.mean(e ** 2)))


def backtest(y, meses, n_origens=N_ORIGENS, h=HORIZONTE, n_sim=500, rng=None):
    """Origem móvel: em cada data t, usa só y[:t], prevê t..t+h-1 e compara com o realizado.

    Concorrentes ingênuos:
      - repete o último mês;
      - sazonal: repete o mesmo mês do ano anterior;
      - para o acumulado em 12 meses: supõe que os próximos 12 meses repetem os últimos 12.
    """
    rng = rng or np.random.default_rng(SEMENTE)
    y = np.asarray(y, float)
    n = len(y)
    origens = range(n - h - n_origens + 1, n - h + 1)
    horizontes = [1, 3, 6, 12]
    err = {k: {hz: [] for hz in horizontes} for k in ("modelo", "ingenuo", "sazonal")}
    err_acum = {"modelo": [], "ingenuo": []}
    dentro80_h1 = []
    dentro80_acum = []
    for t in origens:
        mod = escolher_ordem(y[:t], meses[:t])
        prev = prever(mod, y[:t], meses[t - 1], h)
        real = y[t:t + h]
        for hz in horizontes:
            err["modelo"][hz].append(prev[hz - 1] - real[hz - 1])
            err["ingenuo"][hz].append(y[t - 1] - real[hz - 1])
            err["sazonal"][hz].append(y[t + hz - 1 - 12] - real[hz - 1])
        acum_real = acumulado(real)
        err_acum["modelo"].append(acumulado(prev) - acum_real)
        err_acum["ingenuo"].append(acumulado(y[t - 12:t]) - acum_real)
        sims = simular(mod, y[:t], meses[t - 1], h, n_sim, rng)
        lo, hi = np.percentile(sims[:, 0], [10, 90])
        dentro80_h1.append(lo <= real[0] <= hi)
        lo, hi = np.percentile(acumulado(sims), [10, 90])
        dentro80_acum.append(lo <= acum_real <= hi)

    por_horizonte = {}
    for hz in horizontes:
        r = {k: rmse(err[k][hz]) for k in err}
        melhor_ingenuo = min(r["ingenuo"], r["sazonal"])
        r["ganho_pct"] = round((1 - r["modelo"] / melhor_ingenuo) * 100, 1)
        por_horizonte[str(hz)] = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()}
    rm, ri = rmse(err_acum["modelo"]), rmse(err_acum["ingenuo"])
    return {
        "origens": len(origens),
        "periodo": None,  # preenchido por quem chama, com os rótulos de data
        "rmse_mensal": por_horizonte,
        "acumulado_12m": {"modelo": round(rm, 2), "ingenuo": round(ri, 2), "ganho_pct": round((1 - rm / ri) * 100, 1)},
        "cobertura_80": {"mes_seguinte": round(float(np.mean(dentro80_h1)) * 100, 1),
                         "acumulado_12m": round(float(np.mean(dentro80_acum)) * 100, 1)},
    }


# ---------------------------------------------------------------- dados e saída

def baixar_sgs(codigo, inicio=INICIO):
    url = (f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
           f"?formato=json&dataInicial={inicio}")
    req = urllib.request.Request(url, headers={"User-Agent": "EconoIA/1.0 (+https://econoia.com.br)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        dados = json.loads(r.read().decode("utf-8"))
    datas = [datetime.datetime.strptime(d["data"], "%d/%m/%Y").date() for d in dados]
    valores = np.array([float(d["valor"]) for d in dados])
    return datas, valores


def focus_ipca_12m():
    """Mediana do mercado (Focus/BCB) para o IPCA dos próximos 12 meses, para comparação."""
    url = ("https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/"
           "ExpectativasMercadoInflacao12Meses?$top=1&$format=json&$select=Data,Mediana"
           "&$filter=Indicador%20eq%20'IPCA'%20and%20Suavizada%20eq%20'S'%20and%20baseCalculo%20eq%200"
           "&$orderby=Data%20desc")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "EconoIA/1.0"})
        with urllib.request.urlopen(req, timeout=40) as r:
            v = json.loads(r.read().decode("utf-8"))["value"][0]
        return {"mediana": round(float(v["Mediana"]), 2), "data": v["Data"]}
    except Exception as e:  # noqa: BLE001 - comparação opcional
        print(f"Focus indisponível: {e}")
        return None


MESES_PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def rotulo(ano, mes):
    return f"{MESES_PT[mes - 1]}/{str(ano)[2:]}"


def rodar_serie(cfg, datas, y, rng):
    meses = np.array([d.month for d in datas])
    mod = escolher_ordem(y, meses)
    ultimo = datas[-1]
    pontual = prever(mod, y, ultimo.month)
    sims = simular(mod, y, ultimo.month, rng=rng)
    q = np.percentile(sims, [2.5, 10, 90, 97.5], axis=0)
    futuros = []
    a, m = ultimo.year, ultimo.month
    for j in range(HORIZONTE):
        m += 1
        if m > 12:
            a, m = a + 1, 1
        futuros.append([rotulo(a, m), round(pontual[j], 2), round(q[1][j], 2), round(q[2][j], 2),
                        round(q[0][j], 2), round(q[3][j], 2)])
    acum_sims = acumulado(sims)
    qa = np.percentile(acum_sims, [2.5, 10, 50, 90, 97.5])

    bt = backtest(y, meses, rng=rng)
    o0 = datas[len(y) - HORIZONTE - N_ORIGENS + 1]
    o1 = datas[len(y) - HORIZONTE]
    bt["periodo"] = f"{rotulo(o0.year, o0.month)} a {rotulo(o1.year, o1.month)}"

    historico = [[rotulo(d.year, d.month), round(float(v), 2)] for d, v in zip(datas[-36:], y[-36:])]
    return {
        "id": cfg["id"], "nome": cfg["nome"], "fonte": cfg["fonte"], "unidade": "% ao mês",
        "modelo": f"AR({mod['p']}) com sazonalidade mensal",
        "ordem_p": mod["p"], "observacoes": int(len(y)),
        "inicio_amostra": rotulo(datas[0].year, datas[0].month),
        "ultimo_dado": rotulo(ultimo.year, ultimo.month),
        "historico": historico,
        "previsao": futuros,  # [mês, ponto, lo80, hi80, lo95, hi95]
        "acumulado_12m": {
            "ultimos_12": round(float(acumulado(y[-12:])), 2),
            "previsto": round(float(qa[2]), 2),
            "lo80": round(float(qa[1]), 2), "hi80": round(float(qa[3]), 2),
            "lo95": round(float(qa[0]), 2), "hi95": round(float(qa[4]), 2),
        },
        "backtest": bt,
    }


def main(saida="data/modelos.json"):
    rng = np.random.default_rng(SEMENTE)
    resultado = {"atualizado": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes"),
                 "metodo": __doc__.strip(), "series": []}
    anterior = {}
    if os.path.exists(saida):
        try:
            anterior = {s["id"]: s for s in json.load(open(saida, encoding="utf-8")).get("series", [])}
        except Exception:  # noqa: BLE001
            anterior = {}
    for cfg in SERIES:
        try:
            datas, y = baixar_sgs(cfg["sgs"])
            resultado["series"].append(rodar_serie(cfg, datas, y, rng))
            print(f"OK   {cfg['nome']}: {len(y)} meses")
        except Exception as e:  # noqa: BLE001 - mantém a última versão boa
            print(f"ERRO {cfg['nome']}: {e} (mantida a versão anterior)")
            if cfg["id"] in anterior:
                resultado["series"].append(anterior[cfg["id"]])
    foc = focus_ipca_12m()
    if foc:
        resultado["focus_ipca_12m"] = foc
    if not resultado["series"]:
        raise SystemExit("Nenhuma série calculada.")
    with open(saida, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
