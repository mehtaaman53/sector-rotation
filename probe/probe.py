"""Test: kaun sa data source GitHub se chalta hai. Asli system ko nahi chhoota."""
import json, time, datetime as dt, requests
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"}
out = {}

def rec(k, **v):
    out[k] = v; print(k, v)

# 1) niftyindices.com historical (official index data)
try:
    s = requests.Session(); s.headers.update(UA)
    s.get("https://www.niftyindices.com/reports/historical-data", timeout=20)
    names = ["NIFTY 50", "NIFTY IT", "NIFTY HEALTHCARE INDEX", "NIFTY INDIA DEFENCE", "NIFTY MIDCAP 150"]
    res = {}
    for n in names:
        body = {"cinfo": json.dumps({"name": n, "startDate": "01-Jan-2026", "endDate": dt.date.today().strftime("%d-%b-%Y"), "indexName": n}).replace('"', "'")}
        r = s.post("https://www.niftyindices.com/Backpage.aspx/getHistoricaldatatabletoString", json=body,
                   headers={"Content-Type": "application/json; charset=UTF-8", "X-Requested-With": "XMLHttpRequest",
                            "Origin": "https://www.niftyindices.com", "Referer": "https://www.niftyindices.com/reports/historical-data"}, timeout=30)
        try:
            rows = json.loads(r.json()["d"])
            res[n] = {"status": r.status_code, "rows": len(rows), "first": rows[-1] if rows else None, "last": rows[0] if rows else None}
        except Exception as e:
            res[n] = {"status": r.status_code, "err": str(e)[:80], "text": r.text[:150]}
        time.sleep(1)
    rec("niftyindices_historical", **res)
except Exception as e:
    rec("niftyindices_historical", err=str(e)[:200])

# 2) NSE archives: all-indices daily close CSV
try:
    found = None
    for back in range(0, 7):
        d = dt.date.today() - dt.timedelta(days=back)
        url = f"https://nsearchives.nseindia.com/content/indices/ind_close_all_{d:%d%m%Y}.csv"
        r = requests.get(url, headers=UA, timeout=20)
        if r.status_code == 200 and "Index Name" in r.text[:300]:
            lines = r.text.strip().splitlines()
            found = {"date": str(d), "indices": len(lines) - 1, "header": lines[0][:200],
                     "sample": [l[:120] for l in lines[1:4]],
                     "has_defence": any("Defence" in l for l in lines)}
            break
    rec("nse_archive_daily", **(found or {"status": "not found last 7 days"}))
except Exception as e:
    rec("nse_archive_daily", err=str(e)[:200])

# 3) nseindia.com API (cookie based)
try:
    s = requests.Session(); s.headers.update(UA)
    s.get("https://www.nseindia.com/", timeout=20)
    t = dt.date.today()
    r = s.get(f"https://www.nseindia.com/api/historical/indicesHistory?indexType=NIFTY%20IT&from={(t-dt.timedelta(days=30)):%d-%m-%Y}&to={t:%d-%m-%Y}", timeout=20)
    rec("nse_api", status=r.status_code, text=r.text[:200])
except Exception as e:
    rec("nse_api", err=str(e)[:200])

# 4) investing.com
try:
    r = requests.get("https://www.investing.com/indices/cnx-it-historical-data", headers=UA, timeout=20)
    rec("investing_com", status=r.status_code, cloudflare=("cf-" in str(r.headers).lower() or "Just a moment" in r.text[:2000]), size=len(r.text))
except Exception as e:
    rec("investing_com", err=str(e)[:200])

json.dump(out, open("probe/result.json", "w"), indent=1, default=str)
