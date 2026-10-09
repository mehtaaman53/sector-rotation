"""
NSE official index data — nsearchives.nseindia.com ki daily "ind_close_all" file se.
Har trading day ki ek file mein NSE ke saare (~167) indices ka close hota hai.
History data/nse_indices.csv mein save hoti hai; har run pe sirf naye din jodte hain.
"""
import io, os, time, datetime as dt
import pandas as pd
import requests

HIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "nse_indices.csv")
URL = "https://nsearchives.nseindia.com/content/indices/ind_close_all_{d:%d%m%Y}.csv"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
START_YEARS = 3


def _fetch_day(sess, d):
    try:
        r = sess.get(URL.format(d=d), timeout=20)
    except Exception:
        return None
    if r.status_code != 200 or "Index Name" not in r.text[:300]:
        return None
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = [c.strip() for c in df.columns]
    df = df[["Index Name", "Closing Index Value"]].rename(columns={"Index Name": "index", "Closing Index Value": "close"})
    df["index"] = df["index"].astype(str).str.strip()
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["date"] = pd.Timestamp(d)
    return df.dropna()


def update_history(max_days=None):
    """Purani history load karo, missing din NSE se laao, save karo. Wide DataFrame (date x index) return."""
    os.makedirs(os.path.dirname(HIST), exist_ok=True)
    if os.path.exists(HIST):
        hist = pd.read_csv(HIST, parse_dates=["date"])
        start = hist["date"].max().date() + dt.timedelta(days=1)
    else:
        hist = pd.DataFrame(columns=["date", "index", "close"])
        start = dt.date.today() - dt.timedelta(days=365 * START_YEARS)
    today = dt.date.today()
    days = [start + dt.timedelta(days=i) for i in range((today - start).days + 1)]
    days = [d for d in days if d.weekday() < 5]
    if max_days:
        days = days[:max_days]
    print(f"NSE: {len(days)} din check karne hain (from {start})")
    sess = requests.Session(); sess.headers.update(UA)
    new, miss, fails_in_row = [], 0, 0
    for i, d in enumerate(days):
        df = _fetch_day(sess, d)
        if df is None:
            miss += 1
        else:
            new.append(df)
        time.sleep(0.25)
        if (i + 1) % 100 == 0:
            print(f"  {i + 1}/{len(days)} done, {len(new)} trading days mile")
    print(f"NSE: {len(new)} naye trading days, {miss} chhutti/missing")
    if new:
        hist = pd.concat([hist] + new, ignore_index=True)
        hist = hist.drop_duplicates(["date", "index"], keep="last").sort_values(["date", "index"])
        hist.to_csv(HIST, index=False, date_format="%Y-%m-%d")
    wide = hist.pivot_table(index="date", columns="index", values="close", aggfunc="last").sort_index()
    wide.index = pd.to_datetime(wide.index)
    return wide


def pick(wide, *names):
    """Index naam case/space ignore karke dhundo."""
    norm = {c.lower().replace(" ", ""): c for c in wide.columns}
    for n in names:
        c = norm.get(n.lower().replace(" ", ""))
        if c is not None:
            return c
    return None


if __name__ == "__main__":
    w = update_history()
    print(w.shape, w.index.min(), w.index.max())
    print(sorted(w.columns))
