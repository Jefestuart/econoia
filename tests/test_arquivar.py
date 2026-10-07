import hashlib
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from arquivar import arquivar  # noqa: E402


def escreve(pasta, nome, obj):
    with open(os.path.join(pasta, nome), "w", encoding="utf-8") as f:
        json.dump(obj, f)


class TesteArquivo(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.dados = os.path.join(self.t.name, "dados")
        self.arq = os.path.join(self.t.name, "arq")
        os.makedirs(self.dados)
        escreve(self.dados, "series.json", {"a": 1})
        escreve(self.dados, "modelos.json", {"b": 2})

    def tearDown(self):
        self.t.cleanup()

    def test_copia_arquivos_e_indexa_com_sha256(self):
        r = arquivar(self.dados, self.arq, "2026-10-06")
        snap = r["snapshots"][0]
        self.assertEqual(snap["data"], "2026-10-06")
        copia = os.path.join(self.arq, "2026-10-06", "series.json")
        with open(copia, "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), snap["arquivos"]["series.json"]["sha256"])
        with open(os.path.join(self.arq, "indice.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), r)

    def test_dias_acumulam_em_ordem_e_o_mesmo_dia_sobrescreve(self):
        arquivar(self.dados, self.arq, "2026-10-07")
        arquivar(self.dados, self.arq, "2026-10-06")
        escreve(self.dados, "series.json", {"a": 99})
        r = arquivar(self.dados, self.arq, "2026-10-06")
        self.assertEqual([s["data"] for s in r["snapshots"]], ["2026-10-06", "2026-10-07"])
        with open(os.path.join(self.arq, "2026-10-06", "series.json")) as f:
            self.assertEqual(json.load(f), {"a": 99})

    def test_recusa_data_estranha_json_invalido_e_pasta_vazia(self):
        for ruim in ["../x", "2026-1-6", "hoje"]:
            with self.assertRaises(ValueError):
                arquivar(self.dados, self.arq, ruim)
        with open(os.path.join(self.dados, "series.json"), "w") as f:
            f.write("{quebrado")
        with self.assertRaises(ValueError):
            arquivar(self.dados, self.arq, "2026-10-06")
        vazia = os.path.join(self.t.name, "vazia")
        os.makedirs(vazia)
        with self.assertRaises(FileNotFoundError):
            arquivar(vazia, self.arq, "2026-10-06")


if __name__ == "__main__":
    unittest.main()
