# 📊 Trade Tribe — Sector Rotation (Sector → Industry → Theme)

Live dashboard: `https://<aapka-github-naam>.github.io/sector-rotation/`

**Roz shaam ~7:45 (Mon–Fri)** dashboard update hota hai, **Shanivar subah ~8:45** Telegram alert aata hai.

## Groups kahan se aaye
`data/groups.csv` — scanthecharts.com ki sector / industry / theme mapping (13 Nov 2026 snapshot), saaf karke:
- Unclassified, ₹400 cr se chhote, aur zero-turnover stocks hata diye → **1,815 stocks**
- 22 sectors · 165 industries · 101 themes (blanket aur galat themes theek kiye)
- Apne groups jode: **PSU**, **Railway PSU**, **Hydro Power**, **Power Trading**, **MNC Pharma**

Group badalna ho to bas `data/groups.csv` edit karo (themes `|` se alag). Agla run naye groups use karega.

## Kya nikalta hai
- Har group ka **equal-weight index** (har stock ka barabar wazan)
- Returns 1D / 1W / 1M / 3M / 6M / 1Y / YTD, **rank + rank change** (5 din pehle se)
- Breadth: 20/50/200 DMA ke upar %, 52W high ke 10% andar %, 20-din highs/lows
- **RRG — Daily, Weekly, Monthly**, kisi bhi benchmark ke against
- Har stock: return, 52W high se doori, **RS** (1–99, apne benchmark ke against), volume ratio
- Group quality: size, liquidity, cap mix, "Mostly Micro" flag

## Compare kaise hota hai (scanthecharts jaisa)
Dashboard mein upar dropdown se benchmark chuno — RRG, "vs" column, chart, D/W/M phase sab usi se badalte hain:
- **Equal-weight market** (default) — saare ~1,800 stocks ka seedha average, har stock ka barabar hissa
- Nifty 50 · Nifty 500 · Nifty Midcap 150 · Nifty Smallcap 250

**Rank** (har timeframe ka alag): teen cheezon ka score (0–100) —
1. group ka median return − market return
2. participation: kitne % stocks market se aage
3. kitne % stocks 20-din high pe

Small groups (3 ya kam stocks) ko rank nahi milta, wo "Small groups bhi" tick karke dikhte hain.

Stock RS (1–99): Large → Nifty 50, Mid → Midcap 150, Small + Micro → Smallcap 250 ke against.

Data: stocks Yahoo Finance se, benchmarks NSE official (nsearchives) se.

## Ek baar ka setup (pehle se ho chuka hai)
1. Telegram secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (Settings → Secrets → Actions)
2. Pages: Settings → Pages → Branch `main`, folder `/docs`
3. Haath se chalana: Actions → "Sector Rotation" → Run workflow

## RRG formula
RS = Group ÷ Benchmark → EMA smoothing → RS-Ratio = RS ÷ uska average × 100 → RS-Mom = RS-Ratio ÷ kuch period pehle × 100
- Daily: smoothing 5, ratio 21 din, momentum 5 din
- Weekly: smoothing 3, ratio 10 hafte, momentum 4 hafte
- Monthly: smoothing 2, ratio 6 mahine, momentum 3 mahine

Test (bina internet): `python rotation.py --demo`
