"""
🤖 EGX Pulse Bot - Full Version v3.0
Features: Technical Analysis + AI + Alerts + Daily Report + Portfolio + Compare + Multi-timeframe + Stop Loss/Take Profit + News
"""

import os
import asyncio
import logging
from datetime import datetime, time as dtime
import httpx
import yfinance as yf
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler, ContextTypes)
from openai import OpenAI

# ==================== CONFIG ====================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_TELEGRAM_TOKEN_HERE")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_KEY_HERE")

client = OpenAI(api_key=OPENAI_API_KEY, base_url="https://api.openai.com/v1")

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ==================== EGX STOCKS ====================
EGX30_STOCKS = {
    "COMI": "CIB - البنك التجاري الدولي", "SWDY": "السويدي إليكتريك",
    "TMGH": "طلعت مصطفى", "ETEL": "المصرية للاتصالات",
    "EAST": "إيسترن كومباني", "EGAL": "مصر للألومنيوم",
    "ABUK": "أبو قير للأسمدة", "QNBE": "بنك قطر الوطني",
    "ALCN": "الإسكندرية للحاويات", "EFIH": "إي-فاينانس",
    "FWRY": "فوري", "HDBK": "بنك الإسكان والتعمير",
    "ORAS": "أوراسكوم للإنشاء", "EMFD": "إعمار مصر",
    "ADIB": "بنك أبو ظبي الإسلامي", "HRHO": "EFG هيرميس",
    "JUFO": "جهينة", "IRON": "الحديد والصلب المصرية",
    "FERC": "فيركيم مصر", "GBCO": "GB كورب",
    "OCDI": "سوديك", "EGCH": "الصناعات الكيماوية المصرية",
    "PHDC": "بالم هيلز", "CIEB": "كريدي أجريكول مصر",
    "ORHD": "أوراسكوم للتطوير",
}

EGX70_STOCKS = {
    "VLMR": "فالمور هولدينج", "EFID": "إيديتا للصناعات الغذائية",
    "BTFH": "بلتون هولدينج", "FAIT": "بنك فيصل الإسلامي",
    "CANA": "بنك قناة السويس", "SCTS": "قناة السويس للتكنولوجيا",
    "RAYA": "راية هولدينج", "MFPC": "مصر للأسمدة",
    "ESRS": "عز للصلب", "MNHD": "مدينة نصر للإسكان",
    "SKPC": "سيدي كرير للبتروكيماويات", "AMOC": "مصر لتكرير البترول",
    "CLHO": "سيتي إيدج", "AMER": "أمر جروب",
    "GTHE": "جي تي إتش", "HELI": "هيليوبوليس",
    "ISPH": "آيزيس فارما", "BMRA": "بيتا إيجيبت",
    "EKHO": "إيكو للتطوير", "OFMD": "أوفمد",
    "POUL": "كايرو بولتري", "ORWE": "أوريدو مصر",
}

ALL_STOCKS = {**EGX30_STOCKS, **EGX70_STOCKS}
EGX100_STOCKS = ALL_STOCKS


# ==================== TECHNICAL INDICATORS ====================

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    return round(100 - (100 / (1 + avg_gain / avg_loss)), 2)

def calculate_sma(prices, period):
    if len(prices) < period:
        return prices[-1] if prices else 0
    return round(sum(prices[-period:]) / period, 2)

def calculate_macd(prices):
    def ema(data, period):
        if len(data) < period:
            return data[-1] if data else 0
        k = 2 / (period + 1)
        v = sum(data[:period]) / period
        for p in data[period:]:
            v = p * k + v * (1 - k)
        return round(v, 2)
    if len(prices) < 26:
        return 0, 0, 0
    macd = round(ema(prices, 12) - ema(prices, 26), 2)
    signal = round(ema(prices[-9:], 9), 2) if len(prices) >= 9 else macd
    return macd, signal, round(macd - signal, 2)

def calculate_bollinger(prices, period=20):
    if len(prices) < period:
        p = prices[-1] if prices else 0
        return p, p, p
    sma = sum(prices[-period:]) / period
    std = (sum((p - sma)**2 for p in prices[-period:]) / period) ** 0.5
    return round(sma + 2*std, 2), round(sma, 2), round(sma - 2*std, 2)

def calculate_atr(highs, lows, closes, period=14):
    if len(closes) < period + 1 or not highs or not lows:
        return 0
    trs = [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
           for i in range(1, min(len(closes), len(highs), len(lows)))]
    return round(sum(trs[-period:]) / period, 2) if trs else 0


# ==================== GET STOCK DATA ====================

async def get_stock_data(symbol, interval="1d", range_="60d"):
    """جيب بيانات السهم - بيحاول Yahoo Finance API الأول، لو فشل بيستخدم yfinance"""

    # ترجمة interval وrange لـ yfinance
    yf_period_map = {"60d": "3mo", "52wk": "1y", "30d": "1mo", "5d": "5d"}
    yf_interval_map = {"1d": "1d", "1wk": "1wk", "1h": "60m"}
    yf_period = yf_period_map.get(range_, "3mo")
    yf_interval = yf_interval_map.get(interval, "1d")

    closes, highs, lows, vols = [], [], [], []
    price = prev_close = volume = 0

    # === المحاولة الأولى: Yahoo Finance API ===
    try:
        # جرب query1 و query2
        for host in ["query1", "query2"]:
            url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{symbol}.CA?interval={interval}&range={range_}"
            async with httpx.AsyncClient(timeout=12) as http:
                r = await http.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    "Accept": "application/json",
                })
                if r.status_code != 200:
                    continue
                data = r.json()

            result = data.get("chart", {}).get("result", [])
            if not result:
                continue

            meta = result[0].get("meta", {})
            quote = result[0].get("indicators", {}).get("quote", [{}])[0]

            closes = [c for c in quote.get("close", []) if c is not None]
            highs  = [h for h in quote.get("high",  []) if h is not None]
            lows   = [l for l in quote.get("low",   []) if l is not None]
            vols   = [v for v in quote.get("volume",[]) if v is not None]

            if closes:
                price      = meta.get("regularMarketPrice", closes[-1])
                prev_close = meta.get("previousClose", closes[-2] if len(closes) > 1 else price)
                volume     = meta.get("regularMarketVolume", vols[-1] if vols else 0)
                break  # نجح!
    except Exception:
        pass  # هيكمل على yfinance

    # === المحاولة الثانية: yfinance (fallback) ===
    if not closes:
        try:
            ticker = yf.Ticker(f"{symbol}.CA")
            hist = ticker.history(period=yf_period, interval=yf_interval)

            if hist.empty:
                return {"error": f"السهم '{symbol}' مش موجود على Yahoo Finance.\nجرب: COMI, ETEL, SWDY, HRHO"}

            closes = hist["Close"].tolist()
            highs  = hist["High"].tolist()
            lows   = hist["Low"].tolist()
            vols   = hist["Volume"].tolist()

            price      = closes[-1]
            prev_close = closes[-2] if len(closes) > 1 else price
            volume     = int(vols[-1]) if vols else 0
        except Exception as e:
            return {"error": f"خطأ في جيب البيانات: {str(e)}"}

    if not closes:
        return {"error": "مفيش بيانات متاحة للسهم ده دلوقتي"}

    # === حساب المؤشرات ===
    change     = round(price - prev_close, 2) if prev_close else 0
    change_pct = round((change / prev_close * 100), 2) if prev_close else 0
    avg_vol    = int(sum(vols[-20:]) / len(vols[-20:])) if len(vols) >= 20 else (int(sum(vols) / len(vols)) if vols else 0)

    macd, macd_sig, macd_hist = calculate_macd(closes)
    bb_upper, bb_mid, bb_lower = calculate_bollinger(closes)

    return {
        "symbol": symbol, "name": ALL_STOCKS.get(symbol, symbol),
        "price": round(price, 2), "prev_close": round(prev_close, 2),
        "change": change, "change_pct": change_pct,
        "volume": volume, "avg_volume": avg_vol,
        "volume_ratio": round(volume / avg_vol, 2) if avg_vol else 1.0,
        "time": datetime.now().strftime("%H:%M:%S"),
        "rsi": calculate_rsi(closes),
        "sma20": calculate_sma(closes, 20), "sma50": calculate_sma(closes, 50),
        "macd": macd, "macd_signal": macd_sig, "macd_hist": macd_hist,
        "bb_upper": bb_upper, "bb_mid": bb_mid, "bb_lower": bb_lower,
        "atr": calculate_atr(highs, lows, closes),
        "high_period": round(max(closes), 2), "low_period": round(min(closes), 2),
        "closes": closes,
    }


# ==================== SIGNAL + SL/TP ====================

def calculate_signal(data):
    if "error" in data:
        return {"signal": "WAIT", "emoji": "🟡", "label": "انتظار", "score": 0, "reasons": []}

    score, reasons = 0, []
    price, rsi = data["price"], data["rsi"]
    sma20, sma50 = data["sma20"], data["sma50"]
    macd, macd_sig = data["macd"], data["macd_signal"]
    bb_upper, bb_lower = data["bb_upper"], data["bb_lower"]
    vol_ratio, change_pct = data["volume_ratio"], data["change_pct"]

    if rsi < 30:   score += 2; reasons.append(f"RSI={rsi} 🟢 Oversold")
    elif rsi < 45: score += 1; reasons.append(f"RSI={rsi} منطقة شراء")
    elif rsi > 70: score -= 2; reasons.append(f"RSI={rsi} 🔴 Overbought")
    elif rsi > 55: score -= 1; reasons.append(f"RSI={rsi} ضغط بيع")

    if price > sma20 and sma20 > sma50:   score += 2; reasons.append(f"فوق SMA20({sma20}) و SMA50({sma50}) ✅")
    elif price > sma20:                    score += 1; reasons.append(f"فوق SMA20({sma20})")
    elif price < sma20 and sma20 < sma50: score -= 2; reasons.append(f"تحت SMA20({sma20}) و SMA50({sma50}) ❌")
    elif price < sma20:                   score -= 1; reasons.append(f"تحت SMA20({sma20})")

    if macd > macd_sig and data["macd_hist"] > 0:   score += 2; reasons.append(f"MACD إيجابي ✅")
    elif macd < macd_sig and data["macd_hist"] < 0: score -= 2; reasons.append(f"MACD سلبي ❌")

    if price <= bb_lower:   score += 1; reasons.append(f"عند Bollinger الأدنى ({bb_lower})")
    elif price >= bb_upper: score -= 1; reasons.append(f"عند Bollinger الأعلى ({bb_upper})")

    if vol_ratio > 1.5:
        if change_pct > 0: score += 1; reasons.append(f"حجم مرتفع {vol_ratio}x مع ارتفاع 🔥")
        else:              score -= 1; reasons.append(f"حجم مرتفع {vol_ratio}x مع انخفاض ⚠️")

    if score >= 3:   return {"signal": "BUY",  "emoji": "🟢", "label": "شراء",   "score": score, "reasons": reasons}
    elif score <= -3: return {"signal": "SELL", "emoji": "🔴", "label": "بيع",    "score": score, "reasons": reasons}
    else:             return {"signal": "WAIT", "emoji": "🟡", "label": "انتظار", "score": score, "reasons": reasons}


def calculate_sl_tp(data, signal):
    price = data["price"]
    atr = data.get("atr", 0) or price * 0.02

    if signal["signal"] == "BUY":
        sl  = round(price - 1.5 * atr, 2)
        tp1 = round(price + 2.0 * atr, 2)
        tp2 = round(price + 3.5 * atr, 2)
    elif signal["signal"] == "SELL":
        sl  = round(price + 1.5 * atr, 2)
        tp1 = round(price - 2.0 * atr, 2)
        tp2 = round(price - 3.5 * atr, 2)
    else:
        sl  = round(price - 1.5 * atr, 2)
        tp1 = round(price + 2.0 * atr, 2)
        tp2 = round(price + 3.5 * atr, 2)

    sl_pct  = round(abs(price - sl)  / price * 100, 2)
    tp1_pct = round(abs(price - tp1) / price * 100, 2)
    tp2_pct = round(abs(price - tp2) / price * 100, 2)
    rr = round(abs(tp1 - price) / abs(price - sl), 2) if abs(price - sl) > 0 else 0

    return {"stop_loss": sl, "take_profit_1": tp1, "take_profit_2": tp2,
            "sl_pct": sl_pct, "tp1_pct": tp1_pct, "tp2_pct": tp2_pct, "risk_reward": rr}


# ==================== AI ====================

async def analyze_with_ai(data, signal, weekly_data=None):
    if "error" in data:
        return f"❌ {data['error']}"
    weekly_info = ""
    if weekly_data and "error" not in weekly_data:
        ws = calculate_signal(weekly_data)
        weekly_info = f"\nأسبوعي: RSI={weekly_data['rsi']} | إشارة={ws['label']}"

    prompt = f"""أنت محلل فني خبير في البورصة المصرية.
اكتب تحليلاً موجزاً (3 جمل فقط) للسهم:
{data['name']} ({data['symbol']}) | السعر: {data['price']} | {data['change_pct']:+.2f}%
RSI: {data['rsi']} | SMA20: {data['sma20']} | SMA50: {data['sma50']}
MACD: {data['macd']} | Bollinger: {data['bb_lower']}↔{data['bb_upper']}
حجم: {data['volume_ratio']}x | الإشارة: {signal['label']} (score: {signal['score']}){weekly_info}
انهِ بـ: ⚠️ ليس نصيحة استثمارية."""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=250, temperature=0.2
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"❌ {str(e)}"


async def get_market_news():
    try:
        prompt = """أنت محلل مالي متخصص في البورصة المصرية.
اكتب ملخصاً لأهم 4 عوامل تؤثر على سوق الأسهم المصري حالياً (مارس 2026):
الفائدة، العملة، أسعار النفط، وأي أحداث اقتصادية مهمة.
اجعل الرد مختصراً (4-5 جمل). انهِ بـ: ⚠️ للمعلومات فقط."""
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300, temperature=0.3
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"❌ {str(e)}"


async def get_stock_news(symbol: str) -> list:
    """بيجيب أخبار الشركة من Mubasher"""
    try:
        url = f"https://english.mubasher.info/markets/EGX/stocks/{symbol}/news"
        async with httpx.AsyncClient(timeout=15) as http:
            r = await http.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            html = r.text

        # استخراج العناوين من HTML بشكل بسيط
        import re
        # بندور على عناوين الأخبار
        titles = re.findall(r'class="[^"]*title[^"]*"[^>]*>\s*<[^>]+>\s*([^<]{20,200})', html)
        if not titles:
            # try alternative pattern
            titles = re.findall(r'<h\d[^>]*>\s*([A-Z][^<]{20,150})</h\d>', html)

        # تنظيف النتائج
        clean = []
        for t in titles[:5]:
            t = t.strip()
            if len(t) > 20 and symbol not in t and 'mubasher' not in t.lower():
                clean.append(t)

        return clean[:4] if clean else []
    except Exception:
        return []


async def summarize_news_with_ai(symbol: str, news: list, signal: dict) -> str:
    """AI يلخص الأخبار ويربطها بالإشارة الفنية"""
    if not news:
        return "لم يتم العثور على أخبار حديثة."
    try:
        news_text = "\n".join([f"- {n}" for n in news])
        prompt = f"""أنت محلل مالي خبير في البورصة المصرية.
السهم: {ALL_STOCKS.get(symbol, symbol)} ({symbol})
الإشارة الفنية: {signal['label']} (score: {signal['score']})

أخبار حديثة:
{news_text}

في جملتين فقط:
1. لخص أهم خبر وتأثيره على السهم
2. هل الأخبار تدعم الإشارة الفنية أم تعارضها؟
انهِ بـ: ⚠️ للمعلومات فقط."""
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200, temperature=0.2
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"❌ {str(e)}"


async def get_market_liquidity() -> dict:
    """بيجيب بيانات السيولة من Yahoo Finance لأكبر أسهم EGX"""
    try:
        total_volume = 0
        total_turnover = 0
        top_volume = []

        tasks = [get_stock_data(sym) for sym in list(EGX30_STOCKS.keys())[:15]]
        results = await asyncio.gather(*tasks)

        for data in results:
            if "error" not in data:
                vol = data.get("volume", 0)
                price = data.get("price", 0)
                turnover = vol * price
                total_volume += vol
                total_turnover += turnover
                top_volume.append({
                    "symbol": data["symbol"],
                    "name": data["name"],
                    "volume": vol,
                    "turnover": turnover,
                    "change_pct": data["change_pct"],
                    "volume_ratio": data["volume_ratio"]
                })

        # ترتيب حسب حجم التداول
        top_volume.sort(key=lambda x: x["turnover"], reverse=True)

        return {
            "total_volume": total_volume,
            "total_turnover": total_turnover,
            "top_by_volume": top_volume[:5],
            "time": datetime.now().strftime("%H:%M")
        }
    except Exception as e:
        return {"error": str(e)}


# ==================== COMMANDS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Save chat_id for daily report
    user_id = str(update.effective_user.id)
    if user_id not in context.bot_data:
        context.bot_data[user_id] = {}
    context.bot_data[user_id]["chat_id"] = update.effective_chat.id

    welcome = """🏦 *أهلاً في EGX Pulse Bot v3.1!*
📊 RSI | MACD | Bollinger | SMA | ATR | Multi-Timeframe

*تحليل الأسهم:*
/price COMI - سعر + مؤشرات + SL/TP
/analyze COMI - تحليل يومي + أسبوعي + AI
/compare COMI ETEL - مقارنة سهمين

*📰 الأخبار والسيولة:*
/stocknews COMI - أخبار الشركة من Mubasher + AI
/news - أخبار السوق العامة
/liquidity - حجم السيولة اليومي

*الأسواق:*
/egx30 | /egx70 | /egx100

*🔔 التنبيهات:*
/alert COMI 80 | /alerts | /delalert COMI

*💼 المحفظة:*
/buy COMI 100 75.5 | /sell COMI 100 80 | /portfolio

*📊 تقارير:*
/report - تقرير فوري + اشتراك يومي ١٠ص

*⭐ متابعة:*
/watchlist | /add COMI | /remove COMI | /help

⚠️ _للمعلومات الشخصية فقط - مش نصيحة استثمارية_"""
    await update.message.reply_text(welcome, parse_mode="Markdown")


async def get_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ مثلاً: /price COMI")
        return
    symbol = context.args[0].upper()
    if symbol not in ALL_STOCKS:
        await update.message.reply_text(f"❌ '{symbol}' مش موجود.")
        return
    msg = await update.message.reply_text("⏳ بجيب السعر...")
    data = await get_stock_data(symbol)
    if "error" in data:
        await msg.edit_text(f"❌ {data['error']}")
        return
    signal = calculate_signal(data)
    sl_tp = calculate_sl_tp(data, signal)
    ce = "📈" if data['change'] >= 0 else "📉"

    text = f"""{ce} *{data['name']}* ({symbol})

💰 *السعر:* {data['price']:.2f} جنيه
📊 *التغيير:* {data['change']:+.2f} ({data['change_pct']:+.2f}%)
📦 *حجم:* {data['volume']:,} ({data['volume_ratio']}x)

📉 *مؤشرات:*
• RSI: {data['rsi']}
• SMA20: {data['sma20']} | SMA50: {data['sma50']}
• Bollinger: {data['bb_lower']} ↔ {data['bb_upper']}

{signal['emoji']} *الإشارة: {signal['label']}* (Score: {signal['score']}/8)
🛡️ *SL:* {sl_tp['stop_loss']} ({sl_tp['sl_pct']}% ↓)
🎯 *TP:* {sl_tp['take_profit_1']} ({sl_tp['tp1_pct']}% ↑)
⚖️ *R/R:* 1:{sl_tp['risk_reward']}

🕐 {data['time']}"""

    keyboard = [[
        InlineKeyboardButton("🤖 تحليل AI كامل", callback_data=f"analyze_{symbol}"),
        InlineKeyboardButton("➕ متابعة", callback_data=f"add_{symbol}")
    ]]
    await msg.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


async def analyze_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ مثلاً: /analyze COMI")
        return
    symbol = context.args[0].upper()
    if symbol not in ALL_STOCKS:
        await update.message.reply_text(f"❌ '{symbol}' مش موجود.")
        return
    msg = await update.message.reply_text("🤖 بحلل يومي + أسبوعي... ثانية!")

    daily, weekly = await asyncio.gather(
        get_stock_data(symbol, "1d", "60d"),
        get_stock_data(symbol, "1wk", "52wk")
    )
    if "error" in daily:
        await msg.edit_text(f"❌ {daily['error']}")
        return

    ds = calculate_signal(daily)
    ws = calculate_signal(weekly) if "error" not in weekly else {"emoji": "❓", "label": "غير متاح", "score": 0}
    sl_tp = calculate_sl_tp(daily, ds)
    ai = await analyze_with_ai(daily, ds, weekly)
    reasons = "\n".join([f"  • {r}" for r in ds['reasons']])
    ce = "📈" if daily['change'] >= 0 else "📉"

    text = f"""{ce} *تحليل {daily['name']}* ({symbol})

💰 *السعر:* {daily['price']:.2f} جنيه | {daily['change_pct']:+.2f}%

📊 *مؤشرات يومية:*
• RSI: {daily['rsi']} {'🔴' if daily['rsi']>70 else '🟢' if daily['rsi']<30 else '🟡'}
• SMA20: {daily['sma20']} | SMA50: {daily['sma50']}
• MACD: {daily['macd']} | Signal: {daily['macd_signal']}
• Bollinger: {daily['bb_lower']} ↔ {daily['bb_upper']}
• حجم: {daily['volume_ratio']}x المتوسط

📅 *إشارة أسبوعية:* {ws['emoji']} {ws['label']}

{ds['emoji']} *الإشارة اليومية: {ds['label']}* (Score: {ds['score']}/8)
{reasons}

🛡️ *Stop Loss:* {sl_tp['stop_loss']} ({sl_tp['sl_pct']}% ↓)
🎯 *Take Profit 1:* {sl_tp['take_profit_1']} ({sl_tp['tp1_pct']}% ↑)
🎯 *Take Profit 2:* {sl_tp['take_profit_2']} ({sl_tp['tp2_pct']}% ↑)
⚖️ *Risk/Reward:* 1:{sl_tp['risk_reward']}

🤖 *تحليل AI:*
{ai}"""
    await msg.edit_text(text, parse_mode="Markdown")


async def compare_stocks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ مثلاً: /compare COMI ETEL")
        return
    sym1, sym2 = context.args[0].upper(), context.args[1].upper()
    for s in [sym1, sym2]:
        if s not in ALL_STOCKS:
            await update.message.reply_text(f"❌ '{s}' مش موجود.")
            return
    msg = await update.message.reply_text("⚖️ بقارن السهمين...")
    d1, d2 = await asyncio.gather(get_stock_data(sym1), get_stock_data(sym2))
    if "error" in d1 or "error" in d2:
        await msg.edit_text("❌ خطأ في جيب البيانات.")
        return
    s1, s2 = calculate_signal(d1), calculate_signal(d2)
    winner = sym1 if s1['score'] > s2['score'] else (sym2 if s2['score'] > s1['score'] else "تعادل!")

    text = f"""⚖️ *مقارنة: {sym1} vs {sym2}*

*{sym1} - {d1['name']}*
💰 {d1['price']:.2f} جنيه | {d1['change_pct']:+.2f}%
{s1['emoji']} {s1['label']} (Score: {s1['score']}/8)

*{sym2} - {d2['name']}*
💰 {d2['price']:.2f} جنيه | {d2['change_pct']:+.2f}%
{s2['emoji']} {s2['label']} (Score: {s2['score']}/8)

```
المؤشر    {sym1:<8} {sym2:<8}
RSI     : {str(d1['rsi']):<8} {str(d2['rsi']):<8}
SMA20   : {str(d1['sma20']):<8} {str(d2['sma20']):<8}
SMA50   : {str(d1['sma50']):<8} {str(d2['sma50']):<8}
MACD    : {str(d1['macd']):<8} {str(d2['macd']):<8}
Vol x   : {str(d1['volume_ratio']):<8} {str(d2['volume_ratio']):<8}
Score   : {str(s1['score']):<8} {str(s2['score']):<8}
```
🏆 *الأفضل حالياً:* {winner}"""
    await msg.edit_text(text, parse_mode="Markdown")


async def market_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("📰 بجيب أخبار السوق...")
    news = await get_market_news()
    await msg.edit_text(f"📰 *أخبار السوق المصري*\n🕐 {datetime.now().strftime('%H:%M')}\n\n{news}", parse_mode="Markdown")


async def stock_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/stocknews COMI - أخبار شركة معينة"""
    if not context.args:
        await update.message.reply_text("⚠️ مثلاً: /stocknews COMI")
        return
    symbol = context.args[0].upper()
    if symbol not in ALL_STOCKS:
        await update.message.reply_text(f"❌ '{symbol}' مش موجود.")
        return

    msg = await update.message.reply_text(f"📰 بجيب أخبار {ALL_STOCKS[symbol]}...")

    # جيب الأخبار والبيانات بالتوازي
    news, data = await asyncio.gather(
        get_stock_news(symbol),
        get_stock_data(symbol)
    )

    signal = calculate_signal(data) if "error" not in data else {"label": "غير متاح", "score": 0}
    ai_summary = await summarize_news_with_ai(symbol, news, signal)

    if news:
        news_text = "\n".join([f"• {n}" for n in news])
    else:
        news_text = "لم يتم العثور على أخبار حديثة على Mubasher"

    price_info = ""
    if "error" not in data:
        ce = "📈" if data['change'] >= 0 else "📉"
        price_info = f"\n{ce} السعر: {data['price']:.2f} جنيه ({data['change_pct']:+.2f}%) {signal['emoji'] if 'emoji' in signal else ''}"

    text = f"""📰 *أخبار {ALL_STOCKS[symbol]}* ({symbol}){price_info}

*آخر الأخبار من Mubasher:*
{news_text}

🤖 *تحليل AI للأخبار:*
{ai_summary}

🔗 المزيد: english.mubasher.info/markets/EGX/stocks/{symbol}/news"""

    await msg.edit_text(text, parse_mode="Markdown")


async def market_liquidity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/liquidity - حجم السيولة اليومي"""
    msg = await update.message.reply_text("💧 بجيب بيانات السيولة...")

    liq = await get_market_liquidity()

    if "error" in liq:
        await msg.edit_text(f"❌ خطأ: {liq['error']}")
        return

    top_lines = []
    for s in liq["top_by_volume"]:
        ce = "📈" if s['change_pct'] >= 0 else "📉"
        intensity = "🔥" if s['volume_ratio'] > 2 else "⚡" if s['volume_ratio'] > 1.5 else ""
        top_lines.append(
            f"{ce} *{s['symbol']}* - {s['turnover']/1_000_000:.1f}M جنيه {intensity}\n"
            f"   {s['volume']:,} سهم ({s['volume_ratio']}x المتوسط)"
        )

    # تقييم السيولة الإجمالية
    total_m = liq['total_turnover'] / 1_000_000
    if total_m > 500:
        market_status = "🔥 سوق نشيط جداً"
    elif total_m > 200:
        market_status = "✅ سوق طبيعي"
    else:
        market_status = "😴 سوق هادئ"

    text = f"""💧 *سيولة السوق المصري*
🕐 {liq['time']} | {market_status}

📊 *إجمالي EGX 30 (أكبر 15 سهم):*
• حجم التداول: {liq['total_volume']:,} سهم
• قيمة التداول: {total_m:.1f} مليون جنيه

🏆 *الأعلى تداولاً:*
{chr(10).join(top_lines)}

💡 *ملاحظة:* السيولة المرتفعة تؤكد الإشارات الفنية
_للتحليل: /analyze SYMBOL_"""

    await msg.edit_text(text, parse_mode="Markdown")


# ==================== PRICE ALERTS ====================

async def set_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ مثلاً: /alert COMI 80")
        return
    symbol = context.args[0].upper()
    try:
        target = float(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ السعر لازم يكون رقم")
        return
    if symbol not in ALL_STOCKS:
        await update.message.reply_text(f"❌ '{symbol}' مش موجود.")
        return
    user_id = str(update.effective_user.id)
    if user_id not in context.bot_data:
        context.bot_data[user_id] = {}
    if "alerts" not in context.bot_data[user_id]:
        context.bot_data[user_id]["alerts"] = {}
    context.bot_data[user_id]["alerts"][symbol] = {"target": target, "chat_id": update.effective_chat.id}
    await update.message.reply_text(f"🔔 تم!\n{ALL_STOCKS[symbol]} ({symbol})\nهيتبعتلك لما يوصل {target:.2f} جنيه")


async def show_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    alerts = context.bot_data.get(user_id, {}).get("alerts", {})
    if not alerts:
        await update.message.reply_text("🔔 مفيش تنبيهات.\nعمل تنبيه: /alert COMI 80")
        return
    text = "🔔 *تنبيهاتك:*\n\n" + "\n".join([f"• *{s}* → {i['target']:.2f} جنيه" for s, i in alerts.items()])
    text += "\n\nلحذف: /delalert COMI"
    await update.message.reply_text(text, parse_mode="Markdown")


async def delete_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ مثلاً: /delalert COMI")
        return
    symbol = context.args[0].upper()
    user_id = str(update.effective_user.id)
    alerts = context.bot_data.get(user_id, {}).get("alerts", {})
    if symbol in alerts:
        del context.bot_data[user_id]["alerts"][symbol]
        await update.message.reply_text(f"✅ تم حذف تنبيه {symbol}")
    else:
        await update.message.reply_text(f"❌ مفيش تنبيه لـ {symbol}")


async def check_alerts(context):
    """كل 15 دقيقة - بيتشيك على التنبيهات"""
    for user_id, user_data in context.bot_data.items():
        for symbol, info in list(user_data.get("alerts", {}).items()):
            data = await get_stock_data(symbol)
            if "error" in data:
                continue
            if abs(data["price"] - info["target"]) / info["target"] <= 0.01:
                signal = calculate_signal(data)
                await context.bot.send_message(
                    chat_id=info["chat_id"],
                    text=f"🔔 *تنبيه!*\n{data['name']} ({symbol})\n💰 السعر: {data['price']:.2f} جنيه\n🎯 الهدف: {info['target']:.2f}\n{signal['emoji']} {signal['label']}",
                    parse_mode="Markdown"
                )
                del context.bot_data[user_id]["alerts"][symbol]


# ==================== PORTFOLIO ====================

async def buy_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 3:
        await update.message.reply_text("⚠️ مثلاً: /buy COMI 100 75.5")
        return
    symbol = context.args[0].upper()
    try:
        qty, price = float(context.args[1]), float(context.args[2])
    except ValueError:
        await update.message.reply_text("❌ الكمية والسعر لازم أرقام")
        return
    if symbol not in ALL_STOCKS:
        await update.message.reply_text(f"❌ '{symbol}' مش موجود.")
        return
    user_id = str(update.effective_user.id)
    if user_id not in context.bot_data:
        context.bot_data[user_id] = {}
    if "portfolio" not in context.bot_data[user_id]:
        context.bot_data[user_id]["portfolio"] = {}
    pf = context.bot_data[user_id]["portfolio"]
    if symbol in pf:
        oq, op = pf[symbol]["qty"], pf[symbol]["avg_price"]
        new_qty = oq + qty
        new_avg = round((oq * op + qty * price) / new_qty, 2)
        pf[symbol] = {"qty": new_qty, "avg_price": new_avg}
        await update.message.reply_text(f"✅ تم الإضافة!\n{ALL_STOCKS[symbol]} ({symbol})\n+{qty:.0f} سهم بـ {price:.2f}\nمتوسط جديد: {new_avg:.2f}")
    else:
        pf[symbol] = {"qty": qty, "avg_price": price}
        await update.message.reply_text(f"✅ تم الإضافة!\n{ALL_STOCKS[symbol]} ({symbol})\n{qty:.0f} × {price:.2f} = {qty*price:.2f} جنيه")


async def sell_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 3:
        await update.message.reply_text("⚠️ مثلاً: /sell COMI 100 80")
        return
    symbol = context.args[0].upper()
    try:
        qty, sell_price = float(context.args[1]), float(context.args[2])
    except ValueError:
        await update.message.reply_text("❌ الكمية والسعر لازم أرقام")
        return
    user_id = str(update.effective_user.id)
    pf = context.bot_data.get(user_id, {}).get("portfolio", {})
    if symbol not in pf:
        await update.message.reply_text(f"❌ {symbol} مش في محفظتك.")
        return
    avg = pf[symbol]["avg_price"]
    profit = round((sell_price - avg) * qty, 2)
    profit_pct = round((sell_price - avg) / avg * 100, 2)
    emoji = "🟢" if profit >= 0 else "🔴"
    remaining = pf[symbol]["qty"] - qty
    if remaining <= 0:
        del context.bot_data[user_id]["portfolio"][symbol]
        status = "تم بيع كل الأسهم ✅"
    else:
        context.bot_data[user_id]["portfolio"][symbol]["qty"] = remaining
        status = f"متبقي: {remaining:.0f} سهم"
    await update.message.reply_text(
        f"{emoji} *صفقة بيع*\n{ALL_STOCKS[symbol]} ({symbol})\n"
        f"شراء: {avg:.2f} | بيع: {sell_price:.2f}\n"
        f"الربح: {profit:+.2f} جنيه ({profit_pct:+.2f}%)\n{status}",
        parse_mode="Markdown"
    )


async def show_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    pf = context.bot_data.get(user_id, {}).get("portfolio", {})
    if not pf:
        await update.message.reply_text("💼 محفظتك فاضية!\nسجل صفقة: /buy COMI 100 75.5")
        return
    msg = await update.message.reply_text("💼 بحسب المحفظة...")
    total_inv, total_cur, lines = 0, 0, []
    for symbol, info in pf.items():
        data = await get_stock_data(symbol)
        if "error" in data:
            continue
        cur = data["price"]
        inv = info["qty"] * info["avg_price"]
        val = info["qty"] * cur
        profit = val - inv
        pct = (profit / inv * 100) if inv else 0
        total_inv += inv; total_cur += val
        e = "🟢" if profit >= 0 else "🔴"
        lines.append(f"{e} *{symbol}* × {info['qty']:.0f}\n   {info['avg_price']:.2f} → {cur:.2f} | {profit:+.2f} ({pct:+.2f}%)")
    tp = total_cur - total_inv
    tpct = (tp / total_inv * 100) if total_inv else 0
    te = "🟢" if tp >= 0 else "🔴"
    text = "💼 *محفظتك*\n\n" + "\n\n".join(lines)
    text += f"\n\n{'─'*20}\n{te} الإجمالي:\nرأس المال: {total_inv:,.2f}\nالقيمة الآن: {total_cur:,.2f}\nالربح/الخسارة: {tp:+,.2f} ({tpct:+.2f}%)"
    await msg.edit_text(text, parse_mode="Markdown")


# ==================== DAILY REPORT ====================

async def send_daily_report(context):
    buy, sell, wait = [], [], []
    for symbol in list(EGX30_STOCKS.keys())[:8]:
        data = await get_stock_data(symbol)
        if "error" not in data:
            s = calculate_signal(data)
            sl_tp = calculate_sl_tp(data, s)
            entry = f"{s['emoji']} *{symbol}* {data['price']:.2f} ({data['change_pct']:+.2f}%)"
            if s["signal"] == "BUY":
                entry += f" SL:{sl_tp['stop_loss']} TP:{sl_tp['take_profit_1']}"
                buy.append(entry)
            elif s["signal"] == "SELL":
                sell.append(entry)
            else:
                wait.append(entry)

    text = f"""📊 *التقرير اليومي - EGX Pulse*
🗓️ {datetime.now().strftime('%Y-%m-%d')} | 10:00 ص

🟢 *شراء ({len(buy)}):*\n{chr(10).join(buy) or 'لا يوجد'}

🔴 *بيع ({len(sell)}):*\n{chr(10).join(sell) or 'لا يوجد'}

🟡 *انتظار ({len(wait)}):*\n{chr(10).join(wait) or 'لا يوجد'}

⚠️ ليس نصيحة استثمارية"""

    for user_id, user_data in context.bot_data.items():
        if chat_id := user_data.get("chat_id"):
            try:
                await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
            except Exception:
                pass


async def manual_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in context.bot_data:
        context.bot_data[user_id] = {}
    context.bot_data[user_id]["chat_id"] = update.effective_chat.id
    msg = await update.message.reply_text("📊 بعمل التقرير...")

    buy, sell, wait = [], [], []
    for symbol in list(EGX30_STOCKS.keys())[:8]:
        data = await get_stock_data(symbol)
        if "error" not in data:
            s = calculate_signal(data)
            sl_tp = calculate_sl_tp(data, s)
            entry = f"{s['emoji']} *{symbol}* {data['price']:.2f} ({data['change_pct']:+.2f}%)"
            if s["signal"] == "BUY":
                entry += f"\n   🛡️SL:{sl_tp['stop_loss']} 🎯TP:{sl_tp['take_profit_1']}"
                buy.append(entry)
            elif s["signal"] == "SELL":
                sell.append(entry)
            else:
                wait.append(entry)

    text = f"""📊 *التقرير اليومي*
🕐 {datetime.now().strftime('%H:%M')} | ✅ مشترك في التقرير اليومي الساعة 10ص

🟢 *شراء ({len(buy)}):*
{chr(10).join(buy) or 'لا يوجد حالياً'}

🔴 *بيع ({len(sell)}):*
{chr(10).join(sell) or 'لا يوجد حالياً'}

🟡 *انتظار ({len(wait)}):*
{chr(10).join(wait) or 'لا يوجد حالياً'}

⚠️ ليس نصيحة استثمارية"""
    await msg.edit_text(text, parse_mode="Markdown")


# ==================== WATCHLIST ====================

async def show_index_prices(msg, stocks_dict, index_name):
    results = []
    for symbol in list(stocks_dict.keys())[:10]:
        data = await get_stock_data(symbol)
        if "error" not in data:
            s = calculate_signal(data)
            ce = "📈" if data['change'] >= 0 else "📉"
            results.append(f"{ce} *{symbol}* {data['price']:.2f} ({data['change_pct']:+.2f}%) {s['emoji']}")
    if not results:
        await msg.edit_text("❌ مش قادر أجيب الأسعار دلوقتي.")
        return
    text = f"📊 *أسعار {index_name}* 🕐 {datetime.now().strftime('%H:%M')}\n\n"
    text += "\n".join(results) + "\n\n🟢شراء 🟡انتظار 🔴بيع\n_/analyze SYMBOL للتحليل_"
    await msg.edit_text(text, parse_mode="Markdown")


async def egx30_prices(update, context):
    msg = await update.message.reply_text("⏳ EGX 30...")
    await show_index_prices(msg, EGX30_STOCKS, "EGX 30")

async def egx70_prices(update, context):
    msg = await update.message.reply_text("⏳ EGX 70...")
    await show_index_prices(msg, EGX70_STOCKS, "EGX 70")

async def egx100_prices(update, context):
    msg = await update.message.reply_text("⏳ EGX 100...")
    await show_index_prices(msg, EGX100_STOCKS, "EGX 100")


async def watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    stocks = context.bot_data.get(user_id, {}).get("watchlist", [])
    if not stocks:
        await update.message.reply_text("📋 قائمة فاضية!\nأضف: /add COMI")
        return
    msg = await update.message.reply_text("⏳ جاري التحميل...")
    results = []
    for symbol in stocks:
        data = await get_stock_data(symbol)
        if "error" not in data:
            s = calculate_signal(data)
            ce = "📈" if data['change'] >= 0 else "📉"
            results.append(f"{ce} *{symbol}* {data['price']:.2f} ({data['change_pct']:+.2f}%) {s['emoji']}")
    await msg.edit_text("⭐ *قائمة المتابعة*\n\n" + "\n".join(results) + "\n\n🟢شراء 🟡انتظار 🔴بيع", parse_mode="Markdown")


async def add_to_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ مثلاً: /add COMI")
        return
    symbol = context.args[0].upper()
    if symbol not in ALL_STOCKS:
        await update.message.reply_text(f"❌ '{symbol}' مش موجود.")
        return
    user_id = str(update.effective_user.id)
    if user_id not in context.bot_data:
        context.bot_data[user_id] = {}
    wl = context.bot_data[user_id].get("watchlist", [])
    if symbol not in wl:
        wl.append(symbol)
        context.bot_data[user_id]["watchlist"] = wl
        await update.message.reply_text(f"✅ تم إضافة {ALL_STOCKS[symbol]} ({symbol})")
    else:
        await update.message.reply_text(f"⚠️ {symbol} موجود بالفعل.")


async def remove_from_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ مثلاً: /remove COMI")
        return
    symbol = context.args[0].upper()
    user_id = str(update.effective_user.id)
    wl = context.bot_data.get(user_id, {}).get("watchlist", [])
    if symbol in wl:
        wl.remove(symbol)
        context.bot_data[user_id]["watchlist"] = wl
        await update.message.reply_text(f"✅ تم حذف {symbol}")
    else:
        await update.message.reply_text(f"❌ {symbol} مش في قائمتك.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """📖 *دليل الاستخدام الكامل*

*📊 تحليل:*
/price COMI - سعر + مؤشرات + SL/TP
/analyze COMI - تحليل يومي + أسبوعي + AI
/compare COMI ETEL - مقارنة سهمين

*📰 أخبار وسيولة:*
/stocknews COMI - أخبار الشركة من Mubasher + AI
/news - أخبار السوق العامة
/liquidity - سيولة السوق + أعلى الأسهم تداولاً

*📈 الأسواق:*
/egx30 | /egx70 | /egx100

*🔔 التنبيهات:*
/alert COMI 80 | /alerts | /delalert COMI

*💼 المحفظة:*
/buy COMI 100 75.5 | /sell COMI 100 80 | /portfolio

*📊 التقارير:*
/report - تقرير فوري + اشتراك يومي 10ص

*⭐ المتابعة:*
/watchlist | /add COMI | /remove COMI

⚠️ للمعلومات الشخصية فقط"""
    await update.message.reply_text(text, parse_mode="Markdown")


# ==================== CALLBACKS ====================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("analyze_"):
        symbol = query.data.replace("analyze_", "")
        await query.edit_message_text("🤖 بحلل...")
        daily, weekly = await asyncio.gather(
            get_stock_data(symbol, "1d", "60d"),
            get_stock_data(symbol, "1wk", "52wk")
        )
        if "error" in daily:
            await query.edit_message_text(f"❌ {daily['error']}")
            return
        ds = calculate_signal(daily)
        ws = calculate_signal(weekly) if "error" not in weekly else {"emoji": "❓", "label": "غير متاح"}
        sl_tp = calculate_sl_tp(daily, ds)
        ai = await analyze_with_ai(daily, ds, weekly)
        reasons = "\n".join([f"  • {r}" for r in ds['reasons']])
        ce = "📈" if daily['change'] >= 0 else "📉"
        text = f"""{ce} *تحليل {daily['name']}* ({symbol})
💰 {daily['price']:.2f} | {daily['change_pct']:+.2f}%
RSI:{daily['rsi']} SMA20:{daily['sma20']} SMA50:{daily['sma50']}
MACD:{daily['macd']} BB:{daily['bb_lower']}↔{daily['bb_upper']}
📅 أسبوعي: {ws['emoji']} {ws['label']}
{ds['emoji']} *{ds['label']}* (Score:{ds['score']}/8)
{reasons}
🛡️SL:{sl_tp['stop_loss']} 🎯TP1:{sl_tp['take_profit_1']} TP2:{sl_tp['take_profit_2']}
⚖️R/R: 1:{sl_tp['risk_reward']}
🤖 {ai}"""
        await query.edit_message_text(text, parse_mode="Markdown")

    elif query.data.startswith("add_"):
        symbol = query.data.replace("add_", "")
        user_id = str(query.from_user.id)
        if user_id not in context.bot_data:
            context.bot_data[user_id] = {}
        wl = context.bot_data[user_id].get("watchlist", [])
        if symbol not in wl:
            wl.append(symbol)
            context.bot_data[user_id]["watchlist"] = wl
            await query.answer(f"✅ تم إضافة {symbol}!", show_alert=True)
        else:
            await query.answer(f"⚠️ {symbol} موجود بالفعل.", show_alert=True)


# ==================== MAIN ====================

def main():
    print("🚀 EGX Pulse Bot v3.0 - جاري التشغيل...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    handlers = [
        ("start", start), ("price", get_price), ("analyze", analyze_stock),
        ("compare", compare_stocks), ("news", market_news),
        ("stocknews", stock_news), ("liquidity", market_liquidity),
        ("egx30", egx30_prices), ("egx70", egx70_prices), ("egx100", egx100_prices),
        ("alert", set_alert), ("alerts", show_alerts), ("delalert", delete_alert),
        ("buy", buy_stock), ("sell", sell_stock), ("portfolio", show_portfolio),
        ("watchlist", watchlist), ("add", add_to_watchlist), ("remove", remove_from_watchlist),
        ("report", manual_report), ("help", help_command),
    ]
    for cmd, handler in handlers:
        app.add_handler(CommandHandler(cmd, handler))
    app.add_handler(CallbackQueryHandler(button_callback))

    # Jobs: تقرير يومي 10ص + تشيك تنبيهات كل 15 دقيقة
    jq = app.job_queue
    jq.run_daily(send_daily_report, time=dtime(hour=8, minute=0))  # 8 UTC = 10 Cairo
    jq.run_repeating(check_alerts, interval=900, first=60)

    print("✅ البوت شغال! جاهز للرسائل...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
