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
SECTORS = [  # naam, Yahoo tickers ("|" = pehla na mile to agla try), constituents file
    ("IT",           "^CNXIT|NIFTY_IT.NS",                     "ind_niftyitlist.csv"),
    ("Bank",         "^NSEBANK|NIFTY_BANK.NS",                 "ind_niftybanklist.csv"),
    ("Pvt Bank",     "NIFTY_PVT_BANK.NS|^NIFTYPVTBANK",        "ind_nifty_privatebanklist.csv"),
    ("PSU Bank",     "^CNXPSUBANK|NIFTY_PSU_BANK.NS",          "ind_niftypsubanklist.csv"),
    ("Fin Services", "NIFTY_FIN_SERVICE.NS|^CNXFIN",           "ind_niftyfinancelist.csv"),
    ("Auto",         "^CNXAUTO|NIFTY_AUTO.NS",                 "ind_niftyautolist.csv"),
    ("Pharma",       "^CNXPHARMA|NIFTY_PHARMA.NS",             "ind_niftypharmalist.csv"),
    ("Healthcare",   "NIFTY_HEALTHCARE.NS|^CNXHEALTH",         "ind_niftyhealthcarelist.csv"),
    ("FMCG",         "^CNXFMCG|NIFTY_FMCG.NS",                 "ind_niftyfmcglist.csv"),
    ("Metal",        "^CNXMETAL|NIFTY_METAL.NS",               "ind_niftymetallist.csv"),
    ("Realty",       "^CNXREALTY|NIFTY_REALTY.NS",             "ind_niftyrealtylist.csv"),
    ("Energy",       "^CNXENERGY|NIFTY_ENERGY.NS",             "ind_niftyenergylist.csv"),
    ("Oil & Gas",    "NIFTY_OIL_AND_GAS.NS|^CNXOILGAS",        "ind_niftyoilgaslist.csv"),
    ("Infra",        "^CNXINFRA|NIFTY_INFRA.NS",               "ind_niftyinfralist.csv"),
    ("PSE",          "^CNXPSE|NIFTY_PSE.NS",                   "ind_niftypselist.csv"),
    ("Media",        "^CNXMEDIA|NIFTY_MEDIA.NS",               "ind_niftymedialist.csv"),
    ("Consumption",  "^CNXCONSUM|NIFTY_CONSUMPTION.NS",        "ind_niftyconsumptionlist.csv"),
    ("Defence",      "NIFTY_IND_DEFENCE.NS|^CNXDEFENCE",       "ind_niftyindiadefence_list.csv"),
]
# NSE archive mein index ke naam (pehla jo mile)
NSE_NAMES = {
    "IT": ["Nifty IT"], "Bank": ["Nifty Bank"], "Pvt Bank": ["Nifty Private Bank"],
    "PSU Bank": ["Nifty PSU Bank"], "Fin Services": ["Nifty Financial Services"],
    "Auto": ["Nifty Auto"], "Pharma": ["Nifty Pharma"],
    "Healthcare": ["Nifty Healthcare Index", "Nifty Healthcare"], "FMCG": ["Nifty FMCG"],
    "Metal": ["Nifty Metal"], "Realty": ["Nifty Realty"], "Energy": ["Nifty Energy"],
    "Oil & Gas": ["Nifty Oil & Gas", "Nifty Oil and Gas"], "Infra": ["Nifty Infrastructure", "Nifty Infra"],
    "PSE": ["Nifty PSE"], "Media": ["Nifty Media"],
    "Consumption": ["Nifty India Consumption", "Nifty Consumption"],
    "Defence": ["Nifty India Defence", "Nifty Defence"],
}
RS_LEN, MOM_LEN, SMOOTH, TREND_LEN, PERF_LEN, TAIL = 10, 4, 3, 40, 13, 8
PHASE = {1: "LEADING", 2: "WEAKENING", 3: "LAGGING", 4: "IMPROVING", 0: "NO DATA"}
EMOJI = {1: "🟢", 2: "🟡", 3: "🔴", 4: "🔵", 0: "⚪"}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")


# ── Data ─────────────────────────────────────────────────────────────
def _close(df, tickers):
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        return df["Close"]
    return df[["Close"]].rename(columns={"Close": tickers[0]})


def fetch_prices(tickers, period="3y", chunk=60):
    """Stocks ko chhote batches mein laata hai (Yahoo zyada ek saath mein atakta hai)."""
    import yfinance as yf, time
    parts = []
    for i in range(0, len(tickers), chunk):
        part = tickers[i:i + chunk]
        for attempt in range(2):
            try:
                df = yf.download(part, period=period, interval="1d", auto_adjust=True,
                                 progress=False, group_by="column", threads=True)
                parts.append(_close(df, part))
                break
            except Exception as e:
                print(f"  batch fail ({e}), retry")
                time.sleep(5)
        time.sleep(2)
    out = pd.concat(parts, axis=1) if parts else pd.DataFrame()
    return out.loc[:, ~out.columns.duplicated()].dropna(how="all")


def fetch_index(cands, period="3y"):
    """Har candidate ticker try karo; jiska 1 saal+ data mile wahi lo."""
    import yfinance as yf, time
    for t in cands.split("|"):
        try:
            h = yf.Ticker(t).history(period=period, interval="1d", auto_adjust=True)
            c = h["Close"].dropna()
            if len(c) >= 260:
                c.index = c.index.tz_localize(None).normalize()
                return t, c
        except Exception as e:
            print(f"  {t}: {e}")
        time.sleep(1)
    return None, None


def synthetic_index(px):
    """Index ka data na mile to sector ke stocks ka equal-weight index bana lo."""
    rets = px.ffill().pct_change(fill_method=None)
    rets = rets.loc[:, px.notna().sum() >= 260]
    if rets.shape[1] < 3:
        return None
    return 1000 * (1 + rets.mean(axis=1).fillna(0)).cumprod()


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
        tk = "SEC::" + name
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
    for name, _, _ in SECTORS:
        tk = "SEC::" + name
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


# ── RRG universe (Strike-style chart: sab indices, daily + weekly) ──────────
UNIVERSE = {
    "Sectors": ["Nifty Bank", "Nifty Private Bank", "Nifty PSU Bank", "Nifty Financial Services",
                "Nifty Capital Markets", "Nifty Insurance", "Nifty IT", "Nifty Auto", "Nifty Pharma",
                "Nifty Healthcare Index", "Nifty Hospitals", "Nifty FMCG", "Nifty Consumer Durables",
                "Nifty Metal", "Nifty Realty", "Nifty Energy", "Nifty Oil & Gas", "Nifty Infrastructure",
                "Nifty Capital Goods", "Nifty Cement", "Nifty Chemicals", "Nifty PSE", "Nifty CPSE",
                "Nifty Media", "Nifty India Consumption", "Nifty India Defence", "Nifty India Railways PSU",
                "Nifty India Manufacturing", "Nifty MNC", "Nifty Commodities", "Nifty Housing",
                "Nifty India Tourism", "Nifty EV & New Age Automotive", "Nifty India Digital"],
    "Broad market": ["Nifty Next 50", "Nifty 100", "Nifty 200", "Nifty 500", "NIFTY LargeMidcap 250",
                     "Nifty Midcap 50", "NIFTY Midcap 100", "Nifty Midcap 150", "Nifty Midcap Select",
                     "Nifty MidSmallcap 400", "Nifty Smallcap 50", "NIFTY Smallcap 100",
                     "Nifty Smallcap 250", "Nifty Microcap 250"],
}
# timeframe: (smooth, rs_len, mom_len, kitne points rakhne hain)
TF_PARAMS = {"weekly": (SMOOTH, RS_LEN, MOM_LEN, 52), "daily": (5, 21, 5, 130)}


def short_name(n):
    s = n
    for pre in ("NIFTY ", "Nifty "):
        if s.startswith(pre):
            s = s[len(pre):]
    s = s.replace("India ", "").replace(" Index", "").replace("Financial Services", "Fin Services")
    return s.replace("EV & New Age Automotive", "EV & New Age Auto")


def rrg_universe(nse):
    """nse = wide DataFrame (date x NSE index name). Har timeframe ke liye RS-Ratio/Mom series."""
    import nse_data
    bcol = nse_data.pick(nse, "Nifty 50")
    if bcol is None:
        return None
    nse = nse[nse[bcol].notna()]
    out = {}
    for tf, (sm, rl, ml, keep) in TF_PARAMS.items():
        if tf == "weekly":
            df = nse.resample("W-FRI").last()
            real = pd.Series(nse.index, index=nse.index).resample("W-FRI").last()  # hafte ka asli last din
        else:
            df = nse
            real = pd.Series(nse.index, index=nse.index)
        df = df[df[bcol].notna()]
        b = df[bcol]
        idx = df.index[-keep:]
        labels = real.reindex(idx)
        series = []
        for grp, names in UNIVERSE.items():
            for n in names:
                col = nse_data.pick(df, n)
                if col is None:
                    continue
                c = df[col]
                rs = 100 * c / b
                rs_s = rs.ewm(span=sm, adjust=False, ignore_na=True).mean()
                ratio = 100 * rs_s / rs_s.rolling(rl).mean()
                mom = 100 * ratio / ratio.shift(ml)
                ratio, mom = ratio.reindex(idx), mom.reindex(idx)
                if ratio.notna().sum() < 2:
                    continue
                cl = c.reindex(idx)
                last = cl.dropna()
                chg = float((last.iloc[-1] / last.iloc[-2] - 1) * 100) if len(last) > 1 else None
                f = lambda v: None if pd.isna(v) else round(float(v), 2)
                series.append({"name": short_name(n), "full": n, "group": grp,
                               "rs": [f(v) for v in ratio], "mom": [f(v) for v in mom],
                               "price": f(last.iloc[-1]) if len(last) else None,
                               "chg": None if chg is None else round(chg, 2)})
        out[tf] = {"dates": [d.strftime("%d %b %y") for d in labels],
                   "bench": [None if pd.isna(v) else round(float(v), 2) for v in b.reindex(idx)],
                   "series": series}
    return out


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
    """Telegram pe bhejo; result (bina token ke) status mein wapas do."""
    import requests
    tok = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip().replace(" ", "")
    chat = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip().replace(" ", "")
    info = {"token_set": bool(tok), "chat_set": bool(chat),
            "token_shape_ok": bool(tok) and ":" in tok and tok.split(":")[0].isdigit()}
    if not tok or not chat:
        print("Telegram secrets nahi mile — alert skip.")
        return info
    try:
        me = requests.get(f"https://api.telegram.org/bot{tok}/getMe", timeout=20).json()
        info["getMe_ok"] = me.get("ok"); info["bot"] = (me.get("result") or {}).get("username")
        if not me.get("ok"):
            info["getMe_error"] = me.get("description")
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          data={"chat_id": chat, "text": text, "parse_mode": "Markdown",
                                "disable_web_page_preview": "true"}, timeout=30)
        if r.status_code != 200:  # Markdown me koi ajeeb character ho to plain text bhejo
            info["markdown_error"] = r.json().get("description")
            r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                              data={"chat_id": chat, "text": text.replace("*", "").replace("_", "")}, timeout=30)
        info["send_status"] = r.status_code
        if r.status_code != 200:
            info["send_error"] = r.json().get("description")
    except Exception as e:
        info["exception"] = str(e)[:200].replace(tok, "***")
    print("Telegram:", info)
    return info


# ── Main ─────────────────────────────────────────────────────────────
def main():
    demo = "--demo" in sys.argv
    status = {"indices": {}, "constituents": {}}
    nse = pd.DataFrame()
    if demo:
        daily, cons_map = demo_data()
        # demo NSE frame: sector series ko NSE naam do
        nse = pd.DataFrame({"Nifty 50": daily[BENCH]})
        for (name, _, _), ns in zip(SECTORS, UNIVERSE["Sectors"]):
            nse[ns] = daily["SEC::" + name]
    else:
        import yfinance as yf
        cons_map = {name: fetch_constituents(f) for name, _, f in SECTORS}
        status["constituents"] = {k: len(v) for k, v in cons_map.items()}
        all_stocks = sorted({s for v in cons_map.values() for s in v})
        print(f"Downloading {len(all_stocks)} stocks…")
        stocks = fetch_prices(all_stocks)
        stocks.index = pd.to_datetime(stocks.index).tz_localize(None).normalize()
        # 1st choice: NSE official index data; backup: Yahoo; last: equal-weight stocks
        try:
            import nse_data
            nse = nse_data.update_history()
        except Exception as e:
            print("NSE data fail:", e)
            nse = pd.DataFrame()
        status["nse_days"] = int(len(nse))
        status["nse_last"] = str(nse.index.max().date()) if len(nse) else None
        bcol = nse_data.pick(nse, "Nifty 50") if len(nse) else None
        if bcol and nse[bcol].notna().sum() >= 260:
            bench = nse[bcol].dropna(); status["benchmark"] = "NSE: " + bcol
        else:
            _, bench = fetch_index(BENCH); status["benchmark"] = "Yahoo ^NSEI"
        cols = {BENCH: bench}
        for name, cands, _ in SECTORS:
            used, c = None, None
            col = nse_data.pick(nse, *NSE_NAMES.get(name, [])) if len(nse) else None
            if col and nse[col].notna().sum() >= 260:
                c, used = nse[col].dropna(), "NSE: " + col
            if c is None:
                used, c = fetch_index(cands)
                used = f"Yahoo {used}" if used else None
            if c is None:
                syms = [x for x in cons_map.get(name, []) if x in stocks]
                c = synthetic_index(stocks[syms]) if syms else None
                used = "equal-weight stocks" if c is not None else None
            status["indices"][name] = used or "FAILED"
            print(f"  {name}: {status['indices'][name]}")
            if c is not None:
                cols["SEC::" + name] = c
        idx_df = pd.DataFrame(cols)
        daily = idx_df.join(stocks, how="left")
        daily = daily[daily[BENCH].notna()]
    res = analyse(daily, cons_map)
    try:
        rrg_all = rrg_universe(nse) if len(nse) else None
    except Exception as e:
        print("RRG universe fail:", e); rrg_all = None
    status["rrg_indices"] = len(rrg_all["weekly"]["series"]) if rrg_all else 0
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "data.json"), "w") as f:
        json.dump(res, f, indent=1)
    status["sectors_ok"] = len(res["sectors"])
    with open(os.path.join(OUT, "status.json"), "w") as f:
        json.dump(status, f, indent=1)
    tpl = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard_template.html"), encoding="utf-8").read()
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(tpl.replace("/*__DATA__*/null", json.dumps(res)).replace("/*__RRG__*/null", json.dumps(rrg_all, separators=(",", ":"))))
    if rrg_all:
        with open(os.path.join(OUT, "rrg.json"), "w") as f:
            json.dump(rrg_all, f, separators=(",", ":"))
    msg = alert_text(res, os.environ.get("DASHBOARD_URL", ""))
    print(msg)
    if not demo and os.environ.get("SEND_ALERT") == "1":
        status["telegram"] = send_telegram(msg)
        with open(os.path.join(OUT, "status.json"), "w") as f:
            json.dump(status, f, indent=1)


if __name__ == "__main__":
    main()
