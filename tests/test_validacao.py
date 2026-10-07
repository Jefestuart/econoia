"""Validação do motor econométrico contra o statsmodels (biblioteca de referência em Python).

Como o R não está no ambiente de testes, a conferência é feita com o statsmodels, que
implementa os mesmos modelos e é a referência de fato em Python. Estes testes só rodam se o
statsmodels estiver instalado (no GitHub Actions ele é instalado; veja .github/workflows/testes.yml).

O que se espera de cada parte:
- VAR (MQO), IRF, previsão e teste F de Granger: resultados IGUAIS aos do statsmodels
  (diferenças só de arredondamento numérico), porque são os mesmos cálculos.
- SARIMA: o statsmodels estima por máxima verossimilhança exata e o EconoIA por soma
  condicional de quadrados (CSS). São estimadores diferentes: esperam-se parâmetros e previsões
  PRÓXIMOS (não iguais), e que o estimador do EconoIA seja de fato o mínimo da sua própria função
  objetivo.
"""
import os
import sys
import unittest
import warnings

import numpy as np
from scipy import signal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import modelos as m  # noqa: E402

try:
    import statsmodels.api as sm
    from statsmodels.tsa.api import VAR
    from statsmodels.tsa.statespace.sarimax import SARIMAX
    TEM_SM = True
except ImportError:  # pragma: no cover
    TEM_SM = False


def sarima_simulado(n=600, mu=0.4, phi=0.6, theta=0.3, Phi=0.4, Theta=0.0, sd=0.2, semente=1):
    rng = np.random.default_rng(semente)
    ar, ma = m._polinomios([phi], [Phi], [theta], [Theta] if Theta else [])
    e = rng.normal(0, sd, n + 200)
    return mu + signal.lfilter(ma, ar, e)[200:]


def var_simulado(n=400, semente=2):
    A1 = np.array([[0.3, 0.0, 0.0], [0.4, 0.5, 0.0], [0.0, 0.2, 0.4]])
    A2 = np.array([[0.1, 0.0, 0.0], [0.0, 0.1, 0.0], [0.05, 0.0, 0.1]])
    SIG = np.array([[1.0, 0.3, 0.1], [0.3, 0.8, 0.2], [0.1, 0.2, 0.5]])
    rng = np.random.default_rng(semente)
    L = np.linalg.cholesky(SIG)
    X = np.zeros((n + 100, 3))
    for t in range(2, n + 100):
        X[t] = 0.1 + A1 @ X[t - 1] + A2 @ X[t - 2] + L @ rng.normal(size=3)
    return X[100:], np.array([(i % 12) + 1 for i in range(n)])


@unittest.skipUnless(TEM_SM, "statsmodels não instalado")
class ValidaVAR(unittest.TestCase):
    P = 2

    @classmethod
    def setUpClass(cls):
        cls.X, cls.meses = var_simulado()
        cls.mod = m.var_ajustar(cls.X, cls.meses, cls.P)
        D = m.dummies_mes(cls.meses)
        cls.res = VAR(cls.X, exog=D).fit(cls.P, trend="c")

    def test_coeficientes_iguais_ao_statsmodels(self):
        """Compara coeficiente a coeficiente, ligando as linhas pelos nomes (a ordem das linhas é diferente)."""
        k, p = self.mod["k"], self.mod["p"]
        B, ps = self.mod["B"], self.res.params
        self.assertEqual(B.shape, ps.shape)
        for linha, nome in enumerate(self.res.exog_names):
            if nome == "const":
                nossa = 0
            elif nome.startswith("exog"):
                nossa = 1 + p * k + int(nome[4:])           # dummies de fev. a dez., depois dos lags
            else:                                           # "L2.y3": defasagem 2 da variável 3
                lag, var = nome[1:].split(".y")
                nossa = 1 + (int(lag) - 1) * k + (int(var) - 1)
            np.testing.assert_allclose(B[nossa], ps[linha], atol=1e-8, err_msg=nome)

    def test_residuos_variancia_e_aic(self):
        np.testing.assert_allclose(self.mod["U"], self.res.resid, atol=1e-8)
        np.testing.assert_allclose(self.mod["sigma"], self.res.sigma_u_mle, atol=1e-10)
        self.assertAlmostEqual(self.mod["aic"], float(self.res.info_criteria["aic"]), places=8)

    def test_impulso_resposta_igual(self):
        """IRF ortogonalizada (Cholesky). O statsmodels usa a covariância corrigida por graus de liberdade
        (sigma_u = c · sigma_mle); nós usamos a de máxima verossimilhança. Como cholesky(c·S) = √c · cholesky(S),
        as respostas diferem exatamente pelo fator √c, e é isso que se confere."""
        h = 12
        c = self.res.sigma_u / self.res.sigma_u_mle
        np.testing.assert_allclose(c, c[0, 0], atol=1e-10)  # a razão é a mesma em toda a matriz
        nos = m.var_irf(self.mod, h=h)
        ref = self.res.irf(h).orth_irfs
        np.testing.assert_allclose(nos * np.sqrt(c[0, 0]), ref, atol=1e-8)

    def test_previsao_igual(self):
        h = 12
        ultimo = int(self.meses[-1])
        D_fut = m.dummies_mes(m.proximos_meses(ultimo, h))
        ref = self.res.forecast(self.X[-self.P:], steps=h, exog_future=D_fut)
        nos = m.var_prever(self.mod, self.X, ultimo, h=h)
        np.testing.assert_allclose(nos, ref, atol=1e-8)

    def test_granger_igual_ao_teste_f_do_mqo(self):
        """O teste de Granger do EconoIA é um teste F por equação; confere com OLS.f_test do statsmodels."""
        k, p = self.mod["k"], self.P
        Z, Y = m.var_matrizes(self.X, self.meses, p)
        for r in m.var_granger(self.X, self.meses, p):
            ols = sm.OLS(Y[:, r["efeito"]], Z).fit()
            restr = np.zeros((p, Z.shape[1]))
            for lag in range(p):
                restr[lag, 1 + lag * k + r["causa"]] = 1
            ref = ols.f_test(restr)
            self.assertAlmostEqual(r["F"], float(ref.fvalue), places=8)
            self.assertAlmostEqual(r["p"], float(ref.pvalue), places=10)


@unittest.skipUnless(TEM_SM, "statsmodels não instalado")
class ValidaSARIMA(unittest.TestCase):
    ORDENS = [(1, 1, 1, 0), (1, 0, 1, 0), (2, 1, 0, 1)]

    @classmethod
    def setUpClass(cls):
        cls.y = sarima_simulado()
        cls.ref = {}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for o in cls.ORDENS:
                p, q, P, Q = o
                r = SARIMAX(cls.y, order=(p, 0, q), seasonal_order=(P, 0, Q, 12), trend="c").fit(disp=False)
                cls.ref[o] = r

    @staticmethod
    def _media_sm(nomes, valores, ar_poli):
        """Converte a constante do statsmodels (forma intercepto) para a média μ usada aqui."""
        c = valores[nomes.index("intercept")]
        return c / float(np.sum(ar_poli))

    def test_parametros_proximos_do_statsmodels(self):
        for o in self.ORDENS:
            nos = m.sarima_ajustar(self.y, o)
            mu, phi, theta, Phi, Theta = m._separa(nos["params"], o)
            ref = self.ref[o]
            nomes = list(ref.param_names)
            v = dict(zip(nomes, ref.params))
            for i, c in enumerate(phi, 1):
                self.assertAlmostEqual(c, v[f"ar.L{i}"], delta=0.04, msg=f"{o} phi{i}")
            for i, c in enumerate(theta, 1):
                self.assertAlmostEqual(c, v[f"ma.L{i}"], delta=0.04, msg=f"{o} theta{i}")
            for i, c in enumerate(Phi, 1):
                self.assertAlmostEqual(c, v[f"ar.S.L{12 * i}"], delta=0.04, msg=f"{o} Phi{i}")
            for i, c in enumerate(Theta, 1):
                self.assertAlmostEqual(c, v[f"ma.S.L{12 * i}"], delta=0.04, msg=f"{o} Theta{i}")
            ar_sm, _ = m._polinomios([v.get(f"ar.L{i}", 0) for i in range(1, o[0] + 1)],
                                      [v.get(f"ar.S.L{12 * i}", 0) for i in range(1, o[2] + 1)],
                                      [v.get(f"ma.L{i}", 0) for i in range(1, o[1] + 1)],
                                      [v.get(f"ma.S.L{12 * i}", 0) for i in range(1, o[3] + 1)])
            self.assertAlmostEqual(mu, self._media_sm(nomes, ref.params, ar_sm), delta=0.05, msg=f"{o} média")
            self.assertAlmostEqual(np.sqrt(nos["sigma2"]), np.sqrt(v["sigma2"]), delta=0.01, msg=f"{o} sigma")

    def test_previsao_proxima_do_statsmodels(self):
        for o in self.ORDENS:
            nos = m.sarima_ajustar(self.y, o)
            prev = m.sarima_prever(nos, self.y, h=12)
            ref = self.ref[o].get_forecast(12).predicted_mean
            self.assertLess(float(np.max(np.abs(prev - ref))), 0.01, msg=str(o))  # observado: ~0,004

    def test_estimador_e_o_minimo_da_propria_funcao_objetivo(self):
        """A soma de quadrados dos resíduos no nosso ajuste não pode ser maior que nos parâmetros do statsmodels."""
        for o in self.ORDENS:
            nos = m.sarima_ajustar(self.y, o)
            p, q, P, Q = o
            ref = self.ref[o]
            v = dict(zip(ref.param_names, ref.params))
            ar_sm, _ = m._polinomios([v.get(f"ar.L{i}", 0) for i in range(1, p + 1)],
                                      [v.get(f"ar.S.L{12 * i}", 0) for i in range(1, P + 1)],
                                      [v.get(f"ma.L{i}", 0) for i in range(1, q + 1)],
                                      [v.get(f"ma.S.L{12 * i}", 0) for i in range(1, Q + 1)])
            x_sm = np.r_[self._media_sm(list(ref.param_names), ref.params, ar_sm),
                         [v.get(f"ar.L{i}", 0) for i in range(1, p + 1)],
                         [v.get(f"ma.L{i}", 0) for i in range(1, q + 1)],
                         [v.get(f"ar.S.L{12 * i}", 0) for i in range(1, P + 1)],
                         [v.get(f"ma.S.L{12 * i}", 0) for i in range(1, Q + 1)]]
            mm = max(p + 12 * P, q + 12 * Q)
            e_sm, _, _ = m._residuos(x_sm, self.y, o)
            sse_sm = float(np.sum(e_sm[mm:] ** 2))
            sse_nos = float(np.sum(nos["resid"] ** 2))
            self.assertLessEqual(sse_nos, sse_sm * (1 + 1e-6), msg=str(o))


@unittest.skipUnless(TEM_SM, "statsmodels não instalado")
class ValidaSARIMAComDadosReais(unittest.TestCase):
    """IPCA e IGP-M reais (Banco Central, congelados em tests/fixtures), com as ordens que o site escolhe.

    Em dados reais o IPCA tem sazonalidade quase raiz unitária (AR sazonal ≈ 0,95 com MA sazonal ≈ -0,9,
    que se compensam), e aí os dois estimadores diferem nos parâmetros individuais (até ~0,07 no AR).
    O que importa para o usuário é a previsão, e ela fica a poucos centésimos de ponto percentual
    (observado: IPCA 0,05 p.p., IGP-M 0,03 p.p.)."""

    CASOS = [("ipca", (1, 0, 1, 1)), ("igpm", (1, 0, 0, 1))]

    def test_previsao_de_12_meses_proxima_do_statsmodels(self):
        import json
        with open(os.path.join(os.path.dirname(__file__), "fixtures", "series_reais.json"), encoding="utf-8") as f:
            dados = json.load(f)
        for chave, o in self.CASOS:
            y = np.array(dados[chave]["valores"])
            nos = m.sarima_ajustar(y, o)
            p, q, P, Q = o
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                ref = SARIMAX(y, order=(p, 0, q), seasonal_order=(P, 0, Q, 12), trend="c").fit(disp=False)
            dif = float(np.max(np.abs(m.sarima_prever(nos, y, 12) - ref.get_forecast(12).predicted_mean)))
            self.assertLess(dif, 0.08, msg=f"{chave}: {dif:.3f} p.p.")
            # o coeficiente AR de ordem 1 (o mais bem identificado) fica próximo
            self.assertAlmostEqual(m._separa(nos["params"], o)[1][0], ref.params[list(ref.param_names).index("ar.L1")], delta=0.1)


if __name__ == "__main__":
    unittest.main()
