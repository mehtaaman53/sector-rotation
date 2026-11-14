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
- **RRG — Weekly aur Monthly** (group vs Nifty 500)
- Har stock: return, 52W high se doori, **RS** (1–99, apne benchmark ke against), volume ratio
- Group quality: size, liquidity, cap mix, "Mostly Micro" flag

## Benchmarks
| Kaun | Kisse compare |
|---|---|
| Sector / Industry / Theme | Nifty 500 |
| Large cap stock (mcap rank 1–100) | Nifty 50 |
| Mid cap (101–250) | Nifty Midcap 150 |
| Small (251–500) + Micro (501+) | Nifty Smallcap 250 |

Data: stocks Yahoo Finance se, benchmarks NSE official (nsearchives) se.

## Ek baar ka setup (pehle se ho chuka hai)
1. Telegram secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (Settings → Secrets → Actions)
2. Pages: Settings → Pages → Branch `main`, folder `/docs`
3. Haath se chalana: Actions → "Sector Rotation" → Run workflow

## RRG formula
RS = Group ÷ Nifty 500 → EMA smoothing → RS-Ratio = RS ÷ uska average × 100 → RS-Mom = RS-Ratio ÷ kuch period pehle × 100
- Weekly: smoothing 3, ratio 10 hafte, momentum 4 hafte
- Monthly: smoothing 2, ratio 6 mahine, momentum 3 mahine

Test (bina internet): `python rotation.py --demo`
