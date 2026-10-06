"""Testes do motor econométrico com dados simulados, onde a resposta certa é conhecida."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import modelos as m  # noqa: E402

PHI = (0.5, 0.2)
SAZ = [0.0, 0.3, 0.1, -0.1, -0.2, 0.0, 0.0, 0.1, 0.0, 0.2, 0.1, 0.3]  # efeito de jan..dez


def serie_simulada(n=300, semente=1, ruido=0.15):
    rng = np.random.default_rng(semente)
    meses = np.array([(i % 12) + 1 for i in range(n)])
    y = np.zeros(n)
    for t in range(2, n):
        y[t] = 0.1 + PHI[0] * y[t - 1] + PHI[1] * y[t - 2] + SAZ[meses[t] - 1] + rng.normal(0, ruido)
    return y[50:], meses[50:]  # descarta o início, antes de estabilizar


class TestModelo(unittest.TestCase):
    def test_recupera_coeficientes(self):
        y, meses = serie_simulada(n=1200)
        mod = m.ajustar(y, meses, 2)
        self.assertAlmostEqual(mod["beta"][1], PHI[0], delta=0.07)
        self.assertAlmostEqual(mod["beta"][2], PHI[1], delta=0.07)

    def test_aic_escolhe_ordem_proxima_da_verdadeira(self):
        y, meses = serie_simulada(n=1200)
        self.assertIn(m.escolher_ordem(y, meses)["p"], (2, 3, 4))

    def test_previsao_tem_horizonte_certo_e_e_finita(self):
        y, meses = serie_simulada()
        mod = m.escolher_ordem(y, meses)
        prev = m.prever(mod, y, meses[-1])
        self.assertEqual(len(prev), m.HORIZONTE)
        self.assertTrue(np.all(np.isfinite(prev)))

    def test_meses_futuros_viram_o_ano(self):
        self.assertEqual(m.proximos_meses(11, 4), [12, 1, 2, 3])

    def test_acumulado(self):
        self.assertAlmostEqual(float(m.acumulado([1.0] * 12)), (1.01 ** 12 - 1) * 100, places=6)
        self.assertAlmostEqual(float(m.acumulado([0.0, 0.0])), 0.0)

    def test_intervalos_contem_a_previsao_pontual(self):
        y, meses = serie_simulada()
        mod = m.escolher_ordem(y, meses)
        sims = m.simular(mod, y, meses[-1], n_sim=1000)
        prev = m.prever(mod, y, meses[-1])
        lo, hi = np.percentile(sims, [10, 90], axis=0)
        self.assertTrue(np.all(lo <= prev + 1e-9) and np.all(prev <= hi + 1e-9))
        self.assertTrue(np.all(hi - lo > 0))


class TestBacktest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        y, meses = serie_simulada(n=400, semente=7)
        cls.bt = m.backtest(y, meses, n_origens=36, n_sim=300)

    def test_modelo_certo_vence_os_ingenuos(self):
        for hz in ("1", "3"):
            r = self.bt["rmse_mensal"][hz]
            self.assertLess(r["modelo"], min(r["ingenuo"], r["sazonal"]), hz)
        self.assertGreater(self.bt["acumulado_12m"]["ganho_pct"], 0)

    def test_intervalo_de_80_cobre_perto_de_80(self):
        self.assertGreaterEqual(self.bt["cobertura_80"]["mes_seguinte"], 60)
        self.assertLessEqual(self.bt["cobertura_80"]["mes_seguinte"], 97)

    def test_nao_usa_o_futuro(self):
        """Mudar dados depois da última origem não pode alterar a previsão feita nela."""
        y, meses = serie_simulada(n=300, semente=3)
        t = 200
        p1 = m.prever(m.escolher_ordem(y[:t], meses[:t]), y[:t], meses[t - 1])
        y2 = y.copy()
        y2[t:] += 5.0
        p2 = m.prever(m.escolher_ordem(y2[:t], meses[:t]), y2[:t], meses[t - 1])
        np.testing.assert_allclose(p1, p2)


if __name__ == "__main__":
    unittest.main()
