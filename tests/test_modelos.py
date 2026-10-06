"""Testes do motor econométrico com dados simulados, onde a resposta certa é conhecida."""
import datetime
import os
import sys
import unittest

import numpy as np
from scipy import signal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import modelos as m  # noqa: E402


def sarima_simulado(n=600, mu=0.4, phi=0.6, theta=0.3, Phi=0.4, sd=0.2, semente=1):
    """Gera (1 - φB)(1 - ΦB¹²)(y - μ) = (1 + θB) e."""
    rng = np.random.default_rng(semente)
    ar, ma = m._polinomios([phi], [Phi], [theta], [])
    e = rng.normal(0, sd, n + 200)
    return mu + signal.lfilter(ma, ar, e)[200:]


A1 = np.array([[0.3, 0.0, 0.0],
               [0.4, 0.5, 0.0],   # a variável 0 causa (Granger) a variável 1
               [0.0, 0.2, 0.4]])  # a 1 causa a 2; a 2 não causa ninguém
SIG = np.array([[1.0, 0.3, 0.1], [0.3, 0.8, 0.2], [0.1, 0.2, 0.5]])


def var_simulado(n=600, semente=2):
    rng = np.random.default_rng(semente)
    L = np.linalg.cholesky(SIG)
    X = np.zeros((n + 100, 3))
    for t in range(1, n + 100):
        X[t] = 0.1 + A1 @ X[t - 1] + L @ rng.normal(size=3)
    meses = np.array([(i % 12) + 1 for i in range(n)])
    return X[100:], meses


class TestSarima(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.y = sarima_simulado()
        cls.mod = m.sarima_ajustar(cls.y, (1, 1, 1, 0))

    def test_recupera_parametros(self):
        mu, phi, theta, Phi, _ = m._separa(self.mod["params"], (1, 1, 1, 0))
        self.assertAlmostEqual(mu, 0.4, delta=0.1)
        self.assertAlmostEqual(phi[0], 0.6, delta=0.12)
        self.assertAlmostEqual(theta[0], 0.3, delta=0.15)
        self.assertAlmostEqual(Phi[0], 0.4, delta=0.12)

    def test_modelo_estimado_e_estavel(self):
        self.assertTrue(m._estavel(self.mod["ar"]) and m._estavel(self.mod["ma"]))

    def test_aic_prefere_modelo_com_parte_sazonal(self):
        escolhido = m.sarima_escolher(self.y)
        self.assertGreaterEqual(escolhido["ordem"][2] + escolhido["ordem"][3], 1)

    def test_previsao_converge_para_a_media(self):
        prev = m.sarima_prever(self.mod, self.y, h=240)
        self.assertAlmostEqual(prev[-1], self.mod["params"][0], delta=0.05)

    def test_intervalo_contem_pontual(self):
        sims = m.sarima_simular(self.mod, self.y, n_sim=1000)
        prev = m.sarima_prever(self.mod, self.y)
        lo, hi = np.percentile(sims, [5, 95], axis=0)
        self.assertTrue(np.all((lo <= prev) & (prev <= hi)))


class TestVar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.X, cls.meses = var_simulado()
        cls.mod = m.var_ajustar(cls.X, cls.meses, 1)

    def test_recupera_coeficientes(self):
        _, A, _ = m.var_A(self.mod)
        np.testing.assert_allclose(A[0], A1, atol=0.08)

    def test_aic_escolhe_um_lag(self):
        self.assertEqual(m.var_escolher(self.X, self.meses)["p"], 1)

    def test_irf_no_impacto_e_a_cholesky(self):
        irf = m.var_irf(self.mod)
        np.testing.assert_allclose(irf[0], np.linalg.cholesky(self.mod["sigma"]))
        self.assertTrue(np.all(np.abs(irf[-1]) < 0.05))  # sistema estável: efeito some

    def test_irf_respeita_a_ordem(self):
        """No mês do choque, quem vem depois na ordem não afeta quem vem antes."""
        irf = m.var_irf(self.mod)
        self.assertEqual(irf[0, 0, 1], 0.0)
        self.assertEqual(irf[0, 1, 2], 0.0)

    def test_granger_acha_causalidade_verdadeira_e_nao_inventa(self):
        g = {(r["causa"], r["efeito"]): r["p"] for r in m.var_granger(self.X, self.meses, 1)}
        self.assertLess(g[(0, 1)], 0.01)
        self.assertLess(g[(1, 2)], 0.01)
        self.assertGreater(g[(2, 0)], 0.01)
        self.assertGreater(g[(2, 1)], 0.01)

    def test_bandas_envolvem_o_ponto(self):
        X, meses = self.X[:300], self.meses[:300]
        mod = m.var_ajustar(X, meses, 1)
        lo, hi = m.var_irf_bandas(mod, X, meses, h=6, n_boot=150)
        irf = m.var_irf(mod, 6)
        self.assertGreater(np.mean((lo <= irf + 1e-9) & (irf <= hi + 1e-9)), 0.9)

    def test_previsao_converge_para_media_incondicional(self):
        media = np.linalg.solve(np.eye(3) - A1, np.full(3, 0.1))
        prev = m.var_prever(self.mod, self.X, self.meses[-1], h=120)
        np.testing.assert_allclose(prev[-1], media, atol=0.25)


class TestBacktestEDados(unittest.TestCase):
    def test_acumulado(self):
        self.assertAlmostEqual(float(m.acumulado([1.0] * 12)), (1.01 ** 12 - 1) * 100, places=6)

    def test_backtest_premia_previsor_bom_e_nao_ve_o_futuro(self):
        y = sarima_simulado(n=300, semente=5)
        vistos = []

        def prever_em(t):
            vistos.append(t)
            mod = m.sarima_ajustar(y[:t], (1, 1, 1, 0))
            return m.sarima_prever(mod, y[:t]), m.sarima_simular(mod, y[:t], n_sim=300)

        bt = m.backtest(y, prever_em, n_origens=24)
        self.assertEqual(max(vistos), len(y) - m.HORIZONTE)  # nunca usa os últimos 12 meses para prever
        self.assertLess(bt["rmse_mensal"]["1"]["modelo"], bt["rmse_mensal"]["1"]["ingenuo"])
        self.assertGreater(bt["acumulado_12m"]["ganho_pct"], 0)
        self.assertTrue(55 <= bt["cobertura_80"]["mes_seguinte"] <= 100)

    def test_painel_transforma_dolar_e_selic(self):
        d = [datetime.date(2020, mm, 1) for mm in (1, 2, 3)]
        brutos = {"ipca": dict(zip(d, [0.2, 0.3, 0.4])), "igpm": dict(zip(d, [0.1, 0.2, 0.3])),
                  "dolar": dict(zip(d, [4.0, 4.4, 4.4])), "selic": dict(zip(d, [10.0, 10.5, 10.25]))}
        datas, p = m.montar_painel(brutos)
        self.assertEqual(datas, d[1:])
        np.testing.assert_allclose(p["dolar"], [10.0, 0.0])
        np.testing.assert_allclose(p["selic"], [0.5, -0.25])
        np.testing.assert_allclose(p["ipca"], [0.3, 0.4])


if __name__ == "__main__":
    unittest.main()
