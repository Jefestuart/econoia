"""Robô da EconoIA: busca dados no Banco Central, IBGE e mercado e grava data/data.json.
Roda no GitHub Actions. Só usa a biblioteca padrão do Python.
Se uma fonte falhar, mantém o valor anterior (o site nunca fica vazio).
"""
import json, urllib.request, urllib.parse, datetime, os, sys
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")
NOW = datetime.datetime.now(TZ)
PATH = os.path.join(os.path.dirname(__file__), "..", "data", "data.json")
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
UA = {"User-Agent": "Mozilla/5.0 (EconoIA bot; +https://github.com)", "Accept": "application/json"}

data = json.load(open(PATH, encoding="utf-8"))
log = []


def get(url, tries=3):
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa
            last = e
    raise last


def step(name):
    def deco(fn):
        try:
            fn()
            log.append(f"OK   {name}")
        except Exception as e:  # noqa
            log.append(f"FALHA {name}: {e}")
        return fn
    return deco


def lab(ddmmyyyy):  # "01/08/2026" -> "ago/26"
    _, m, y = ddmmyyyy.split("/")
    return f"{MESES[int(m) - 1]}/{y[2:]}"


def sgs(code, start=None, last=None):
    base = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"
    if last:
        return get(f"{base}/ultimos/{last}?formato=json")
    return get(f"{base}?formato=json&dataInicial={start}&dataFinal={NOW:%d/%m/%Y}")


# ---------- Banco Central: Selic meta ----------
@step("Selic (SGS 432)")
def _():
    start = (NOW - datetime.timedelta(days=730)).strftime("%d/%m/%Y")
    rows = sgs(432, start=start)
    pts, prev = [], None
    for r in rows:
        v = float(r["valor"])
        if v != prev:
            pts.append([lab(r["data"]), v, r["data"]])
            prev = v
    if not pts:
        raise ValueError("vazio")
    data["selic"] = [[p[0], p[1]] for p in pts]
    data["selic_data"] = pts[-1][2]


# ---------- IBGE via SGS: IPCA mensal e 12 meses ----------
@step("IPCA (SGS 433 e 13522)")
def _():
    m = sgs(433, last=24)
    a = {r["data"]: float(r["valor"]) for r in sgs(13522, last=24)}
    out = [[lab(r["data"]), float(r["valor"]), a.get(r["data"])] for r in m]
    out = [r for r in out if r[2] is not None]
    if len(out) < 6:
        raise ValueError("poucos dados")
    data["ipca"] = out


# ---------- FGV via SGS: IGP-M ----------
@step("IGP-M (SGS 189)")
def _():
    m = sgs(189, last=36)
    vals = [float(r["valor"]) for r in m]
    out = []
    for i, r in enumerate(m):
        if i < 11:
            continue
        f = 1.0
        for v in vals[i - 11:i + 1]:
            f *= 1 + v / 100
        out.append([lab(r["data"]), vals[i], round((f - 1) * 100, 2)])
    if len(out) < 6:
        raise ValueError("poucos dados")
    data["igpm"] = out[-24:]


# ---------- IBGE SIDRA: desemprego ----------
@step("Desocupação PNAD (SIDRA 6381)")
def _():
    rows = get("https://apisidra.ibge.gov.br/values/t/6381/n1/all/v/4099/p/last%201")
    r = rows[1]
    data["desemprego"] = ["trim. " + r["D3N"], float(r["V"])]


# ---------- IBGE SIDRA: PIB trimestral ----------
@step("PIB trimestral (SIDRA 5932)")
def _():
    def q(code):  # "202602" -> "2T26"
        return f"{int(code[4:])}T{code[2:4]}"
    t = get("https://apisidra.ibge.gov.br/values/t/5932/n1/all/v/6564/p/last%2010/c11255/90707")[1:]
    data["pibT"] = [[q(r["D3C"]), float(r["V"])] for r in t if r["V"] not in ("...", "-")]
    y = get("https://apisidra.ibge.gov.br/values/t/5932/n1/all/v/6561/p/last%201/c11255/90707")[1]
    data["pibYoY"] = [q(y["D3C"]), float(y["V"])]


# ---------- Banco Central PTAX: câmbio ----------
@step("Câmbio PTAX")
def _():
    ini = (NOW - datetime.timedelta(days=10)).strftime("%m-%d-%Y")
    fim = NOW.strftime("%m-%d-%Y")
    novo, data_ref = [], None
    AWESOME = ("CNY", "MXN", "ARS")  # fora da PTAX: vêm da AwesomeAPI
    aw = {}
    try:
        aw = get("https://economia.awesomeapi.com.br/json/last/" + ",".join(c + "-BRL" for c in AWESOME))
    except Exception as e:  # noqa
        log.append(f"     AwesomeAPI indisponível: {e}")
    for item in data["fx"]:
        if item[0] in AWESOME:
            code = item[0]
            unit = 1000 if code == "ARS" else 1
            q = aw.get(code + "BRL")
            if q:
                item = [code, item[1], item[2], round(float(q["bid"]) * unit, 4), 1, "AwesomeAPI"]
            else:
                log.append(f"     moeda {code} mantida (AwesomeAPI sem dado)")
                item = (item + [None, None])[:5] + ["AwesomeAPI"]
                item[4] = 0
            novo.append(item)
            continue
        code, unit = item[0], (100 if item[0] == "JPY" else 1000 if item[0] == "ARS" else 1)
        try:
            url = ("https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
                   "CotacaoMoedaPeriodo(moeda=@moeda,dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
                   f"?@moeda='{code}'&@dataInicial='{ini}'&@dataFinalCotacao='{fim}'&$format=json")
            v = get(url)["value"]
            last = v[-1]
            item = [code, item[1], item[2], round(float(last["cotacaoVenda"]) * unit, 4), 1, "PTAX/BCB"]
            data_ref = last["dataHoraCotacao"][:16]
        except Exception as e:  # noqa
            log.append(f"     moeda {code} mantida: {e}")
        novo.append(item)
    data["fx"] = novo
    if data_ref:
        d, h = data_ref.split(" ")
        y, m, dd = d.split("-")
        data["fx_data"] = f"{dd}/{m}/{y} {h} (PTAX/BCB)"


# ---------- Mercado: Ibovespa, ações, EUA ----------
@step("Bolsa (Yahoo Finance)")
def _():
    symbols = [("IBOV", "^BVSP", "pts"), ("PETR4", "PETR4.SA", "R$"), ("VALE3", "VALE3.SA", "R$"),
               ("ITUB4", "ITUB4.SA", "R$"), ("BBAS3", "BBAS3.SA", "R$"), ("BBDC4", "BBDC4.SA", "R$"),
               ("ABEV3", "ABEV3.SA", "R$"), ("WEGE3", "WEGE3.SA", "R$"),
               ("S&P 500", "^GSPC", "pts"), ("NASDAQ", "^IXIC", "pts"), ("DOW JONES", "^DJI", "pts")]
    old = {m[0]: m for m in data.get("market", [])}
    out, ok = [], 0
    for name, sym, kind in symbols:
        try:
            j = get("https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(sym) + "?range=5d&interval=1d")
            meta = j["chart"]["result"][0]["meta"]
            p, prev = float(meta["regularMarketPrice"]), float(meta["chartPreviousClose"])
            closes = [c for c in j["chart"]["result"][0]["indicators"]["quote"][0]["close"] if c]
            if len(closes) >= 2:
                prev = closes[-2]
            pct = round((p / prev - 1) * 100, 2)
            txt = (f"{p:,.0f} pts".replace(",", ".") if kind == "pts"
                   else "R$ " + f"{p:.2f}".replace(".", ","))
            out.append([name, txt, pct])
            ok += 1
        except Exception as e:  # noqa
            log.append(f"     {name} mantido: {e}")
            if name in old:
                out.append(old[name])
    if ok == 0:
        raise ValueError("nenhuma cotação")
    data["market"] = out
    data["market_data"] = NOW.strftime("%d/%m/%Y %H:%M") + " (Brasília)"



# ---------- Commodities: ouro, prata, petróleo (Yahoo Finance) ----------
@step("Ouro e commodities (Yahoo)")
def _():
    usd = next((f[3] for f in data["fx"] if f[0] == "USD"), None)
    itens = [("Ouro", "GC=F", "onça-troy"), ("Prata", "SI=F", "onça-troy"), ("Petróleo Brent", "BZ=F", "barril")]
    out = []
    for nome, sym, unid in itens:
        j = get("https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(sym) + "?range=5d&interval=1d")
        res = j["chart"]["result"][0]
        p = float(res["meta"]["regularMarketPrice"])
        closes = [c for c in res["indicators"]["quote"][0]["close"] if c]
        prev = closes[-2] if len(closes) >= 2 else float(res["meta"]["chartPreviousClose"])
        out.append([nome, unid, round(p, 2), round(p * usd, 2) if usd else None, round((p / prev - 1) * 100, 2)])
    data["commod"] = out


# ---------- Criptomoedas (CoinGecko, sem chave) ----------
@step("Cripto (CoinGecko)")
def _():
    ids = [("bitcoin", "BTC", "Bitcoin"), ("ethereum", "ETH", "Ethereum"), ("solana", "SOL", "Solana"),
           ("ripple", "XRP", "XRP"), ("binancecoin", "BNB", "BNB"), ("dogecoin", "DOGE", "Dogecoin"),
           ("cardano", "ADA", "Cardano"), ("tether", "USDT", "Tether")]
    j = get("https://api.coingecko.com/api/v3/simple/price?ids=" + ",".join(i[0] for i in ids) +
            "&vs_currencies=brl,usd&include_24hr_change=true&include_market_cap=true")
    out = []
    for cid, sym, nome in ids:
        c = j.get(cid)
        if not c:
            continue
        out.append([sym, nome, c["brl"], c["usd"], round(c.get("brl_24h_change") or 0, 2), c.get("usd_market_cap")])
    if not out:
        raise ValueError("vazio")
    data["crypto"] = out
    data["crypto_data"] = NOW.strftime("%d/%m/%Y %H:%M") + " (Brasília)"


data["updated"] = NOW.isoformat(timespec="minutes")
json.dump(data, open(PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\n".join(log))
if all(l.startswith("FALHA") for l in log if not l.startswith("     ")):
    sys.exit(1)
