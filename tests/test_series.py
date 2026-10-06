"""Testes do catálogo de indicadores (scripts/series.py), sem acessar a internet."""
import datetime
import json
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import series as S  # noqa: E402

BAIXAR_SGS = S.baixar_sgs  # original, antes de os testes trocarem por versões falsas

D = datetime.date


class TestConversoes(unittest.TestCase):
    def test_media_mensal_de_serie_diaria(self):
        pontos = {D(2020, 1, 2): 10.0, D(2020, 1, 20): 12.0, D(2020, 2, 3): 13.0}
        self.assertEqual(S.para_mensal(pontos, "media"), [(D(2020, 1, 1), 11.0), (D(2020, 2, 1), 13.0)])

    def test_mensal_pega_o_ultimo_valor_do_mes(self):
        pontos = {D(2020, 1, 1): 1.0, D(2020, 1, 31): 2.0}
        self.assertEqual(S.para_mensal(pontos, "mensal"), [(D(2020, 1, 1), 2.0)])

    def test_variacao_em_12_meses(self):
        pontos = {D(2019, m, 1): 100.0 for m in range(1, 13)} | {D(2020, 1, 1): 104.0}
        self.assertAlmostEqual(S.para_mensal(pontos, "yoy")[0][1], 4.0)

    def test_descarta_antes_do_inicio(self):
        pontos = {D(2002, 12, 1): 1.0, D(2003, 1, 1): 2.0}
        self.assertEqual(S.para_mensal(pontos, "mensal"), [(D(2003, 1, 1), 2.0)])

    def test_transformar_e_integrar_voltam_ao_nivel(self):
        nivel = np.array([100.0, 102.0, 101.0, 105.0])
        for modo in ("dif", "logdif"):
            x = S.transformar(nivel, modo)
            reconstruido = S.integrar(nivel[0], x, modo)
            np.testing.assert_allclose(reconstruido, nivel[1:], err_msg=modo)


class TestSazonalidade(unittest.TestCase):
    def test_detecta_padrao_sazonal(self):
        rng = np.random.default_rng(0)
        meses = np.array([(i % 12) + 1 for i in range(180)])
        x = np.where(meses == 1, 1.0, 0.0) + rng.normal(0, 0.1, 180)
        efeito, p = S.sazonalidade(meses, x)
        self.assertLess(p, 0.001)
        self.assertEqual(int(np.argmax(efeito)), 0)  # janeiro

    def test_nao_inventa_padrao_em_ruido(self):
        rng = np.random.default_rng(1)
        meses = np.array([(i % 12) + 1 for i in range(180)])
        _, p = S.sazonalidade(meses, rng.normal(0, 1, 180))
        self.assertGreater(p, 0.01)


class TestProcessar(unittest.TestCase):
    def test_serie_completa_sem_internet(self):
        rng = np.random.default_rng(2)
        datas = [D(2003 + i // 12, i % 12 + 1, 1) for i in range(200)]
        nivel = 3.0 * np.exp(np.cumsum(rng.normal(0, 2, 200)) / 100)
        S.baixar_sgs = lambda codigo: dict(zip(datas, nivel))
        cfg = next(c for c in S.CATALOGO if c["id"] == "dolar")
        r = S.processar(cfg, rng)
        self.assertEqual(len(r["dados"]), 200)
        a = r["analise"]
        self.assertEqual(len(a["previsao"]), 12)
        self.assertEqual(a["previsao"][0][0], "2019-09")  # mês seguinte ao último (ago/2019)
        mes, ponto, lo, hi = a["previsao"][0]
        self.assertTrue(lo <= ponto <= hi)
        self.assertTrue(all(v > 0 for _, v, *_ in a["previsao"]))  # dólar previsto positivo
        self.assertEqual(len(a["sazonal_efeito"]), 12)

    def test_serie_anual_do_ipea(self):
        rng = np.random.default_rng(3)
        pontos = {D(1990 + i, 1, 1): 0.6 - i * 0.003 for i in range(30)}
        S.ipea_descobrir = lambda termo: ("PNADC_GINI", pontos)
        cfg = next(c for c in S.CATALOGO if c["id"] == "gini")
        r = S.processar(cfg, rng)
        self.assertEqual(r["freq"], "anual")
        self.assertEqual(r["dados"][0], ["1990", 0.6])
        self.assertNotIn("analise", r)
        self.assertIn("PNADC_GINI", r["fonte"])

    def test_ipea_fica_so_com_o_brasil(self):
        S._get = lambda url, **k: json.dumps({"value": [
            {"VALDATA": "2020-01-01T00:00:00-03:00", "VALVALOR": 0.52, "NIVNOME": "Brasil"},
            {"VALDATA": "2020-01-01T00:00:00-03:00", "VALVALOR": 0.61, "NIVNOME": "Estados"},
            {"VALDATA": "2021-01-01T00:00:00-03:00", "VALVALOR": 0.53, "NIVNOME": ""}]})
        self.assertEqual(S.baixar_ipea("X"), {D(2020, 1, 1): 0.52, D(2021, 1, 1): 0.53})

    def test_sgs_nao_salva_serie_cortada(self):
        """Se o SGS devolve lixo num bloco de anos, a série inteira falha (e a versão anterior é mantida)."""
        respostas = iter(['[{"data":"01/01/2003","valor":"1"}]'] + ["<html>erro</html>"] * 50)
        S._get = lambda url, **k: next(respostas)
        S.time.sleep = lambda s: None
        with self.assertRaises(ValueError):
            BAIXAR_SGS(999)

    def test_catalogo_sem_ids_repetidos_e_com_campos(self):
        ids = [c["id"] for c in S.CATALOGO]
        self.assertEqual(len(ids), len(set(ids)))
        for c in S.CATALOGO:
            self.assertIn(c["modelar"], ("nivel", "dif", "logdif"))
            self.assertIn(c["transf"], ("mensal", "media", "yoy", "anual"))
            self.assertTrue(c["descricao"])


if __name__ == "__main__":
    unittest.main()
