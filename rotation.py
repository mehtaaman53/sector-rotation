"""
THE TRADE TRIBE — Sector Rotation Engine (v2: Sector → Industry → Theme)

Groups: data/groups.csv (scanthecharts se liya, saaf kiya hua — 1,815 stocks, mcap ₹400 cr+).
Har group EQUAL-WEIGHT hai (koi heavyweight nahi).

Har run pe:
  1. Saare stocks ka 3 saal ka daily price (Yahoo) + NSE official benchmarks
  2. Har sector / industry / theme ka equal-weight index
  3. Returns (1D…YTD), rank + rank change, breadth, 20D highs/lows
  4. RRG — WEEKLY aur MONTHLY (group vs Nifty 500)
  5. Har stock: return, 52W high se doori, RS (apne benchmark ke against)
  6. docs/index.html dashboard (scanthecharts jaisa) + Telegram alert

Benchmarks:
  Group → NIFTY 500
  Stock → Large (rank 1–100) NIFTY 50 | Mid (101–250) MIDCAP 150 | Small + Micro → SMALLCAP 250

Test: python rotation.py --demo   (bina internet, nakli data)
"""
import json, os, sys, time, datetime as dt
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "docs")
GROUPS_CSV = os.path.join(ROOT, "data", "groups.csv")

BENCH_NAMES = {  # NSE archive naam → apna naam
    "NIFTY 50": ["Nifty 50"],
    "NIFTY 500": ["Nifty 500"],
    "NIFTY MIDCAP 150": ["Nifty Midcap 150"],
    "NIFTY SMALLCAP 250": ["Nifty Smallcap 250"],
}
BENCH_YAHOO = {"NIFTY 50": "^NSEI", "NIFTY 500": "^CRSLDX",
               "NIFTY MIDCAP 150": "NIFTYMIDCAP150.NS", "NIFTY SMALLCAP 250": "NIFTYSMLCAP250.NS"}
GROUP_BENCH = "NIFTY 500"

# timeframe → kitne trading din
TF = {"1D": 1, "1W": 5, "1M": 21, "3M": 63, "6M": 126, "1Y": 252}
# RRG: (smoothing, RS-Ratio length, Momentum lookback, kitne points rakhne)
RRG_P = {"daily": (5, 21, 5, 12), "weekly": (3, 10, 4, 12), "monthly": (2, 6, 3, 12)}  # last 12 points (tail max 10)
SMALL_GROUP = 3          # isse kam/barabar stocks = "small group" (default chhupa, toggle se dikhe)
MAX_DAILY_MOVE = 0.40    # ek din mein 40%+ move = data galti maan ke clip


# ── Data ─────────────────────────────────────────────────────────────────
def load_groups():
    g = pd.read_csv(GROUPS_CSV)
    g["themes"] = g["themes"].fillna("")
    return g


def yahoo_ticker(sym):
    return sym + ".NS"


def fetch_prices(syms, period="3y", chunk=60):
    """Stocks ko batches mein Yahoo se laao. Return: close & volume (date x symbol)."""
    import yfinance as yf
    closes, vols = [], []
    for i in range(0, len(syms), chunk):
        part = syms[i:i + chunk]
        tick = [yahoo_ticker(s) for s in part]
        for attempt in range(3):
            try:
                df = yf.download(tick, period=period, interval="1d", auto_adjust=True,
                                 progress=False, group_by="column", threads=True)
                if df is None or df.empty:
                    raise ValueError("empty")
                c = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df[["Close"]].set_axis(tick, axis=1)
                v = df["Volume"] if isinstance(df.columns, pd.MultiIndex) else df[["Volume"]].set_axis(tick, axis=1)
                closes.append(c); vols.append(v)
                break
            except Exception as e:
                print(f"  batch {i // chunk + 1} fail ({e}), retry {attempt + 1}")
                time.sleep(5 * (attempt + 1))
        time.sleep(1.5)
        print(f"  prices: {min(i + chunk, len(syms))}/{len(syms)}")
    close = pd.concat(closes, axis=1) if closes else pd.DataFrame()
    vol = pd.concat(vols, axis=1) if vols else pd.DataFrame()
    for d in (close, vol):
        d.columns = [c.replace(".NS", "") for c in d.columns]
        d.index = pd.to_datetime(d.index).tz_localize(None).normalize()
    close = close.loc[:, ~close.columns.duplicated()]
    vol = vol.loc[:, ~vol.columns.duplicated()]
    return close.sort_index(), vol.sort_index()


def fetch_benchmarks():
    """Pehle NSE official (data/nse_indices.csv), na mile to Yahoo."""
    out, src = {}, {}
    try:
        import nse_data
        nse = nse_data.update_history()
        for k, names in BENCH_NAMES.items():
            col = nse_data.pick(nse, *names)
            if col is not None and nse[col].notna().sum() > 260:
                out[k] = nse[col].dropna(); src[k] = "NSE: " + col
    except Exception as e:
        print("NSE data fail:", e)
    missing = [k for k in BENCH_NAMES if k not in out]
    if missing:
        import yfinance as yf
        for k in missing:
            try:
                h = yf.Ticker(BENCH_YAHOO[k]).history(period="3y", interval="1d", auto_adjust=True)["Close"].dropna()
                h.index = h.index.tz_localize(None).normalize()
                if len(h) > 260:
                    out[k] = h; src[k] = "Yahoo " + BENCH_YAHOO[k]
            except Exception as e:
                print(f"  bench {k} fail: {e}")
    return pd.DataFrame(out).sort_index(), src


def demo_data(groups):
    """Nakli data — sirf test ke liye."""
    rng = np.random.default_rng(11)
    idx = pd.bdate_range(end=pd.Timestamp("2026-11-13"), periods=760)
    n = len(idx)
    mkt = np.cumsum(rng.normal(0.0004, 0.009, n))
    bench = pd.DataFrame({"NIFTY 500": 20000 * np.exp(mkt)}, index=idx)
    bench["NIFTY 50"] = 24000 * np.exp(mkt * 0.9 + np.cumsum(rng.normal(0, 0.002, n)))
    bench["NIFTY MIDCAP 150"] = 18000 * np.exp(mkt * 1.2 + np.cumsum(rng.normal(0, 0.003, n)))
    bench["NIFTY SMALLCAP 250"] = 15000 * np.exp(mkt * 1.4 + np.cumsum(rng.normal(0, 0.004, n)))
    themes = sorted({t for s in groups["themes"] for t in s.split("|") if t})
    inds = sorted(groups["industry"].unique())
    drift = {}
    for k, name in enumerate(inds + themes):
        ph = rng.uniform(0, 6.28); sp = rng.uniform(1.5, 5)
        drift[name] = np.sin(np.linspace(0, sp, n) + ph) * rng.uniform(0.0004, 0.0018)
    close, vol = {}, {}
    for _, r in groups.iterrows():
        d = drift[r["industry"]].copy()
        for t in [t for t in r["themes"].split("|") if t]:
            d += drift[t] * 0.6
        ret = mkt[1:] - mkt[:-1]
        steps = np.r_[0, ret] * rng.uniform(0.7, 1.4) + d + rng.normal(0, 0.017, n)
        start = int(rng.integers(0, 120)) if rng.random() < 0.08 else 0
        p = 100 * np.exp(np.cumsum(steps))
        p[:start] = np.nan
        close[r["symbol"]] = p
        vol[r["symbol"]] = rng.lognormal(11, 1, n) * (1 + (rng.random(n) < 0.03) * 2)
    return pd.DataFrame(close, index=idx), pd.DataFrame(vol, index=idx), bench


# ── Calculations ─────────────────────────────────────────────────────────
def clean_returns(close):
    r = close.pct_change(fill_method=None)
    return r.where(r.abs() <= MAX_DAILY_MOVE)


def ew_index(rets, members):
    """Equal-weight index: har din members ke return ka average."""
    cols = [m for m in members if m in rets.columns]
    if not cols:
        return None
    r = rets[cols].mean(axis=1, skipna=True)
    cnt = rets[cols].notna().sum(axis=1)
    r = r.where(cnt > 0, 0.0).fillna(0.0)
    return 100 * (1 + r).cumprod()


def ret_over(s, n):
    s = s.dropna()
    if len(s) <= n:
        return None
    return float(s.iloc[-1] / s.iloc[-1 - n] - 1)


def ytd_ret(s):
    s = s.dropna()
    if s.empty:
        return None
    prev = s[s.index < pd.Timestamp(s.index[-1].year, 1, 1)]
    if prev.empty:
        return None
    return float(s.iloc[-1] / prev.iloc[-1] - 1)


def quad(r, m):
    if r is None or m is None or np.isnan(r) or np.isnan(m):
        return 0
    return (1 if m >= 100 else 2) if r >= 100 else (4 if m >= 100 else 3)


def rrg_series(idx_s, bench_s, tf):
    sm, rl, ml, keep = RRG_P[tf]
    df = pd.concat([idx_s, bench_s], axis=1, keys=["g", "b"]).dropna()
    if tf != "daily":
        df = df.resample("W-FRI" if tf == "weekly" else "ME").last().dropna()
    rs = 100 * df["g"] / df["b"]
    rs_s = rs.ewm(span=sm, adjust=False).mean()
    ratio = 100 * rs_s / rs_s.rolling(rl).mean()
    mom = 100 * ratio / ratio.shift(ml)
    ok = ratio.notna() & mom.notna()
    ratio, mom = ratio[ok].iloc[-keep:], mom[ok].iloc[-keep:]
    return ratio, mom


def r2(x, k=2):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), k)


def pct(x):
    return None if x is None else round(100 * x, 2)


def analyse(groups, close, vol, bench):
    close = close.loc[close.index >= bench.index.min()].copy()
    close = close.reindex(close.index.union(bench.index)).sort_index()
    close = close.loc[close.index <= bench.index.max()]
    close = close.ffill(limit=5)
    rets = clean_returns(close)
    last_day = bench[GROUP_BENCH].dropna().index[-1]
    close, rets = close.loc[:last_day], rets.loc[:last_day]
    bench = bench.ffill().loc[:last_day]

    have = [s for s in groups["symbol"] if s in close.columns and close[s].notna().sum() > 30]
    g = groups[groups["symbol"].isin(have)].copy()
    print(f"Price mila: {len(have)} / {len(groups)} stocks")

    # ── stock level
    px = close[have]
    sma20, sma50, sma200 = px.rolling(20).mean(), px.rolling(50).mean(), px.rolling(200).mean()
    hi252 = px.rolling(252, min_periods=60).max()
    hi20 = px.rolling(20).max(); lo20 = px.rolling(20).min()
    lastp = px.iloc[-1]
    stock_ret = {}
    for k, n in TF.items():
        stock_ret[k] = (px.iloc[-1] / px.shift(n).iloc[-1] - 1)
    ytd_base = px[px.index < pd.Timestamp(last_day.year, 1, 1)].iloc[-1] if (px.index < pd.Timestamp(last_day.year, 1, 1)).any() else None
    stock_ret["YTD"] = (px.iloc[-1] / ytd_base - 1) if ytd_base is not None else pd.Series(np.nan, index=px.columns)
    # 5 din pehle ki position (rank change ke liye)
    stock_ret_prev = {k: (px.iloc[-6] / px.shift(n).iloc[-6] - 1) for k, n in TF.items()}
    stock_ret_prev["YTD"] = (px.iloc[-6] / ytd_base - 1) if ytd_base is not None else pd.Series(np.nan, index=px.columns)
    h20_prev = (px.iloc[-6] >= px.rolling(20).max().iloc[-6] * 0.9999)
    # RS: 3M + 6M return apne benchmark ke against → percentile 1–99
    rel = {}
    for _, r in g.iterrows():
        b = bench[r["benchmark"]] if r["benchmark"] in bench else bench[GROUP_BENCH]
        p = px[r["symbol"]]
        parts = []
        for n, w in ((63, 0.4), (126, 0.4), (21, 0.2)):
            a, bb = ret_over(p, n), ret_over(b, n)
            if a is not None and bb is not None:
                parts.append(w * (a - bb))
        rel[r["symbol"]] = sum(parts) if parts else np.nan
    rel = pd.Series(rel)
    rs_rating = (rel.rank(pct=True) * 98 + 1).round()
    is20h = (px.iloc[-1] >= hi20.iloc[-1] * 0.9999)
    is20l = (px.iloc[-1] <= lo20.iloc[-1] * 1.0001)
    above = {k: (px.iloc[-1] > s.iloc[-1]) for k, s in (("20", sma20), ("50", sma50), ("200", sma200))}
    from_hi = (px.iloc[-1] / hi252.iloc[-1] - 1)
    vratio = None
    if vol is not None and not vol.empty:
        vv = vol.reindex(columns=have).loc[:last_day]
        vratio = vv.rolling(5).mean().iloc[-1] / vv.rolling(50).mean().iloc[-1]

    stocks = []
    for _, r in g.iterrows():
        s = r["symbol"]
        stocks.append({
            "s": s, "sec": r["sector"], "ind": r["industry"],
            "th": [t for t in r["themes"].split("|") if t],
            "cap": r["cap_bucket"], "bm": r["benchmark"], "mc": r2(r["mcap_cr"], 0),
            "liq": r["liquidity_tag"].split(" ")[0], "fno": int(r["fno"]) if not pd.isna(r["fno"]) else 0,
            "p": r2(lastp[s]), "r": {k: pct(None if pd.isna(v[s]) else v[s]) for k, v in stock_ret.items()},
            "hi": pct(None if pd.isna(from_hi[s]) else from_hi[s]),
            "rs": None if pd.isna(rs_rating.get(s)) else int(rs_rating[s]),
            "h20": bool(is20h[s]), "l20": bool(is20l[s]),
            "a50": bool(above["50"][s]), "a200": bool(above["200"][s]),
            "vr": None if vratio is None or pd.isna(vratio.get(s)) else r2(vratio[s], 1),
        })

    # ── group level
    def members(kind):
        m = {}
        for _, r in g.iterrows():
            keys = [t for t in r["themes"].split("|") if t] if kind == "theme" else [r[kind]]
            for k in keys:
                m.setdefault(k, []).append(r["symbol"])
        return m

    ewm = ew_index(rets, have)               # equal-weight market (saare stocks barabar)
    bench = bench.copy(); bench["EW MARKET"] = ewm.reindex(bench.index)
    bench_ret = {k: ret_over(bench[GROUP_BENCH], n) for k, n in TF.items()}
    bench_ret["YTD"] = ytd_ret(bench[GROUP_BENCH])
    BK = {"ew": "EW MARKET", "n50": "NIFTY 50", "n500": "NIFTY 500", "mid150": "NIFTY MIDCAP 150", "sm250": "NIFTY SMALLCAP 250"}
    BK = {k: v for k, v in BK.items() if v in bench.columns and bench[v].notna().sum() > 260}
    BR = {}
    for bk, bcol in BK.items():
        BR[bk] = {k: ret_over(bench[bcol], n) for k, n in TF.items()}
        BR[bk]["YTD"] = ytd_ret(bench[bcol])
    MR = BR["ew"]                                  # market = equal-weight (scanthecharts jaisa)
    ewp = ewm.iloc[:-5]
    MRP = {k: ret_over(ewp, n) for k, n in TF.items()}; MRP["YTD"] = ytd_ret(ewp)
    out_groups = {}
    for kind in ("sector", "industry", "theme"):
        rows = []
        for name, mem in members(kind).items():
            idx_s = ew_index(rets, mem)
            if idx_s is None:
                continue
            row = {"name": name, "n": len(mem), "m": mem, "small": len(mem) <= SMALL_GROUP}
            # returns + median member return
            row["ret"] = {k: pct(ret_over(idx_s, n)) for k, n in TF.items()}
            row["ret"]["YTD"] = pct(ytd_ret(idx_s))
            row["med"] = {k: pct(float(np.nanmedian(stock_ret[k][mem].values))) if stock_ret[k][mem].notna().any() else None
                          for k in list(TF) + ["YTD"]}
            # vs benchmark = group ka MEDIAN return − benchmark return (scanthecharts jaisa)
            row["rel"] = {bk: {k: None if row["med"][k] is None or BR[bk][k] is None else round(row["med"][k] - 100 * BR[bk][k], 2)
                               for k in row["med"]} for bk in BK}
            # rank change ke liye 5 din pehle ka return
            prev_idx = idx_s.iloc[:-5]
            row["ret_prev"] = {k: pct(ret_over(prev_idx, n)) for k, n in TF.items()}
            row["ret_prev"]["YTD"] = pct(ytd_ret(prev_idx))
            # breadth
            row["b20"] = round(100 * float(above["20"][mem].mean()), 0)
            row["b50"] = round(100 * float(above["50"][mem].mean()), 0)
            row["b200"] = round(100 * float(above["200"][mem].mean()), 0)
            row["nh"] = round(100 * float((from_hi[mem] >= -0.10).mean()), 0)
            row["h20"] = int(is20h[mem].sum()); row["l20"] = int(is20l[mem].sum()); row["h20p"] = int(h20_prev[mem].sum())
            # quality tags
            n = len(mem)
            row["size"] = "Single" if n == 1 else "Chhota" if n <= 3 else "Medium" if n <= 9 else "Broad"
            caps = g.set_index("symbol").loc[mem, "cap_bucket"].value_counts()
            row["capmix"] = {c: int(caps.get(c, 0)) for c in ("Large", "Mid", "Small", "Micro")}
            row["micro"] = round(caps.get("Micro", 0) / n, 2)
            liqs = g.set_index("symbol").loc[mem, "median30_turnover_cr"]
            row["liq"] = r2(float(liqs.median()), 1)
            if kind != "sector":
                row["sec"] = g[g["symbol"].isin(mem)]["sector"].mode().iloc[0]
            # RRG weekly + monthly
            row["rrg"] = {}
            for bk, bcol in BK.items():
                row["rrg"][bk] = {}
                for tf in RRG_P:
                    ratio, mom = rrg_series(idx_s, bench[bcol], tf)
                    if len(ratio) >= 2:
                        row["rrg"][bk][tf] = {"x": [r2(v, 1) for v in ratio], "y": [r2(v, 1) for v in mom],
                                              "q": quad(ratio.iloc[-1], mom.iloc[-1]), "pq": quad(ratio.iloc[-2], mom.iloc[-2])}
            # chhota chart: 1 saal ka index vs Nifty 500 (weekly)
            w = pd.concat([idx_s] + [bench[c] for c in BK.values()], axis=1, keys=["g"] + list(BK)).dropna().resample("W-FRI").last().iloc[-53:]
            row["spark"] = {c: [r2(100 * v / w[c].iloc[0], 1) for v in w[c]] for c in w.columns}
            rows.append(row)
        # ── scanthecharts jaisa rank: har timeframe ka score =
        #    (median return − market return) + participation (% stocks jo market ko hara rahe) + 20D highs %
        #    teeno ka percentile average → 0–100 score → rank
        for key in ("cur", "prev"):
            for k in list(TF) + ["YTD"]:
                vals = []
                for r in rows:
                    m = r["m"]
                    if key == "cur":
                        sr = stock_ret[k][m]; mk = MR[k]
                    else:
                        sr = stock_ret_prev[k][m]; mk = MRP[k]
                    if sr.notna().sum() == 0 or mk is None:
                        vals.append(None); continue
                    vals.append((float(np.nanmedian(sr)) - mk, float((sr > mk).mean()), float(r["h20"] / len(m)) if key == "cur" else float(r["h20p"] / len(m))))
                ok = [v for v in vals if v is not None]
                if not ok:
                    continue
                arr = np.array(ok)
                pr = np.zeros(len(ok))
                for c in range(3):
                    pr += pd.Series(arr[:, c]).rank(pct=True).values
                score = iter(np.round(100 * pr / 3, 1))
                for r, v in zip(rows, vals):
                    sc = next(score) if v is not None else None
                    if key == "cur":
                        r.setdefault("score", {})[k] = None if sc is None else float(sc)
                        if v is not None:
                            r.setdefault("part", {})[k] = round(100 * v[1], 0)
                    else:
                        r.setdefault("_ps", {})[k] = None if sc is None else float(sc)
        for k in list(TF) + ["YTD"]:
            # rank sirf normal groups mein (small groups ka rank nahi — scanthecharts jaisa)
            cur = sorted([r for r in rows if not r["small"] and r.get("score", {}).get(k) is not None], key=lambda r: -r["score"][k])
            prv = sorted([r for r in rows if not r["small"] and r.get("_ps", {}).get(k) is not None], key=lambda r: -r["_ps"][k])
            pr = {r["name"]: i + 1 for i, r in enumerate(prv)}
            for i, r in enumerate(cur):
                r.setdefault("rank", {})[k] = i + 1
                r.setdefault("rchg", {})[k] = (pr[r["name"]] - (i + 1)) if r["name"] in pr else None
        for r in rows:
            r.pop("_ps", None); r.pop("h20p", None); r.pop("ret_prev", None)
        out_groups[kind] = rows
        continue
        # (purana) rank per timeframe (equal-weight return) + rank change
        for k in list(TF) + ["YTD"]:
            cur = sorted([r for r in rows if r["ret"][k] is not None], key=lambda r: -r["ret"][k])
            prv = sorted([r for r in rows if r["ret_prev"][k] is not None], key=lambda r: -r["ret_prev"][k])
            pr = {r["name"]: i + 1 for i, r in enumerate(prv)}
            for i, r in enumerate(cur):
                r.setdefault("rank", {})[k] = i + 1
                r.setdefault("rchg", {})[k] = (pr[r["name"]] - (i + 1)) if r["name"] in pr else None
        for r in rows:
            r.pop("ret_prev", None)
        out_groups[kind] = rows

    # RRG dates
    rrg_dates = {}
    for tf in RRG_P:
        real = pd.Series(bench.index, index=bench.index)
        if tf != "daily":
            real = real.resample("W-FRI" if tf == "weekly" else "ME").last().dropna()
        rrg_dates[tf] = [d.strftime("%d %b %y") for d in real.iloc[-RRG_P[tf][3]:]]
    bm = {k: {"ret": {kk: pct(ret_over(bench[k], n)) for kk, n in TF.items()}} for k in bench.columns}
    for k in bm:
        bm[k]["ret"]["YTD"] = pct(ytd_ret(bench[k]))
    return {
        "asof": last_day.strftime("%d %b %Y"),
        "generated": dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).strftime("%d %b %Y, %I:%M %p IST"),
        "universe": len(groups), "priced": len(have),
        "bench": bm, "bkeys": BK, "rrg_dates": rrg_dates, "groups": out_groups, "stocks": stocks,
    }


# ── Telegram ─────────────────────────────────────────────────────────────
PHASE = {1: "LEADING", 2: "WEAKENING", 3: "LAGGING", 4: "IMPROVING", 0: "—"}
EMOJI = {1: "🟢", 2: "🟡", 3: "🔴", 4: "🔵", 0: "⚪"}


def alert_text(res, url=""):
    L = [f"📊 *Trade Tribe — Sector Rotation*", f"_Data: {res['asof']}_", ""]
    for kind, label, top in (("sector", "Sectors", 99), ("industry", "Industries", 8), ("theme", "Themes", 8)):
        rows = [r for r in res["groups"][kind] if not r["small"] and "weekly" in r["rrg"].get("ew", {})]
        moved = [r for r in rows if r["rrg"]["ew"]["weekly"]["q"] != r["rrg"]["ew"]["weekly"]["pq"] and r["rrg"]["ew"]["weekly"]["q"] in (1, 4)]
        lead = sorted([r for r in rows if r["rrg"]["ew"]["weekly"]["q"] == 1], key=lambda r: -(r["rel"]["ew"]["1M"] or -99))[:top]
        L.append(f"*{label} — weekly RRG*")
        if moved:
            L += [f"{EMOJI[r['rrg']['ew']['weekly']['q']]} {r['name']} → {PHASE[r['rrg']['ew']['weekly']['q']]}" for r in moved[:top]]
        if lead:
            L.append("Leading: " + ", ".join(f"{r['name']} ({r['rel']['ew']['1M']:+.1f}%)" for r in lead if r["rel"]["ew"]["1M"] is not None))
        L.append("")
    L.append("_% = 1 mahine ka median return, Equal-weight market (saare stocks ka average) se upar/neeche_")
    if url:
        L += ["", f"Dashboard: {url}"]
    return "\n".join(L)


def send_telegram(text):
    import requests
    tok = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not tok or not chat:
        print("Telegram secrets nahi mile — alert skip."); return {"sent": False}
    try:
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          data={"chat_id": chat, "text": text, "parse_mode": "Markdown",
                                "disable_web_page_preview": "true"}, timeout=30)
        if r.status_code != 200:
            r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                              data={"chat_id": chat, "text": text.replace("*", "").replace("_", "")}, timeout=30)
        return {"sent": r.status_code == 200, "status": r.status_code}
    except Exception as e:
        return {"sent": False, "error": str(e)[:200].replace(tok, "***")}


# ── Main ─────────────────────────────────────────────────────────────────
def main():
    demo = "--demo" in sys.argv
    groups = load_groups()
    status = {"mode": "demo" if demo else "live"}
    if demo:
        close, vol, bench = demo_data(groups)
        status["bench_src"] = "demo"
    else:
        bench, status["bench_src"] = fetch_benchmarks()
        syms = groups["symbol"].tolist()
        print(f"Downloading {len(syms)} stocks…")
        close, vol = fetch_prices(syms)
    missing = sorted(set(groups["symbol"]) - set(close.columns[close.notna().sum() > 30]))
    status["missing_prices"] = missing
    res = analyse(groups, close, vol, bench)
    status.update({"asof": res["asof"], "priced": res["priced"], "universe": res["universe"],
                   "groups": {k: len(v) for k, v in res["groups"].items()}})
    os.makedirs(OUT, exist_ok=True)
    payload = json.dumps(res, separators=(",", ":"), allow_nan=False)
    with open(os.path.join(OUT, "data.json"), "w") as f:
        f.write(payload)
    tpl = open(os.path.join(ROOT, "dashboard_template.html"), encoding="utf-8").read()
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(tpl.replace("/*__DATA__*/null", payload))
    msg = alert_text(res, os.environ.get("DASHBOARD_URL", ""))
    print(msg)
    if not demo and os.environ.get("SEND_ALERT") == "1":
        status["telegram"] = send_telegram(msg)
    with open(os.path.join(OUT, "status.json"), "w") as f:
        json.dump(status, f, indent=1)
    print("Done:", {k: v for k, v in status.items() if k != "missing_prices"}, "| missing:", len(missing))


if __name__ == "__main__":
    main()
