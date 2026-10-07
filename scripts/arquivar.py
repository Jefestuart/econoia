"""Guarda uma cópia datada dos dados publicados (séries e modelos) para que um número citado
possa ser conferido depois, mesmo que o site já tenha atualizado.

Uso: python scripts/arquivar.py <pasta_dos_dados> <pasta_do_arquivo> [AAAA-MM-DD]

Cria <arquivo>/AAAA-MM-DD/{series,modelos}.json e atualiza <arquivo>/indice.json com o
tamanho e o SHA-256 de cada arquivo. Rodar duas vezes no mesmo dia só sobrescreve o dia.
"""
import datetime
import hashlib
import json
import os
import re
import sys

ARQUIVOS = ("series.json", "modelos.json")
PADRAO_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def sha256(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(65536), b""):
            h.update(bloco)
    return h.hexdigest()


def arquivar(dados, arquivo, dia=None):
    dia = dia or datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    if not PADRAO_DATA.match(dia):
        raise ValueError(f"data inválida: {dia}")
    destino = os.path.join(arquivo, dia)
    os.makedirs(destino, exist_ok=True)
    arqs = {}
    for nome in ARQUIVOS:
        origem = os.path.join(dados, nome)
        if not os.path.exists(origem):
            continue
        with open(origem, "rb") as f:
            bruto = f.read()
        json.loads(bruto)  # só guarda JSON válido
        with open(os.path.join(destino, nome), "wb") as f:
            f.write(bruto)
        arqs[nome] = {"bytes": len(bruto), "sha256": hashlib.sha256(bruto).hexdigest()}
    if not arqs:
        raise FileNotFoundError("nenhum arquivo de dados encontrado")

    caminho_indice = os.path.join(arquivo, "indice.json")
    try:
        with open(caminho_indice, encoding="utf-8") as f:
            indice = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        indice = {}
    snaps = {s["data"]: s for s in indice.get("snapshots", [])}
    snaps[dia] = {"data": dia, "arquivos": arqs}
    indice = {
        "descricao": "Cópias diárias dos dados do EconoIA Brasil (econoia.com.br). Cada arquivo tem SHA-256 para conferência.",
        "snapshots": [snaps[d] for d in sorted(snaps)],
    }
    with open(caminho_indice, "w", encoding="utf-8") as f:
        json.dump(indice, f, ensure_ascii=False, indent=1)
    return indice


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    r = arquivar(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    print(f"{len(r['snapshots'])} cópias no arquivo; última: {r['snapshots'][-1]['data']}")
