# 📊 Trade Tribe — Sector Rotation (Auto)

**Roz shaam ~7:45 (Mon–Fri)** dashboard update hota hai, aur **Shanivar subah ~8:45** Telegram alert aata hai.

Data: **NSE official indices** (nsearchives.nseindia.com), stocks ke liye Yahoo Finance.

Kya hota hai:
1. ~48 NSE indices (sectors + broad market) ko Nifty 50 se compare karta hai — Strike jaisa RRG chart, Daily/Weekly, ▶ Play
1. 18 main sectors ka phase (RRG — Leading / Improving / Weakening / Lagging)
2. Har sector ka breadth (% stocks 50 DMA ke upar) + top 5 strong stocks nikalta hai
3. Live dashboard update karta hai → `https://<aapka-github-naam>.github.io/sector-rotation/`
4. **Telegram pe alert** bhejta hai — kaun sa sector Leading mein aaya, kaun sa kamzor hua

Python aane ki zarurat nahi. Sirf ek baar 10–15 minute ka setup.

## Ek baar ka setup

**1. Telegram bot banao (alert ke liye)**
- Telegram mein `@BotFather` kholo → `/newbot` → koi naam do → jo **token** mile, copy karo
- Apne naye bot ko kholo aur `/start` bhejo
- `@userinfobot` ko message karo → jo **Id** number mile, copy karo (ye aapka chat ID hai)

**2. Secrets daalo** — repo mein: Settings → Secrets and variables → Actions → New repository secret
- `TELEGRAM_BOT_TOKEN` = BotFather wala token
- `TELEGRAM_CHAT_ID` = userinfobot wala Id

**3. Dashboard on karo** — Settings → Pages → Source: *Deploy from a branch* → Branch: `main`, folder: `/docs` → Save

**4. Pehli baar chalao** — Actions tab → "Weekly Sector Rotation" → **Run workflow**. 2–3 minute mein Telegram pe message aa jayega.

## Sectors badalne hain?
`rotation.py` mein upar `SECTORS` list hai — line hatao ya jodo. Bas.

## Formula (TradingView indicator jaisa hi)
- RS = Sector ÷ Nifty → 3-week EMA → RS-Ratio = RS ÷ 10-week average × 100
- RS-Mom = RS-Ratio ÷ RS-Ratio 4 hafte pehle × 100
- Ratio > 100 aur Mom > 100 = LEADING, Ratio < 100 aur Mom > 100 = IMPROVING, waghera
