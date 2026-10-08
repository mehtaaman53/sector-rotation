"""
THE TRADE TRIBE — Sector Rotation Engine
Har hafte GitHub Actions pe automatic chalta hai:
  1. NSE sector indices ka data (Yahoo Finance) laata hai
  2. RRG (RS-Ratio / RS-Momentum) nikalta hai — TradingView indicator wala hi formula
  3. Sector breadth (% stocks 50 DMA ke upar) + top RS stocks nikalta hai
  4. docs/index.html dashboard banata hai (GitHub Pages pe live)
  5. Telegram pe alert bhejta hai
Aapko isme kuch chhedna nahi hai. Sectors badalne ho to SECTORS list edit karo.
"""
import json, os, sys, datetime as dt
import numpy as np
import pandas as pd

BENCH = "^NSEI"
# naam, Yahoo ticker, niftyindices constituents file
SECTORS = [
    ("IT",           "^CNXIT",               "ind_niftyitlist.csv"),
    ("Bank",         "^NSEBANK",             "ind_niftybanklist.csv"),
    ("Pvt Bank",     "NIFTY_PVT_BANK.NS",    "ind_nifty_privatebanklist.csv"),
    ("PSU Bank",     "^CNXPSUBANK",          "ind_niftypsubanklist.csv"),
    ("Fin Services", "NIFTY_FIN_SERVICE.NS", "ind_niftyfinancelist.csv"),
    ("Auto",         "^CNXAUTO",             "ind_niftyautolist.csv"),
    ("Pharma",       "^CNXPHARMA",           "ind_niftypharmalist.csv"),
    ("Healthcare",   "NIFTY_HEALTHCARE.NS",  "ind_niftyhealthcarelist.csv"),
    ("FMCG",         "^CNXFMCG",             "ind_niftyfmcglist.csv"),
    ("Metal",        "^CNXMETAL",            "ind_niftymetallist.csv"),
    ("Realty",       "^CNXREALTY",           "ind_niftyrealtylist.csv"),
    ("Energy",       "^CNXENERGY",           "ind_niftyenergylist.csv"),
    ("Oil & Gas",    "NIFTY_OIL_AND_GAS.NS", "ind_niftyoilgaslist.csv"),
    ("Infra",        "^CNXINFRA",            "ind_niftyinfralist.csv"),
    ("PSE",          "^CNXPSE",              "ind_niftypselist.csv"),
    ("Media",        "^CNXMEDIA",            "ind_niftymedialist.csv"),
    ("Consumption",  "^CNXCONSUM",           "ind_niftyconsumptionlist.csv"),
    ("Defence",      "NIFTY_IND_DEFENCE.NS", "ind_niftyindiadefence_list.csv"),
]
RS_LEN, MOM_LEN, SMOOTH, TREND_LEN, PERF_LEN, TAIL = 10, 4, 3, 40, 13, 8
PHASE = {1: "LEADING", 2: "WEAKENING", 3: "LAGGING", 4: "IMPROVING", 0: "NO DATA"}
EMOJI = {1: "🟢", 2: "🟡", 3: "🔴", 4: "🔵", 0: "⚪"}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")


# ── Data ─────────────────────────────────────────────────────────────
def fetch_prices(tickers, period="3y"):
    import yfinance as yf
    df = yf.download(tickers, period=period, interval="1d", auto_adjust=True,
                     progress=False, group_by="column", threads=True)
    close = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df[["Close"]].rename(columns={"Close": tickers[0]})
    return close.dropna(how="all")


def fetch_constituents(fname):
    import requests, io
    url = f"https://niftyindices.com/IndexConstituent/{fname}"
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        c = pd.read_csv(io.StringIO(r.text))
        return [s.strip() + ".NS" for s in c["Symbol"].dropna()]
    except Exception as e:
        print(f"  constituents fail {fname}: {e}")
        return []


def demo_data():
    """Synthetic data — sirf test ke liye (python rotation.py --demo)."""
    rng = np.random.default_rng(7)
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=750)
    bench = 20000 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, len(idx))))
    data = {BENCH: bench}
    cons = {}
    for k, (name, tk, _) in enumerate(SECTORS):
        drift = np.sin(np.linspace(0, 3 + k * 0.4, len(idx)) + k) * 0.0012
        data[tk] = bench * np.exp(np.cumsum(drift + rng.normal(0, 0.006, len(idx))))
        cons[name] = []
        for j in range(6):
            sym = f"{name[:4].upper().replace(' ', '')}{j}.NS"
            data[sym] = data[tk] * np.exp(np.cumsum(rng.normal(0.0002 * (j - 2), 0.012, len(idx))))
            cons[name].append(sym)
    return pd.DataFrame(data, index=idx), cons


# ── Calculations (TradingView indicator jaisa hi) ──────────────────────
def quad(r, m):
    if pd.isna(r) or pd.isna(m):
        return 0
    return (1 if m >= 100 else 2) if r >= 100 else (4 if m >= 100 else 3)


def rrg(sec_w, bench_w):
    rs = 100 * sec_w / bench_w
    rs_s = rs.ewm(span=SMOOTH, adjust=False).mean()
    ratio = 100 * rs_s / rs_s.rolling(RS_LEN).mean()
    mom = 100 * ratio / ratio.shift(MOM_LEN)
    return ratio, mom


def analyse(daily, cons_map):
    weekly = daily.resample("W-FRI").last()
    bw = weekly[BENCH]
    sectors = []
    for name, tk, _ in SECTORS:
        if tk not in weekly or weekly[tk].dropna().size < RS_LEN + MOM_LEN + 5:
            print(f"  skip {name} ({tk}) — data nahi mila")
            continue
        sw = weekly[tk]
        ratio, mom = rrg(sw, bw)
        valid = ratio.notna() & mom.notna()
        r, m = ratio[valid], mom[valid]
        q_now, q_prev = quad(r.iloc[-1], m.iloc[-1]), quad(r.iloc[-2], m.iloc[-2])
        perf = (sw.iloc[-1] / sw.iloc[-1 - PERF_LEN] - bw.iloc[-1] / bw.iloc[-1 - PERF_LEN]) * 100
        trend_up = bool(sw.iloc[-1] > sw.rolling(TREND_LEN).mean().iloc[-1])

        # Breadth + top stocks
        syms = [s for s in cons_map.get(name, []) if s in daily]
        breadth, top = None, []
        if syms:
            px = daily[syms].ffill()
            above = (px.iloc[-1] > px.rolling(50).mean().iloc[-1])
            breadth = round(100 * above.mean(), 0)
            bd = daily[BENCH].ffill()
            rows = []
            for s in syms:
                p = px[s].dropna()
                if len(p) < 130:
                    continue
                rr = p / bd.reindex(p.index)
                mrs = (rr.iloc[-1] / rr.rolling(125).mean().iloc[-1] - 1) * 100
                ret3m = (p.iloc[-1] / p.iloc[-63] - 1) * 100
                rows.append({"symbol": s.replace(".NS", ""), "rs": round(float(mrs), 1),
                             "ret3m": round(float(ret3m), 1),
                             "above50": bool(p.iloc[-1] > p.rolling(50).mean().iloc[-1])})
            top = sorted(rows, key=lambda x: -x["rs"])[:5]

        sectors.append({
            "name": name, "ratio": round(float(r.iloc[-1]), 2), "mom": round(float(m.iloc[-1]), 2),
            "phase": q_now, "prev_phase": q_prev, "perf3m": round(float(perf), 1),
            "trend_up": trend_up, "breadth": breadth, "top": top,
            "tail": [[round(float(a), 2), round(float(b), 2)] for a, b in zip(r.iloc[-TAIL:], m.iloc[-TAIL:])],
        })
    prio = {1: 0, 4: 1, 2: 2, 3: 3, 0: 9}
    sectors.sort(key=lambda s: (prio[s["phase"]], -((s["ratio"] - 100) + 2 * (s["mom"] - 100))))
    return {"asof": daily.index[-1].strftime("%d %b %Y"),
            "generated": dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).strftime("%d %b %Y, %I:%M %p IST"),
            "sectors": sectors}


# ── Alert text ───────────────────────────────────────────────────────
def alert_text(res, url=""):
    lines = [f"📊 *Trade Tribe — Weekly Sector Rotation*", f"_Week ending {res['asof']}_", ""]
    changes = []
    for s in res["sectors"]:
        c, p = s["phase"], s["prev_phase"]
        if c == p or 0 in (c, p):
            continue
        if c == 1:
            changes.append(f"🟢 *{s['name']}* → LEADING. Top stocks dekho.")
        elif c == 4 and p == 3:
            changes.append(f"🔵 *{s['name']}* → IMPROVING. Watchlist mein daalo (early).")
        elif c == 2 and p == 1:
            changes.append(f"🟡 *{s['name']}* → WEAKENING. Profit book / SL tight.")
        elif c == 3:
            changes.append(f"🔴 *{s['name']}* → LAGGING. Door raho.")
    lines += (["*Is hafte ke badlav:*"] + changes) if changes else ["Is hafte koi phase change nahi."]
    lines.append("")
    for ph in (1, 4):
        group = [s for s in res["sectors"] if s["phase"] == ph]
        if group:
            lines.append(f"{EMOJI[ph]} *{PHASE[ph]}:*")
            for s in group:
                b = f", breadth {int(s['breadth'])}%" if s["breadth"] is not None else ""
                tops = ", ".join(t["symbol"] for t in s["top"][:3] if t["above50"])
                lines.append(f"• {s['name']} ({s['perf3m']:+.1f}% vs Nifty 3M{b})" + (f"\n   ↳ {tops}" if tops else ""))
    weak = [s["name"] for s in res["sectors"] if s["phase"] in (2, 3)]
    if weak:
        lines += ["", "🟡🔴 Weak/avoid: " + ", ".join(weak)]
    if url:
        lines += ["", f"Full dashboard: {url}"]
    return "\n".join(lines)


def send_telegram(text):
    import requests
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        print("Telegram secrets nahi mile — alert skip.")
        return
    r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                      data={"chat_id": chat, "text": text, "parse_mode": "Markdown",
                            "disable_web_page_preview": "true"}, timeout=30)
    if r.status_code != 200:  # Markdown me koi ajeeb character ho to plain text bhejo
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          data={"chat_id": chat, "text": text.replace("*", "").replace("_", "")}, timeout=30)
    print("Telegram:", r.status_code, r.text[:200])


# ── Main ─────────────────────────────────────────────────────────────
def main():
    demo = "--demo" in sys.argv
    if demo:
        daily, cons_map = demo_data()
    else:
        cons_map = {name: fetch_constituents(f) for name, _, f in SECTORS}
        all_stocks = sorted({s for v in cons_map.values() for s in v})
        tickers = [BENCH] + [tk for _, tk, _ in SECTORS] + all_stocks
        print(f"Downloading {len(tickers)} tickers…")
        daily = fetch_prices(tickers)
    res = analyse(daily, cons_map)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "data.json"), "w") as f:
        json.dump(res, f, indent=1)
    tpl = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard_template.html"), encoding="utf-8").read()
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(tpl.replace("/*__DATA__*/null", json.dumps(res)))
    msg = alert_text(res, os.environ.get("DASHBOARD_URL", ""))
    print(msg)
    if not demo and "--no-alert" not in sys.argv:
        send_telegram(msg)


if __name__ == "__main__":
    main()
