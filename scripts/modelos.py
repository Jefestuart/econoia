"""Modelos econométricos da EconoIA: SARIMA e VAR, com avaliação honesta.

Séries mensais do Banco Central (SGS):
  IPCA (433) e IGP-M (189), em % ao mês;
  dólar PTAX de venda, média do mês (3698), usado como variação % mensal;
  Selic efetiva do mês, anualizada (4189), usada como variação em p.p.

SARIMA (uma série por vez)
  (1 - φ(B))(1 - Φ(B¹²))(y_t - μ) = (1 + θ(B))(1 + Θ(B¹²)) e_t
  Estimado por soma condicional de quadrados (CSS). As ordens (p, q, P, Q) são
  escolhidas pelo critério de Akaike (AIC).

VAR (as quatro séries juntas)
  x_t = c + Σ A_i x_{t-i} + dummies de mês + u_t, estimado por MQO equação a equação,
  com a ordem p escolhida pelo AIC multivariado. Daí saem:
  - previsões conjuntas;
  - funções impulso-resposta (decomposição de Cholesky na ordem dólar → IGP-M → IPCA → Selic),
    com faixa de 90% por bootstrap;
  - testes de causalidade de Granger (teste F).

Para os dois modelos:
  - intervalos de previsão de 80% e 95% por simulação com resíduos sorteados (bootstrap);
  - backtest de origem móvel: o modelo é reestimado só com os dados de cada data passada
    e comparado com o realizado e com previsões ingênuas.

Saída: data/modelos.json, lido pelo site.
"""
import datetime
import json
import os
import urllib.request

import numpy as np
from scipy import optimize, signal, stats

INICIO = "01/01/2003"
JANELA = 180            # estima com os últimos 15 anos (regime mais parecido com o atual)
HORIZONTE = 12
N_ORIGENS = 48          # backtest: 4 anos de previsões fora da amostra
N_SIM = 2000
SEMENTE = 2026
H_IRF = 24

SERIES = {
    "ipca": {"nome": "IPCA", "sgs": 433, "fonte": "IBGE, via SGS/Banco Central (série 433)"},
    "igpm": {"nome": "IGP-M", "sgs": 189, "fonte": "FGV IBRE, via SGS/Banco Central (série 189)"},
    "dolar": {"nome": "Dólar", "sgs": 3698, "fonte": "PTAX venda, média mensal (SGS 3698)"},
    "selic": {"nome": "Selic", "sgs": 4189, "fonte": "Selic efetiva mensal anualizada (SGS 4189)"},
}
# Ordem de Cholesky: o que vem antes pode afetar o que vem depois no mesmo mês, não o contrário.
# O Copom (Selic) reage por último; o câmbio é o mais "rápido".
VAR_VARS = ["dolar", "igpm", "ipca", "selic"]
VAR_ROTULOS = {"dolar": "Dólar (% no mês)", "igpm": "IGP-M (% no mês)", "ipca": "IPCA (% no mês)", "selic": "Selic (variação em p.p.)"}
CHOQUES = {"dolar": ("Alta de 10% no dólar", 10.0), "selic": ("Alta de 1 p.p. na Selic", 1.0),
           "ipca": ("IPCA 1 p.p. acima no mês", 1.0), "igpm": ("IGP-M 1 p.p. acima no mês", 1.0)}


def acumulado(mensal_pct):
    """Acumula variações mensais em %: Π(1 + x/100) − 1, em %."""
    m = np.asarray(mensal_pct, float) / 100.0
    return (np.prod(1.0 + m, axis=-1) - 1.0) * 100.0


def rmse(e):
    e = np.asarray(e, float)
    return float(np.sqrt(np.mean(e ** 2)))


def dummies_mes(meses):
    """Matriz n×11 com dummies de fevereiro a dezembro."""
    meses = np.asarray(meses)
    return np.column_stack([(meses == m).astype(float) for m in range(2, 13)])


def proximos_meses(ultimo_mes, h):
    return np.array([((ultimo_mes + i - 1) % 12) + 1 for i in range(1, h + 1)])


# ======================================================================= SARIMA

def _polinomios(phi, Phi, theta, Theta, s=12):
    """Polinômios AR e MA completos (coeficientes de B^0, B^1, ...) do modelo multiplicativo."""
    ar = np.r_[1.0, -np.asarray(phi, float)]
    ar_s = np.zeros(s * len(Phi) + 1)
    ar_s[0] = 1.0
    for i, c in enumerate(Phi, 1):
        ar_s[s * i] = -c
    ma = np.r_[1.0, np.asarray(theta, float)]
    ma_s = np.zeros(s * len(Theta) + 1)
    ma_s[0] = 1.0
    for i, c in enumerate(Theta, 1):
        ma_s[s * i] = c
    return np.convolve(ar, ar_s), np.convolve(ma, ma_s)


def _estavel(poli):
    """Raízes fora do círculo unitário (estacionário / invertível)."""
    if len(poli) <= 1:
        return True
    raizes = np.roots(poli[::-1])
    return bool(np.all(np.abs(raizes) > 1.001))


def _separa(params, ordem):
    p, q, P, Q = ordem
    mu = params[0]
    i = 1
    phi = params[i:i + p]; i += p
    theta = params[i:i + q]; i += q
    Phi = params[i:i + P]; i += P
    Theta = params[i:i + Q]
    return mu, phi, theta, Phi, Theta


def _residuos(params, y, ordem):
    mu, phi, theta, Phi, Theta = _separa(params, ordem)
    ar, ma = _polinomios(phi, Phi, theta, Theta)
    return signal.lfilter(ar, ma, y - mu), ar, ma


def sarima_ajustar(y, ordem):
    """Estima SARIMA(p,0,q)(P,0,Q)12 com constante por CSS. Devolve dict com parâmetros e AIC."""
    y = np.asarray(y, float)
    p, q, P, Q = ordem
    m = max(p + 12 * P, q + 12 * Q)  # observações iniciais descartadas
    k = 1 + p + q + P + Q

    def objetivo(params):
        e, ar, ma = _residuos(params, y, ordem)
        if not (_estavel(ar) and _estavel(ma)):
            return 1e10
        return float(np.sum(e[m:] ** 2))

    x0 = np.r_[y.mean(), np.full(k - 1, 0.1)]
    melhor = None
    for metodo in ("L-BFGS-B", "Nelder-Mead"):
        r = optimize.minimize(objetivo, x0, method=metodo, options={"maxiter": 4000})
        if melhor is None or r.fun < melhor.fun:
            melhor = r
    e, ar, ma = _residuos(melhor.x, y, ordem)
    resid = e[m:]
    n = len(resid)
    sigma2 = float(resid @ resid / n)
    return {"ordem": ordem, "params": melhor.x, "ar": ar, "ma": ma, "resid": resid,
            "e_todos": e, "aic": n * np.log(sigma2) + 2 * k, "n": n, "sigma2": sigma2}


ORDENS_SARIMA = [(p, q, P, Q) for p in (0, 1, 2) for q in (0, 1) for P in (0, 1) for Q in (0, 1) if p + q + P + Q > 0]


def sarima_escolher(y, ordens=ORDENS_SARIMA):
    """Menor AIC, todos comparados na mesma amostra (descartando as 25 primeiras observações)."""
    y = np.asarray(y, float)
    melhor = None
    for o in ordens:
        try:
            m = sarima_ajustar(y, o)
        except Exception:  # noqa: BLE001
            continue
        resid = m["e_todos"][25:]
        k = 1 + sum(o)
        aic = len(resid) * np.log(resid @ resid / len(resid)) + 2 * k
        if melhor is None or aic < melhor[0]:
            melhor = (aic, m)
    return melhor[1]


def sarima_nome(ordem):
    p, q, P, Q = ordem
    return f"SARIMA({p},0,{q})({P},0,{Q})12"


def sarima_simular(mod, y, h=HORIZONTE, n_sim=N_SIM, rng=None, choques=True):
    """Caminhos futuros. Com choques=False devolve a previsão pontual (1 caminho)."""
    rng = rng or np.random.default_rng(SEMENTE)
    mu = mod["params"][0]
    ar, ma = mod["ar"], mod["ma"]
    w = np.asarray(y, float) - mu
    e = mod["e_todos"]
    na, nm = len(ar) - 1, len(ma) - 1
    n_cam = n_sim if choques else 1
    fut_e = rng.choice(mod["resid"], size=(n_cam, h)) if choques else np.zeros((1, h))
    w_hist = np.tile(w[-na:] if na else np.zeros(0), (n_cam, 1))
    e_hist = np.tile(e[-nm:] if nm else np.zeros(0), (n_cam, 1))
    out = np.empty((n_cam, h))
    for j in range(h):
        val = fut_e[:, j].copy()
        for i in range(1, na + 1):
            val -= ar[i] * w_hist[:, -i]
        for i in range(1, nm + 1):
            val += ma[i] * e_hist[:, -i]
        out[:, j] = val + mu
        w_hist = np.column_stack([w_hist, val])
        e_hist = np.column_stack([e_hist, fut_e[:, j]])
    return out


def sarima_prever(mod, y, h=HORIZONTE):
    return sarima_simular(mod, y, h, choques=False)[0]


# ======================================================================= VAR

def var_matrizes(X, meses, p):
    """Regressores [1, x_{t-1}, ..., x_{t-p}, dummies] e alvos x_t, para t = p..n-1."""
    X = np.asarray(X, float)
    n, k = X.shape
    lags = np.column_stack([X[p - i:n - i] for i in range(1, p + 1)])
    Z = np.column_stack([np.ones(n - p), lags, dummies_mes(meses[p:])])
    return Z, X[p:]


def var_ajustar(X, meses, p, inicio=None):
    X = np.asarray(X, float)
    corte = 0 if inicio is None else inicio - p
    Z, Y = var_matrizes(X[corte:], np.asarray(meses)[corte:], p)
    B, *_ = np.linalg.lstsq(Z, Y, rcond=None)
    U = Y - Z @ B
    n, k = Y.shape
    sigma = U.T @ U / n
    aic = np.log(np.linalg.det(sigma)) + 2 * B.size / n
    return {"p": p, "B": B, "U": U, "sigma": sigma, "aic": float(aic), "n": n, "k": k, "Z": Z, "Y": Y}


def var_escolher(X, meses, p_max=4):
    cand = [var_ajustar(X, meses, p, inicio=p_max) for p in range(1, p_max + 1)]
    melhor = min(cand, key=lambda m: m["aic"])
    return var_ajustar(X, meses, melhor["p"])


def var_A(mod):
    """Matrizes A_1..A_p (k×k) e constante, a partir de B."""
    k, p = mod["k"], mod["p"]
    B = mod["B"]
    A = [B[1 + (i * k):1 + (i + 1) * k].T for i in range(p)]
    return B[0], A, B[1 + p * k:]  # constante, lags, dummies (11×k)


def var_simular(mod, X, ultimo_mes, h=HORIZONTE, n_sim=N_SIM, rng=None, choques=True):
    rng = rng or np.random.default_rng(SEMENTE)
    c, A, D = var_A(mod)
    k, p = mod["k"], mod["p"]
    meses = proximos_meses(ultimo_mes, h)
    n_cam = n_sim if choques else 1
    hist = np.tile(np.asarray(X, float)[-p:][None, :, :], (n_cam, 1, 1))
    U = mod["U"]
    out = np.empty((n_cam, h, k))
    for j in range(h):
        val = np.tile(c, (n_cam, 1)).astype(float)
        if meses[j] >= 2:
            val += D[meses[j] - 2]
        for i in range(p):
            val += hist[:, -1 - i, :] @ A[i].T
        if choques:
            val += U[rng.integers(0, len(U), n_cam)]
        out[:, j, :] = val
        hist = np.concatenate([hist, val[:, None, :]], axis=1)
    return out


def var_prever(mod, X, ultimo_mes, h=HORIZONTE):
    return var_simular(mod, X, ultimo_mes, h, choques=False)[0]


def var_irf(mod, h=H_IRF):
    """Respostas ortogonalizadas (Cholesky): irf[t, i, j] = resposta da variável i, t meses
    após um choque de 1 desvio-padrão na variável j."""
    _, A, _ = var_A(mod)
    k, p = mod["k"], mod["p"]
    P = np.linalg.cholesky(mod["sigma"])
    psi = [np.eye(k)]
    for t in range(1, h + 1):
        acc = np.zeros((k, k))
        for i in range(1, min(t, p) + 1):
            acc += A[i - 1] @ psi[t - i]
        psi.append(acc)
    return np.array([m @ P for m in psi])


def var_irf_bandas(mod, X, meses, h=H_IRF, n_boot=300, rng=None):
    """Faixa de 90% por bootstrap: gera séries artificiais com os resíduos sorteados,
    reestima o VAR (mesma ordem) e recalcula as respostas."""
    rng = rng or np.random.default_rng(SEMENTE)
    X = np.asarray(X, float)
    meses = np.asarray(meses)
    c, A, D = var_A(mod)
    p, U = mod["p"], mod["U"]
    n = len(X)
    amostras = []
    for _ in range(n_boot):
        Xb = X.copy()
        sort = U[rng.integers(0, len(U), n)]
        for t in range(p, n):
            v = c.copy()
            if meses[t] >= 2:
                v = v + D[meses[t] - 2]
            for i in range(p):
                v = v + A[i] @ Xb[t - 1 - i]
            Xb[t] = v + sort[t]
        try:
            amostras.append(var_irf(var_ajustar(Xb, meses, p), h))
        except np.linalg.LinAlgError:
            continue
    amostras = np.array(amostras)
    return np.percentile(amostras, 5, axis=0), np.percentile(amostras, 95, axis=0)


def var_granger(X, meses, p):
    """Teste F: os lags da variável `causa` melhoram a previsão de `efeito` além dos lags dela mesma?"""
    X = np.asarray(X, float)
    k = X.shape[1]
    Z, Y = var_matrizes(X, np.asarray(meses), p)
    n = len(Y)
    resultados = []
    for j in range(k):          # efeito
        bu, *_ = np.linalg.lstsq(Z, Y[:, j], rcond=None)
        rss_u = float(np.sum((Y[:, j] - Z @ bu) ** 2))
        for i in range(k):      # causa
            if i == j:
                continue
            fora = [1 + lag * k + i for lag in range(p)]
            Zr = np.delete(Z, fora, axis=1)
            br, *_ = np.linalg.lstsq(Zr, Y[:, j], rcond=None)
            rss_r = float(np.sum((Y[:, j] - Zr @ br) ** 2))
            gl2 = n - Z.shape[1]
            F = ((rss_r - rss_u) / p) / (rss_u / gl2)
            resultados.append({"causa": i, "efeito": j, "F": float(F), "p": float(stats.f.sf(F, p, gl2))})
    return resultados


# ======================================================================= backtest

def backtest(y_alvo, prever_em, n_origens=N_ORIGENS, h=HORIZONTE):
    """Origem móvel genérica.

    y_alvo: série mensal realizada (% ao mês).
    prever_em(t): devolve (previsao_pontual[h], simulacoes[n_sim, h]) usando só dados até t-1.
    Concorrentes: repetir o último mês; repetir o mesmo mês do ano anterior;
    no acumulado de 12 meses, supor que os próximos 12 repetem os últimos 12.
    """
    y = np.asarray(y_alvo, float)
    n = len(y)
    origens = list(range(n - h - n_origens + 1, n - h + 1))
    horizontes = [1, 3, 6, 12]
    err = {k: {hz: [] for hz in horizontes} for k in ("modelo", "ingenuo", "sazonal")}
    acum = {"modelo": [], "ingenuo": []}
    cob1, cob12 = [], []
    for t in origens:
        prev, sims = prever_em(t)
        real = y[t:t + h]
        for hz in horizontes:
            err["modelo"][hz].append(prev[hz - 1] - real[hz - 1])
            err["ingenuo"][hz].append(y[t - 1] - real[hz - 1])
            err["sazonal"][hz].append(y[t + hz - 1 - 12] - real[hz - 1])
        a_real = acumulado(real)
        acum["modelo"].append(acumulado(prev) - a_real)
        acum["ingenuo"].append(acumulado(y[t - 12:t]) - a_real)
        lo, hi = np.percentile(sims[:, 0], [10, 90])
        cob1.append(lo <= real[0] <= hi)
        lo, hi = np.percentile(acumulado(sims), [10, 90])
        cob12.append(lo <= a_real <= hi)
    por_h = {}
    for hz in horizontes:
        r = {k: rmse(err[k][hz]) for k in err}
        r["ganho_pct"] = (1 - r["modelo"] / min(r["ingenuo"], r["sazonal"])) * 100
        por_h[str(hz)] = {k: round(v, 3) for k, v in r.items()}
    rm, ri = rmse(acum["modelo"]), rmse(acum["ingenuo"])
    return {
        "origens": len(origens), "primeira_origem": origens[0], "ultima_origem": origens[-1],
        "rmse_mensal": por_h,
        "acumulado_12m": {"modelo": round(rm, 2), "ingenuo": round(ri, 2), "ganho_pct": round((1 - rm / ri) * 100, 1)},
        "cobertura_80": {"mes_seguinte": round(float(np.mean(cob1)) * 100, 1),
                         "acumulado_12m": round(float(np.mean(cob12)) * 100, 1)},
    }


# ======================================================================= dados

def baixar_sgs(codigo, inicio=INICIO):
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial={inicio}"
    req = urllib.request.Request(url, headers={"User-Agent": "EconoIA/1.0 (+https://econoia.com.br)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        dados = json.loads(r.read().decode("utf-8"))
    return {datetime.datetime.strptime(d["data"], "%d/%m/%Y").date().replace(day=1): float(d["valor"]) for d in dados}


def focus_12m(indicador):
    """Mediana do mercado (Focus/BCB) para os próximos 12 meses."""
    filtro = f"Indicador%20eq%20'{indicador}'%20and%20Suavizada%20eq%20'S'%20and%20baseCalculo%20eq%200"
    url = ("https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/"
           f"ExpectativasMercadoInflacao12Meses?$top=1&$format=json&$select=Data,Mediana&$filter={filtro}&$orderby=Data%20desc")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "EconoIA/1.0"})
        with urllib.request.urlopen(req, timeout=40) as r:
            v = json.loads(r.read().decode("utf-8"))["value"][0]
        return {"mediana": round(float(v["Mediana"]), 2), "data": v["Data"]}
    except Exception as e:  # noqa: BLE001 - comparação opcional
        print(f"Focus {indicador} indisponível: {e}")
        return None


def montar_painel(brutos):
    """Alinha as séries nos meses em que todas existem e transforma para o VAR:
    dólar em variação % mensal e Selic em variação em p.p."""
    datas = sorted(set.intersection(*[set(v) for v in brutos.values()]))
    d0 = datas[1:]  # perde um mês por causa das variações
    painel = {
        "ipca": np.array([brutos["ipca"][d] for d in d0]),
        "igpm": np.array([brutos["igpm"][d] for d in d0]),
        "dolar": np.array([(brutos["dolar"][d] / brutos["dolar"][a] - 1) * 100 for a, d in zip(datas[:-1], d0)]),
        "selic": np.array([brutos["selic"][d] - brutos["selic"][a] for a, d in zip(datas[:-1], d0)]),
    }
    return d0, painel


MESES_PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def rotulo(d):
    return f"{MESES_PT[d.month - 1]}/{str(d.year)[2:]}"


def rotulo_somado(d, n):
    m = d.month - 1 + n
    return f"{MESES_PT[m % 12]}/{str(d.year + m // 12)[2:]}"


# ======================================================================= execução

def resumo_previsao(prev, sims, ultima_data):
    q = np.percentile(sims, [2.5, 10, 90, 97.5], axis=0)
    linhas = [[rotulo_somado(ultima_data, j + 1), round(float(prev[j]), 2), round(float(q[1][j]), 2),
               round(float(q[2][j]), 2), round(float(q[0][j]), 2), round(float(q[3][j]), 2)] for j in range(len(prev))]
    qa = np.percentile(acumulado(sims), [2.5, 10, 90, 97.5])
    return linhas, {"previsto": round(float(acumulado(prev)), 2), "lo80": round(float(qa[1]), 2),
                    "hi80": round(float(qa[2]), 2), "lo95": round(float(qa[0]), 2), "hi95": round(float(qa[3]), 2)}


def rodar(datas, painel, rng, n_origens=N_ORIGENS, n_sim_bt=300, n_boot=300):
    meses = np.array([d.month for d in datas])
    X = np.column_stack([painel[v] for v in VAR_VARS])
    n = len(datas)
    ult = datas[-1]

    def janela(t):
        return max(0, t - JANELA)

    # ---------- VAR na amostra completa (janela final)
    j0 = janela(n)
    var_mod = var_escolher(X[j0:], meses[j0:])
    var_prev = var_prever(var_mod, X[j0:], meses[-1])
    var_sims = var_simular(var_mod, X[j0:], meses[-1], rng=rng)

    # backtest do VAR: uma reestimação por origem serve para IPCA e IGP-M
    cache_var = {}

    def var_em(t):
        if t not in cache_var:
            a = janela(t)
            m = var_escolher(X[a:t], meses[a:t])
            cache_var[t] = (var_prever(m, X[a:t], meses[t - 1]),
                            var_simular(m, X[a:t], meses[t - 1], n_sim=n_sim_bt, rng=rng))
        return cache_var[t]

    saida_series = {}
    for nome in ("ipca", "igpm"):
        y = painel[nome]
        idx = VAR_VARS.index(nome)

        # ---------- SARIMA
        sar = sarima_escolher(y[j0:])
        s_prev = sarima_prever(sar, y[j0:])
        s_sims = sarima_simular(sar, y[j0:], rng=rng)

        def sar_em(t, y=y):
            a = janela(t)
            m = sarima_escolher(y[a:t])
            return sarima_prever(m, y[a:t]), sarima_simular(m, y[a:t], n_sim=n_sim_bt, rng=rng)

        bt_sar = backtest(y, sar_em, n_origens)
        bt_var = backtest(y, lambda t, i=idx: (var_em(t)[0][:, i], var_em(t)[1][:, :, i]), n_origens)
        for bt in (bt_sar, bt_var):
            bt["periodo"] = f"{rotulo(datas[bt.pop('primeira_origem')])} a {rotulo(datas[bt.pop('ultima_origem')])}"

        s_lin, s_acum = resumo_previsao(s_prev, s_sims, ult)
        v_lin, v_acum = resumo_previsao(var_prev[:, idx], var_sims[:, :, idx], ult)
        modelos = {
            "sarima": {"nome": sarima_nome(sar["ordem"]), "previsao": s_lin, "acumulado_12m": s_acum, "backtest": bt_sar},
            "var": {"nome": f"VAR({var_mod['p']})", "previsao": v_lin, "acumulado_12m": v_acum, "backtest": bt_var},
        }
        melhor = min(modelos, key=lambda k: modelos[k]["backtest"]["acumulado_12m"]["modelo"])
        saida_series[nome] = {
            "nome": SERIES[nome]["nome"], "fonte": SERIES[nome]["fonte"], "unidade": "% ao mês",
            "ultimo_dado": rotulo(ult), "ultimos_12": round(float(acumulado(y[-12:])), 2),
            "historico": [[rotulo(d), round(float(v), 2)] for d, v in zip(datas[-36:], y[-36:])],
            "modelos": modelos, "melhor": melhor,
        }

    # ---------- impulso-resposta e Granger (VAR da janela final)
    irf = var_irf(var_mod)
    lo, hi = var_irf_bandas(var_mod, X[j0:], meses[j0:], n_boot=n_boot, rng=rng)
    sd = np.sqrt(np.diag(var_mod["sigma"]))
    respostas = {}
    for c_nome, (c_txt, tamanho) in CHOQUES.items():
        j = VAR_VARS.index(c_nome)
        escala = tamanho / irf[0, j, j]  # choque do tamanho anunciado no próprio mês
        for r_nome in VAR_VARS:
            if r_nome == c_nome:
                continue
            i = VAR_VARS.index(r_nome)
            cum = lambda a: np.cumsum(a[:, i, j]) * escala  # noqa: E731 - efeito acumulado
            respostas[f"{c_nome}->{r_nome}"] = {
                "choque": c_txt, "resposta": SERIES[r_nome]["nome"],
                "unidade": "p.p. acumulados" if r_nome != "dolar" else "% acumulado",
                "ponto": [round(float(v), 3) for v in cum(irf)],
                "lo90": [round(float(v), 3) for v in cum(lo)], "hi90": [round(float(v), 3) for v in cum(hi)],
            }
    granger = [{"causa": SERIES[VAR_VARS[g["causa"]]]["nome"], "efeito": SERIES[VAR_VARS[g["efeito"]]]["nome"],
                "F": round(g["F"], 2), "p": round(g["p"], 4)}
               for g in var_granger(X[j0:], meses[j0:], var_mod["p"])]
    var_info = {
        "nome": f"VAR({var_mod['p']})", "variaveis": [VAR_ROTULOS[v] for v in VAR_VARS],
        "ordem_cholesky": [SERIES[v]["nome"] for v in VAR_VARS],
        "amostra": f"{rotulo(datas[j0])} a {rotulo(ult)}", "observacoes": int(var_mod["n"]),
        "desvios_choque": {SERIES[v]["nome"]: round(float(s), 3) for v, s in zip(VAR_VARS, sd)},
        "irf": respostas, "granger": granger,
    }
    return saida_series, var_info


def main(saida="data/modelos.json"):
    rng = np.random.default_rng(SEMENTE)
    brutos = {k: baixar_sgs(cfg["sgs"]) for k, cfg in SERIES.items()}
    datas, painel = montar_painel(brutos)
    print(f"Painel: {len(datas)} meses ({rotulo(datas[0])} a {rotulo(datas[-1])})")
    series, var_info = rodar(datas, painel, rng)
    for nome, foc in (("ipca", "IPCA"), ("igpm", "IGP-M")):
        f = focus_12m(foc)
        if f:
            series[nome]["focus_12m"] = f
    resultado = {
        "atualizado": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes"),
        "janela_meses": JANELA, "series": series, "var": var_info,
    }
    with open(saida, "w", encoding="utf-8") as fh:
        json.dump(resultado, fh, ensure_ascii=False, indent=1)
    for nome, s in series.items():
        print(f"OK   {s['nome']}: melhor = {s['melhor']}, "
              + ", ".join(f"{k} {m['acumulado_12m']['previsto']}%" for k, m in s["modelos"].items()))


if __name__ == "__main__":
    main()
