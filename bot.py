"""
EGX Pulse Bot — بوت تحليل البورصة المصرية
Technical Analysis | AI | Alerts | Portfolio | News | Multi-timeframe | SL/TP
"""

import os
import re
import asyncio
import logging
from datetime import datetime, time as dtime

import httpx
import yfinance as yf
from openai import OpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_TELEGRAM_TOKEN_HERE")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_KEY_HERE")
OPENAI_TIMEOUT = 60.0

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

_openai_client = None

def get_openai_client():
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url="https://api.openai.com/v1",
            timeout=OPENAI_TIMEOUT,
        )
    return _openai_client


# ---------------------------------------------------------------------------
# EGX STOCKS DATA
# ---------------------------------------------------------------------------

EGX30_STOCKS = {
    "COMI": "CIB - البنك التجاري الدولي",
    "SWDY": "السويدي إليكتريك",
    "TMGH": "طلعت مصطفى",
    "ETEL": "المصرية للاتصالات",
    "EAST": "إيسترن كومباني",
    "EGAL": "مصر للألومنيوم",
    "ABUK": "أبو قير للأسمدة",
    "QNBE": "بنك قطر الوطني",
    "ALCN": "الإسكندرية للحاويات",
    "EFIH": "إي-فاينانس",
    "FWRY": "فوري",
    "HDBK": "بنك الإسكان والتعمير",
    "ORAS": "أوراسكوم للإنشاء",
    "EMFD": "إعمار مصر",
    "ADIB": "بنك أبو ظبي الإسلامي",
    "HRHO": "EFG هيرميس",
    "JUFO": "جهينة",
    "IRON": "الحديد والصلب المصرية",
    "FERC": "فيركيم مصر",
    "GBCO": "GB كورب",
    "OCDI": "سوديك",
    "EGCH": "الصناعات الكيماوية المصرية",
    "PHDC": "بالم هيلز",
    "CIEB": "كريدي أجريكول مصر",
    "ORHD": "أوراسكوم للتطوير",
}

EGX70_STOCKS = {
    "VLMR": "فالمور هولدينج",
    "EFID": "إيديتا للصناعات الغذائية",
    "BTFH": "بلتون هولدينج",
    "FAIT": "بنك فيصل الإسلامي",
    "CANA": "بنك قناة السويس",
    "SCTS": "قناة السويس للتكنولوجيا",
    "RAYA": "راية هولدينج",
    "MFPC": "مصر للأسمدة",
    "ESRS": "عز للصلب",
    "MNHD": "مدينة نصر للإسكان",
    "SKPC": "سيدي كرير للبتروكيماويات",
    "AMOC": "مصر لتكرير البترول",
    "CLHO": "سيتي إيدج",
    "AMER": "أمر جروب",
    "GTHE": "جي تي إتش",
    "HELI": "هيليوبوليس",
    "ISPH": "آيزيس فارما",
    "BMRA": "بيتا إيجيبت",
    "EKHO": "إيكو للتطوير",
    "OFMD": "أوفمد",
    "POUL": "كايرو بولتري",
    "ORWE": "أوريدو مصر",
}

ALL_STOCKS = {**EGX30_STOCKS, **EGX70_STOCKS}
EGX100_STOCKS = ALL_STOCKS

YF_PERIOD = {"60d": "3mo", "52wk": "1y", "30d": "1mo", "5d": "5d"}
YF_INTERVAL = {"1d": "1d", "1wk": "1wk", "1h": "60m"}


# ---------------------------------------------------------------------------
# TECHNICAL INDICATORS
# ---------------------------------------------------------------------------

def _ema(data, period):
    if len(data) < period:
        return data[-1] if data else 0
    k = 2 / (period + 1)
    v = sum(data[:period]) / period
    for p in data[period:]:
        v = p * k + v * (1 - k)
    return round(v, 2)


def rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50.0
    gains = [max(prices[i] - prices[i - 1], 0) for i in range(1, len(prices))]
    losses = [max(prices[i - 1] - prices[i], 0) for i in range(1, len(prices))]
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    return round(100 - (100 / (1 + avg_gain / avg_loss)), 2)


def sma(prices, period):
    if len(prices) < period:
        return prices[-1] if prices else 0
    return round(sum(prices[-period:]) / period, 2)


def macd(prices):
    if len(prices) < 26:
        return 0, 0, 0
    macd_line = round(_ema(prices, 12) - _ema(prices, 26), 2)
    sig = round(_ema(prices[-9:], 9), 2) if len(prices) >= 9 else macd_line
    hist = round(macd_line - sig, 2)
    return macd_line, sig, hist


def bollinger(prices, period=20):
    if len(prices) < period:
        p = prices[-1] if prices else 0
        return p, p, p
    mid = sum(prices[-period:]) / period
    std = (sum((p - mid) ** 2 for p in prices[-period:]) / period) ** 0.5
    return (
        round(mid + 2 * std, 2),
        round(mid, 2),
        round(mid - 2 * std, 2),
    )


def atr(highs, lows, closes, period=14):
    if len(closes) < period + 1 or not highs or not lows:
        return 0
    n = min(len(closes), len(highs), len(lows))
    trs = [
        max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        for i in range(1, n)
    ]
    return round(sum(trs[-period:]) / period, 2) if trs else 0


# ---------------------------------------------------------------------------
# STOCK DATA FETCHING
# ---------------------------------------------------------------------------

async def fetch_stock_data(symbol: str, interval: str = "1d", range_: str = "60d") -> dict:
    closes, highs, lows, vols = [], [], [], []
    price = prev_close = volume = 0
    period = YF_PERIOD.get(range_, "3mo")
    intv = YF_INTERVAL.get(interval, "1d")

    for host in ["query1", "query2"]:
        try:
            url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{symbol}.CA?interval={interval}&range={range_}"
            async with httpx.AsyncClient(timeout=12) as http:
                r = await http.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                        "Accept": "application/json",
                    },
                )
            if r.status_code != 200:
                continue
            data = r.json()
            result = data.get("chart", {}).get("result", [])
            if not result:
                continue
            meta = result[0].get("meta", {})
            quote = result[0].get("indicators", {}).get("quote", [{}])[0]
            closes = [c for c in quote.get("close", []) if c is not None]
            highs = [h for h in quote.get("high", []) if h is not None]
            lows = [l for l in quote.get("low", []) if l is not None]
            vols = [v for v in quote.get("volume", []) if v is not None]
            if closes:
                price = meta.get("regularMarketPrice", closes[-1])
                prev_close = meta.get("previousClose", closes[-2] if len(closes) > 1 else price)
                volume = meta.get("regularMarketVolume", vols[-1] if vols else 0)
                break
        except Exception:
            continue

    if not closes:
        try:
            ticker = yf.Ticker(f"{symbol}.CA")
            hist = ticker.history(period=period, interval=intv)
            if hist.empty:
                return {"error": f"السهم '{symbol}' مش موجود. جرب: COMI, ETEL, SWDY, HRHO"}
            closes = hist["Close"].tolist()
            highs = hist["High"].tolist()
            lows = hist["Low"].tolist()
            vols = hist["Volume"].tolist()
            price = closes[-1]
            prev_close = closes[-2] if len(closes) > 1 else price
            volume = int(vols[-1]) if vols else 0
        except Exception as e:
            return {"error": f"خطأ في جيب البيانات: {str(e)}"}

    if not closes:
        return {"error": "مفيش بيانات متاحة للسهم ده دلوقتي"}

    change = round(price - prev_close, 2) if prev_close else 0
    change_pct = round((change / prev_close * 100), 2) if prev_close else 0
    avg_vol = int(sum(vols[-20:]) / len(vols[-20:])) if len(vols) >= 20 else (int(sum(vols) / len(vols)) if vols else 0)
    vol_ratio = round(volume / avg_vol, 2) if avg_vol else 1.0

    macd_line, macd_sig, macd_hist = macd(closes)
    bb_u, bb_m, bb_l = bollinger(closes)

    return {
        "symbol": symbol,
        "name": ALL_STOCKS.get(symbol, symbol),
        "price": round(price, 2),
        "prev_close": round(prev_close, 2),
        "change": change,
        "change_pct": change_pct,
        "volume": volume,
        "avg_volume": avg_vol,
        "volume_ratio": vol_ratio,
        "time": datetime.now().strftime("%H:%M:%S"),
        "rsi": rsi(closes),
        "sma20": sma(closes, 20),
        "sma50": sma(closes, 50),
        "macd": macd_line,
        "macd_signal": macd_sig,
        "macd_hist": macd_hist,
        "bb_upper": bb_u,
        "bb_mid": bb_m,
        "bb_lower": bb_l,
        "atr": atr(highs, lows, closes),
        "high_period": round(max(closes), 2),
        "low_period": round(min(closes), 2),
        "closes": closes,
    }


# ---------------------------------------------------------------------------
# SIGNAL & SL/TP
# ---------------------------------------------------------------------------

def compute_signal(data: dict) -> dict:
    if "error" in data:
        return {"signal": "WAIT", "emoji": "🟡", "label": "انتظار", "score": 0, "reasons": []}
    score, reasons = 0, []
    p, r, s20, s50 = data["price"], data["rsi"], data["sma20"], data["sma50"]
    macd_v, macd_s = data["macd"], data["macd_signal"]
    bb_u, bb_l = data["bb_upper"], data["bb_lower"]
    vol_r, ch_pct = data["volume_ratio"], data["change_pct"]

    if r < 30:
        score += 2
        reasons.append(f"RSI={r} 🟢 Oversold")
    elif r < 45:
        score += 1
        reasons.append(f"RSI={r} منطقة شراء")
    elif r > 70:
        score -= 2
        reasons.append(f"RSI={r} 🔴 Overbought")
    elif r > 55:
        score -= 1
        reasons.append(f"RSI={r} ضغط بيع")

    if p > s20 and s20 > s50:
        score += 2
        reasons.append(f"فوق SMA20({s20}) و SMA50({s50}) ✅")
    elif p > s20:
        score += 1
        reasons.append(f"فوق SMA20({s20})")
    elif p < s20 and s20 < s50:
        score -= 2
        reasons.append(f"تحت SMA20({s20}) و SMA50({s50}) ❌")
    elif p < s20:
        score -= 1
        reasons.append(f"تحت SMA20({s20})")

    if macd_v > macd_s and data["macd_hist"] > 0:
        score += 2
        reasons.append("MACD إيجابي ✅")
    elif macd_v < macd_s and data["macd_hist"] < 0:
        score -= 2
        reasons.append("MACD سلبي ❌")

    if p <= bb_l:
        score += 1
        reasons.append(f"عند Bollinger الأدنى ({bb_l})")
    elif p >= bb_u:
        score -= 1
        reasons.append(f"عند Bollinger الأعلى ({bb_u})")

    if vol_r > 1.5:
        if ch_pct > 0:
            score += 1
            reasons.append(f"حجم مرتفع {vol_r}x مع ارتفاع 🔥")
        else:
            score -= 1
            reasons.append(f"حجم مرتفع {vol_r}x مع انخفاض ⚠️")

    if score >= 3:
        return {"signal": "BUY", "emoji": "🟢", "label": "شراء", "score": score, "reasons": reasons}
    if score <= -3:
        return {"signal": "SELL", "emoji": "🔴", "label": "بيع", "score": score, "reasons": reasons}
    return {"signal": "WAIT", "emoji": "🟡", "label": "انتظار", "score": score, "reasons": reasons}


def compute_sl_tp(data: dict, signal: dict) -> dict:
    p = data["price"]
    atr_val = data.get("atr", 0) or p * 0.02
    sig = signal["signal"]
    if sig == "BUY":
        sl = round(p - 1.5 * atr_val, 2)
        tp1, tp2 = round(p + 2.0 * atr_val, 2), round(p + 3.5 * atr_val, 2)
    elif sig == "SELL":
        sl = round(p + 1.5 * atr_val, 2)
        tp1, tp2 = round(p - 2.0 * atr_val, 2), round(p - 3.5 * atr_val, 2)
    else:
        sl = round(p - 1.5 * atr_val, 2)
        tp1, tp2 = round(p + 2.0 * atr_val, 2), round(p + 3.5 * atr_val, 2)
    sl_pct = round(abs(p - sl) / p * 100, 2)
    tp1_pct = round(abs(p - tp1) / p * 100, 2)
    tp2_pct = round(abs(p - tp2) / p * 100, 2)
    rr = round(abs(tp1 - p) / abs(p - sl), 2) if abs(p - sl) > 0 else 0
    return {
        "stop_loss": sl,
        "take_profit_1": tp1,
        "take_profit_2": tp2,
        "sl_pct": sl_pct,
        "tp1_pct": tp1_pct,
        "tp2_pct": tp2_pct,
        "risk_reward": rr,
    }


# ---------------------------------------------------------------------------
# AI
# ---------------------------------------------------------------------------

def _openai_error_message(e: Exception) -> str:
    err = str(e).lower()
    if "connection" in err or "timeout" in err:
        return "❌ فشل الاتصال بـ OpenAI. تأكد من OPENAI_API_KEY والإنترنت."
    if "api_key" in err or "invalid" in err or "auth" in err:
        return "❌ مفتاح OpenAI غير صحيح. راجع platform.openai.com"
    return f"❌ {str(e)}"


def _has_openai_key() -> bool:
    return bool(OPENAI_API_KEY and OPENAI_API_KEY != "YOUR_OPENAI_KEY_HERE")


async def ai_analyze_stock(data: dict, signal: dict, weekly_data: dict = None) -> str:
    if "error" in data:
        return f"❌ {data['error']}"
    weekly_info = ""
    if weekly_data and "error" not in weekly_data:
        ws = compute_signal(weekly_data)
        weekly_info = f"\nأسبوعي: RSI={weekly_data['rsi']} | إشارة={ws['label']}"
    prompt = f"""أنت محلل فني خبير في البورصة المصرية.
اكتب تحليلاً موجزاً (3 جمل فقط) للسهم:
{data['name']} ({data['symbol']}) | السعر: {data['price']} | {data['change_pct']:+.2f}%
RSI: {data['rsi']} | SMA20: {data['sma20']} | SMA50: {data['sma50']}
MACD: {data['macd']} | Bollinger: {data['bb_lower']}↔{data['bb_upper']}
حجم: {data['volume_ratio']}x | الإشارة: {signal['label']} (score: {signal['score']}){weekly_info}
انهِ بـ: ⚠️ ليس نصيحة استثمارية."""
    if not _has_openai_key():
        return "⚠️ تحليل AI غير مفعّل. ضع OPENAI_API_KEY في Variables."
    try:
        client = get_openai_client()
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=250,
            temperature=0.2,
        )
        return r.choices[0].message.content
    except Exception as e:
        return _openai_error_message(e)


async def ai_market_news() -> str:
    if not _has_openai_key():
        return "⚠️ ضع OPENAI_API_KEY في Variables."
    try:
        prompt = """أنت محلل مالي متخصص في البورصة المصرية.
اكتب ملخصاً لأهم 4 عوامل تؤثر على سوق الأسهم المصري حالياً:
الفائدة، العملة، أسعار النفط، وأي أحداث اقتصادية مهمة.
اجعل الرد مختصراً (4-5 جمل). انهِ بـ: ⚠️ للمعلومات فقط."""
        client = get_openai_client()
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.3,
        )
        return r.choices[0].message.content
    except Exception as e:
        return _openai_error_message(e)


async def fetch_stock_news(symbol: str) -> list:
    try:
        url = f"https://english.mubasher.info/markets/EGX/stocks/{symbol}/news"
        async with httpx.AsyncClient(timeout=15) as http:
            r = await http.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            )
        html = r.text
        titles = re.findall(r'class="[^"]*title[^"]*"[^>]*>\s*<[^>]+>\s*([^<]{20,200})', html)
        if not titles:
            titles = re.findall(r'<h\d[^>]*>\s*([A-Z][^<]{20,150})</h\d>', html)
        clean = []
        for t in titles[:5]:
            t = t.strip()
            if len(t) > 20 and symbol not in t and "mubasher" not in t.lower():
                clean.append(t)
        return clean[:4]
    except Exception:
        return []


async def ai_summarize_news(symbol: str, news: list, signal: dict) -> str:
    if not news:
        return "لم يتم العثور على أخبار حديثة."
    if not _has_openai_key():
        return "⚠️ ضع OPENAI_API_KEY في Variables."
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
        client = get_openai_client()
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.2,
        )
        return r.choices[0].message.content
    except Exception as e:
        return _openai_error_message(e)


async def fetch_market_liquidity() -> dict:
    try:
        tasks = [fetch_stock_data(s) for s in list(EGX30_STOCKS.keys())[:15]]
        results = await asyncio.gather(*tasks)
        total_vol = total_turn = 0
        top = []
        for d in results:
            if "error" in d:
                continue
            vol, p = d["volume"], d["price"]
            turn = vol * p
            total_vol += vol
            total_turn += turn
            top.append({
                "symbol": d["symbol"],
                "name": d["name"],
                "volume": vol,
                "turnover": turn,
                "change_pct": d["change_pct"],
                "volume_ratio": d["volume_ratio"],
            })
        top.sort(key=lambda x: x["turnover"], reverse=True)
        return {
            "total_volume": total_vol,
            "total_turnover": total_turn,
            "top_by_volume": top[:5],
            "time": datetime.now().strftime("%H:%M"),
        }
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# COMMAND HANDLERS
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = str(update.effective_user.id)
    if uid not in context.bot_data:
        context.bot_data[uid] = {}
    context.bot_data[uid]["chat_id"] = update.effective_chat.id
    welcome = """🏦 *أهلاً في EGX Pulse Bot!*
📊 RSI | MACD | Bollinger | SMA | ATR | Multi-Timeframe

*تحليل:* /price COMI | /analyze COMI | /compare COMI ETEL | /testapi
*أخبار:* /stocknews COMI | /news | /liquidity
*أسواق:* /egx30 | /egx70 | /egx100
*تنبيهات:* /alert COMI 80 | /alerts | /delalert COMI
*محفظة:* /buy COMI 100 75.5 | /sell COMI 100 80 | /portfolio
*تقارير:* /report | *متابعة:* /watchlist | /add COMI | /remove COMI | /help

⚠️ _للمعلومات فقط - مش نصيحة استثمارية_"""
    await update.message.reply_text(welcome, parse_mode="Markdown")


async def cmd_testapi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = await update.message.reply_text("⏳ جاري التحقق من الاتصال بـ OpenAI...")
    if not _has_openai_key():
        await msg.edit_text(
            "❌ *المفتاح غير موجود*\n\nOPENAI_API_KEY مش مضاف في Variables. ضيفه وعمل Redeploy.",
            parse_mode="Markdown",
        )
        return
    try:
        client = get_openai_client()
        client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "قل مرحبا فقط."}],
            max_tokens=10,
        )
        await msg.edit_text("✅ *الاتصال شغال!* تقدر تستخدم /analyze COMI عادي.", parse_mode="Markdown")
    except Exception as e:
        err = str(e).lower()
        if "connection" in err or "timeout" in err or "connect" in err:
            text = "❌ *فشل الاتصال* — المفتاح موجود لكن الطلب مش واصل. جرب من جهازك أو راجع السيرفر."
        elif "api_key" in err or "invalid" in err or "auth" in err:
            text = "❌ *مفتاح غير صحيح* — اعمل مفتاح جديد من platform.openai.com"
        else:
            text = f"❌ {str(e)}"
        await msg.edit_text(text, parse_mode="Markdown")


async def cmd_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("⚠️ مثلاً: /price COMI")
        return
    symbol = context.args[0].upper()
    if symbol not in ALL_STOCKS:
        await update.message.reply_text(f"❌ '{symbol}' مش موجود.")
        return
    msg = await update.message.reply_text("⏳ بجيب السعر...")
    data = await fetch_stock_data(symbol)
    if "error" in data:
        await msg.edit_text(f"❌ {data['error']}")
        return
    sig = compute_signal(data)
    sl_tp = compute_sl_tp(data, sig)
    ce = "📈" if data["change"] >= 0 else "📉"
    text = f"""{ce} *{data['name']}* ({symbol})
💰 *السعر:* {data['price']:.2f} جنيه | *التغيير:* {data['change']:+.2f} ({data['change_pct']:+.2f}%)
📦 حجم: {data['volume']:,} ({data['volume_ratio']}x)
📉 RSI: {data['rsi']} | SMA20: {data['sma20']} | SMA50: {data['sma50']} | Bollinger: {data['bb_lower']} ↔ {data['bb_upper']}
{sig['emoji']} *الإشارة: {sig['label']}* (Score: {sig['score']}/8)
🛡️ SL: {sl_tp['stop_loss']} ({sl_tp['sl_pct']}% ↓) | 🎯 TP: {sl_tp['take_profit_1']} ({sl_tp['tp1_pct']}% ↑) | ⚖️ R/R: 1:{sl_tp['risk_reward']}
🕐 {data['time']}"""
    kb = [
        [
            InlineKeyboardButton("🤖 تحليل AI كامل", callback_data=f"analyze_{symbol}"),
            InlineKeyboardButton("➕ متابعة", callback_data=f"add_{symbol}"),
        ]
    ]
    await msg.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def cmd_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("⚠️ مثلاً: /analyze COMI")
        return
    symbol = context.args[0].upper()
    if symbol not in ALL_STOCKS:
        await update.message.reply_text(f"❌ '{symbol}' مش موجود.")
        return
    msg = await update.message.reply_text("🤖 بحلل يومي + أسبوعي...")
    daily, weekly = await asyncio.gather(
        fetch_stock_data(symbol, "1d", "60d"),
        fetch_stock_data(symbol, "1wk", "52wk"),
    )
    if "error" in daily:
        await msg.edit_text(f"❌ {daily['error']}")
        return
    ds = compute_signal(daily)
    ws = compute_signal(weekly) if "error" not in weekly else {"emoji": "❓", "label": "غير متاح", "score": 0}
    sl_tp = compute_sl_tp(daily, ds)
    ai_text = await ai_analyze_stock(daily, ds, weekly)
    reasons = "\n".join([f"  • {r}" for r in ds["reasons"]])
    ce = "📈" if daily["change"] >= 0 else "📉"
    text = f"""{ce} *تحليل {daily['name']}* ({symbol})
💰 السعر: {daily['price']:.2f} جنيه | {daily['change_pct']:+.2f}%
📊 RSI: {daily['rsi']} | SMA20: {daily['sma20']} | SMA50: {daily['sma50']} | MACD: {daily['macd']} | BB: {daily['bb_lower']}↔{daily['bb_upper']} | حجم: {daily['volume_ratio']}x
📅 أسبوعي: {ws['emoji']} {ws['label']}
{ds['emoji']} *الإشارة اليومية: {ds['label']}* (Score: {ds['score']}/8)
{reasons}
🛡️ SL: {sl_tp['stop_loss']} ({sl_tp['sl_pct']}%) | 🎯 TP1: {sl_tp['take_profit_1']} TP2: {sl_tp['take_profit_2']} | ⚖️ R/R: 1:{sl_tp['risk_reward']}
🤖 *تحليل AI:*\n{ai_text}"""
    await msg.edit_text(text, parse_mode="Markdown")


async def cmd_compare(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ مثلاً: /compare COMI ETEL")
        return
    s1, s2 = context.args[0].upper(), context.args[1].upper()
    for s in (s1, s2):
        if s not in ALL_STOCKS:
            await update.message.reply_text(f"❌ '{s}' مش موجود.")
            return
    msg = await update.message.reply_text("⚖️ بقارن...")
    d1, d2 = await asyncio.gather(fetch_stock_data(s1), fetch_stock_data(s2))
    if "error" in d1 or "error" in d2:
        await msg.edit_text("❌ خطأ في جيب البيانات.")
        return
    sig1, sig2 = compute_signal(d1), compute_signal(d2)
    winner = s1 if sig1["score"] > sig2["score"] else (s2 if sig2["score"] > sig1["score"] else "تعادل!")
    text = f"""⚖️ *{s1} vs {s2}*
*{s1}* {d1['price']:.2f} ({d1['change_pct']:+.2f}%) {sig1['emoji']} {sig1['label']} (Score: {sig1['score']}/8)
*{s2}* {d2['price']:.2f} ({d2['change_pct']:+.2f}%) {sig2['emoji']} {sig2['label']} (Score: {sig2['score']}/8)
RSI: {d1['rsi']} / {d2['rsi']} | SMA20: {d1['sma20']} / {d2['sma20']} | MACD: {d1['macd']} / {d2['macd']} | Vol: {d1['volume_ratio']}x / {d2['volume_ratio']}x
🏆 *الأفضل:* {winner}"""
    await msg.edit_text(text, parse_mode="Markdown")


async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = await update.message.reply_text("📰 بجيب أخبار السوق...")
    news = await ai_market_news()
    await msg.edit_text(f"📰 *أخبار السوق*\n🕐 {datetime.now().strftime('%H:%M')}\n\n{news}", parse_mode="Markdown")


async def cmd_stocknews(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("⚠️ مثلاً: /stocknews COMI")
        return
    symbol = context.args[0].upper()
    if symbol not in ALL_STOCKS:
        await update.message.reply_text(f"❌ '{symbol}' مش موجود.")
        return
    msg = await update.message.reply_text(f"📰 بجيب أخبار {ALL_STOCKS[symbol]}...")
    news, data = await asyncio.gather(fetch_stock_news(symbol), fetch_stock_data(symbol))
    sig = compute_signal(data) if "error" not in data else {"label": "غير متاح", "score": 0, "emoji": "🟡"}
    ai_summary = await ai_summarize_news(symbol, news, sig)
    news_txt = "\n".join([f"• {n}" for n in news]) if news else "لم يتم العثور على أخبار حديثة على Mubasher"
    price_line = ""
    if "error" not in data:
        ce = "📈" if data["change"] >= 0 else "📉"
        price_line = f"\n{ce} السعر: {data['price']:.2f} ({data['change_pct']:+.2f}%) {sig.get('emoji', '')}"
    text = f"📰 *أخبار {ALL_STOCKS[symbol]}* ({symbol}){price_line}\n\n*أخبار Mubasher:*\n{news_txt}\n\n🤖 *تحليل AI:*\n{ai_summary}"
    await msg.edit_text(text, parse_mode="Markdown")


async def cmd_liquidity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = await update.message.reply_text("💧 بجيب السيولة...")
    liq = await fetch_market_liquidity()
    if "error" in liq:
        await msg.edit_text(f"❌ {liq['error']}")
        return
    total_m = liq["total_turnover"] / 1_000_000
    status = "🔥 سوق نشيط جداً" if total_m > 500 else ("✅ سوق طبيعي" if total_m > 200 else "😴 سوق هادئ")
    lines = []
    for s in liq["top_by_volume"]:
        ce = "📈" if s["change_pct"] >= 0 else "📉"
        lines.append(f"{ce} *{s['symbol']}* {s['turnover']/1_000_000:.1f}M جنيه | {s['volume']:,} سهم ({s['volume_ratio']}x)")
    text = f"""💧 *سيولة السوق* 🕐 {liq['time']} | {status}
📊 إجمالي: {liq['total_volume']:,} سهم | {total_m:.1f} مليون جنيه
🏆 الأعلى تداولاً:\n""" + "\n".join(lines)
    await msg.edit_text(text, parse_mode="Markdown")


async def cmd_alert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    uid = str(update.effective_user.id)
    if uid not in context.bot_data:
        context.bot_data[uid] = {}
    if "alerts" not in context.bot_data[uid]:
        context.bot_data[uid]["alerts"] = {}
    context.bot_data[uid]["alerts"][symbol] = {"target": target, "chat_id": update.effective_chat.id}
    await update.message.reply_text(f"🔔 تم! {ALL_STOCKS[symbol]} ({symbol}) هيتبعتلك لما يوصل {target:.2f} جنيه")


async def cmd_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    alerts = context.bot_data.get(str(update.effective_user.id), {}).get("alerts", {})
    if not alerts:
        await update.message.reply_text("🔔 مفيش تنبيهات. /alert COMI 80")
        return
    text = "🔔 *تنبيهاتك:*\n\n" + "\n".join([f"• *{s}* → {i['target']:.2f} جنيه" for s, i in alerts.items()]) + "\n\nلحذف: /delalert COMI"
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_delalert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("⚠️ مثلاً: /delalert COMI")
        return
    symbol = context.args[0].upper()
    uid = str(update.effective_user.id)
    alerts = context.bot_data.get(uid, {}).get("alerts", {})
    if symbol in alerts:
        del context.bot_data[uid]["alerts"][symbol]
        await update.message.reply_text(f"✅ تم حذف تنبيه {symbol}")
    else:
        await update.message.reply_text(f"❌ مفيش تنبيه لـ {symbol}")


async def job_check_alerts(context) -> None:
    for uid, ud in context.bot_data.items():
        for symbol, info in list(ud.get("alerts", {}).items()):
            data = await fetch_stock_data(symbol)
            if "error" in data:
                continue
            if abs(data["price"] - info["target"]) / info["target"] <= 0.01:
                sig = compute_signal(data)
                await context.bot.send_message(
                    chat_id=info["chat_id"],
                    text=f"🔔 *تنبيه!* {data['name']} ({symbol}) 💰 {data['price']:.2f} | 🎯 {info['target']:.2f} {sig['emoji']} {sig['label']}",
                    parse_mode="Markdown",
                )
                del context.bot_data[uid]["alerts"][symbol]


async def cmd_buy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    uid = str(update.effective_user.id)
    if uid not in context.bot_data:
        context.bot_data[uid] = {}
    if "portfolio" not in context.bot_data[uid]:
        context.bot_data[uid]["portfolio"] = {}
    pf = context.bot_data[uid]["portfolio"]
    if symbol in pf:
        oq, op = pf[symbol]["qty"], pf[symbol]["avg_price"]
        nq = oq + qty
        navg = round((oq * op + qty * price) / nq, 2)
        pf[symbol] = {"qty": nq, "avg_price": navg}
        await update.message.reply_text(f"✅ تم الإضافة! {symbol} +{qty:.0f} سهم | متوسط جديد: {navg:.2f}")
    else:
        pf[symbol] = {"qty": qty, "avg_price": price}
        await update.message.reply_text(f"✅ تم الإضافة! {symbol} {qty:.0f} × {price:.2f} = {qty*price:.2f} جنيه")


async def cmd_sell(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 3:
        await update.message.reply_text("⚠️ مثلاً: /sell COMI 100 80")
        return
    symbol = context.args[0].upper()
    try:
        qty, sell_price = float(context.args[1]), float(context.args[2])
    except ValueError:
        await update.message.reply_text("❌ الكمية والسعر لازم أرقام")
        return
    uid = str(update.effective_user.id)
    pf = context.bot_data.get(uid, {}).get("portfolio", {})
    if symbol not in pf:
        await update.message.reply_text(f"❌ {symbol} مش في محفظتك.")
        return
    avg = pf[symbol]["avg_price"]
    profit = round((sell_price - avg) * qty, 2)
    pct = round((sell_price - avg) / avg * 100, 2)
    em = "🟢" if profit >= 0 else "🔴"
    rem = pf[symbol]["qty"] - qty
    if rem <= 0:
        del context.bot_data[uid]["portfolio"][symbol]
        status = "تم بيع كل الأسهم ✅"
    else:
        context.bot_data[uid]["portfolio"][symbol]["qty"] = rem
        status = f"متبقي: {rem:.0f} سهم"
    await update.message.reply_text(
        f"{em} *صفقة بيع* {symbol}\nشراء: {avg:.2f} | بيع: {sell_price:.2f}\nالربح: {profit:+.2f} ({pct:+.2f}%)\n{status}",
        parse_mode="Markdown",
    )


async def cmd_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pf = context.bot_data.get(str(update.effective_user.id), {}).get("portfolio", {})
    if not pf:
        await update.message.reply_text("💼 محفظتك فاضية! /buy COMI 100 75.5")
        return
    msg = await update.message.reply_text("💼 بحسب المحفظة...")
    total_inv = total_cur = 0
    lines = []
    for symbol, info in pf.items():
        data = await fetch_stock_data(symbol)
        if "error" in data:
            continue
        cur = data["price"]
        inv = info["qty"] * info["avg_price"]
        val = info["qty"] * cur
        profit = val - inv
        pct = (profit / inv * 100) if inv else 0
        total_inv += inv
        total_cur += val
        e = "🟢" if profit >= 0 else "🔴"
        lines.append(f"{e} *{symbol}* × {info['qty']:.0f} | {info['avg_price']:.2f} → {cur:.2f} | {profit:+.2f} ({pct:+.2f}%)")
    tp = total_cur - total_inv
    tpct = (tp / total_inv * 100) if total_inv else 0
    te = "🟢" if tp >= 0 else "🔴"
    text = "💼 *محفظتك*\n\n" + "\n\n".join(lines) + f"\n\n{'─'*20}\n{te} الإجمالي: رأس المال {total_inv:,.2f} | القيمة الآن {total_cur:,.2f} | ربح/خسارة {tp:+,.2f} ({tpct:+.2f}%)"
    await msg.edit_text(text, parse_mode="Markdown")


async def job_daily_report(context) -> None:
    buy, sell, wait = [], [], []
    for symbol in list(EGX30_STOCKS.keys())[:8]:
        data = await fetch_stock_data(symbol)
        if "error" in data:
            continue
        s = compute_signal(data)
        sl_tp = compute_sl_tp(data, s)
        entry = f"{s['emoji']} *{symbol}* {data['price']:.2f} ({data['change_pct']:+.2f}%)"
        if s["signal"] == "BUY":
            entry += f" SL:{sl_tp['stop_loss']} TP:{sl_tp['take_profit_1']}"
            buy.append(entry)
        elif s["signal"] == "SELL":
            sell.append(entry)
        else:
            wait.append(entry)
    text = f"""📊 *التقرير اليومي - EGX Pulse* 🗓️ {datetime.now().strftime('%Y-%m-%d')} 10:00 ص
🟢 شراء ({len(buy)}):\n{chr(10).join(buy) or 'لا يوجد'}
🔴 بيع ({len(sell)}):\n{chr(10).join(sell) or 'لا يوجد'}
🟡 انتظار ({len(wait)}):\n{chr(10).join(wait) or 'لا يوجد'}
⚠️ ليس نصيحة استثمارية"""
    for uid, ud in context.bot_data.items():
        if cid := ud.get("chat_id"):
            try:
                await context.bot.send_message(chat_id=cid, text=text, parse_mode="Markdown")
            except Exception:
                pass


async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = str(update.effective_user.id)
    if uid not in context.bot_data:
        context.bot_data[uid] = {}
    context.bot_data[uid]["chat_id"] = update.effective_chat.id
    msg = await update.message.reply_text("📊 بعمل التقرير...")
    buy, sell, wait = [], [], []
    for symbol in list(EGX30_STOCKS.keys())[:8]:
        data = await fetch_stock_data(symbol)
        if "error" in data:
            continue
        s = compute_signal(data)
        sl_tp = compute_sl_tp(data, s)
        entry = f"{s['emoji']} *{symbol}* {data['price']:.2f} ({data['change_pct']:+.2f}%)"
        if s["signal"] == "BUY":
            entry += f"\n   🛡️SL:{sl_tp['stop_loss']} 🎯TP:{sl_tp['take_profit_1']}"
            buy.append(entry)
        elif s["signal"] == "SELL":
            sell.append(entry)
        else:
            wait.append(entry)
    text = f"""📊 *التقرير اليومي* 🕐 {datetime.now().strftime('%H:%M')} | اشتراك يومي 10ص
🟢 شراء:\n{chr(10).join(buy) or 'لا يوجد'}
🔴 بيع:\n{chr(10).join(sell) or 'لا يوجد'}
🟡 انتظار:\n{chr(10).join(wait) or 'لا يوجد'}
⚠️ ليس نصيحة استثمارية"""
    await msg.edit_text(text, parse_mode="Markdown")


async def _show_index(update, context, stocks_dict, index_name) -> None:
    msg = await update.message.reply_text(f"⏳ {index_name}...")
    results = []
    for symbol in list(stocks_dict.keys())[:10]:
        data = await fetch_stock_data(symbol)
        if "error" not in data:
            s = compute_signal(data)
            ce = "📈" if data["change"] >= 0 else "📉"
            results.append(f"{ce} *{symbol}* {data['price']:.2f} ({data['change_pct']:+.2f}%) {s['emoji']}")
    if not results:
        await msg.edit_text("❌ مش قادر أجيب الأسعار دلوقتي.")
        return
    await msg.edit_text(
        f"📊 *{index_name}* 🕐 {datetime.now().strftime('%H:%M')}\n\n" + "\n".join(results) + "\n\n_/analyze SYMBOL للتحليل_",
        parse_mode="Markdown",
    )


async def cmd_egx30(update, context):
    await _show_index(update, context, EGX30_STOCKS, "EGX 30")


async def cmd_egx70(update, context):
    await _show_index(update, context, EGX70_STOCKS, "EGX 70")


async def cmd_egx100(update, context):
    await _show_index(update, context, EGX100_STOCKS, "EGX 100")


async def cmd_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    wl = context.bot_data.get(str(update.effective_user.id), {}).get("watchlist", [])
    if not wl:
        await update.message.reply_text("📋 قائمة فاضية! /add COMI")
        return
    msg = await update.message.reply_text("⏳ جاري التحميل...")
    lines = []
    for symbol in wl:
        data = await fetch_stock_data(symbol)
        if "error" not in data:
            s = compute_signal(data)
            ce = "📈" if data["change"] >= 0 else "📉"
            lines.append(f"{ce} *{symbol}* {data['price']:.2f} ({data['change_pct']:+.2f}%) {s['emoji']}")
    await msg.edit_text("⭐ *قائمة المتابعة*\n\n" + "\n".join(lines or ["لا يوجد"]), parse_mode="Markdown")


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("⚠️ مثلاً: /add COMI")
        return
    symbol = context.args[0].upper()
    if symbol not in ALL_STOCKS:
        await update.message.reply_text(f"❌ '{symbol}' مش موجود.")
        return
    uid = str(update.effective_user.id)
    if uid not in context.bot_data:
        context.bot_data[uid] = {}
    wl = context.bot_data[uid].get("watchlist", [])
    if symbol not in wl:
        wl.append(symbol)
        context.bot_data[uid]["watchlist"] = wl
        await update.message.reply_text(f"✅ تم إضافة {ALL_STOCKS[symbol]} ({symbol})")
    else:
        await update.message.reply_text(f"⚠️ {symbol} موجود بالفعل.")


async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("⚠️ مثلاً: /remove COMI")
        return
    symbol = context.args[0].upper()
    uid = str(update.effective_user.id)
    wl = context.bot_data.get(uid, {}).get("watchlist", [])
    if symbol in wl:
        wl.remove(symbol)
        context.bot_data[uid]["watchlist"] = wl
        await update.message.reply_text(f"✅ تم حذف {symbol}")
    else:
        await update.message.reply_text(f"❌ {symbol} مش في قائمتك.")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = """📖 *دليل الاستخدام*
/price COMI | /analyze COMI | /compare COMI ETEL | /testapi
/stocknews COMI | /news | /liquidity
/egx30 | /egx70 | /egx100
/alert COMI 80 | /alerts | /delalert COMI
/buy COMI 100 75.5 | /sell COMI 100 80 | /portfolio
/report | /watchlist | /add COMI | /remove COMI
⚠️ للمعلومات الشخصية فقط"""
    await update.message.reply_text(text, parse_mode="Markdown")


# ---------------------------------------------------------------------------
# CALLBACKS (INLINE BUTTONS)
# ---------------------------------------------------------------------------

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if query.data.startswith("analyze_"):
        symbol = query.data.replace("analyze_", "")
        await query.edit_message_text("🤖 بحلل...")
        daily, weekly = await asyncio.gather(
            fetch_stock_data(symbol, "1d", "60d"),
            fetch_stock_data(symbol, "1wk", "52wk"),
        )
        if "error" in daily:
            await query.edit_message_text(f"❌ {daily['error']}")
            return
        ds = compute_signal(daily)
        ws = compute_signal(weekly) if "error" not in weekly else {"emoji": "❓", "label": "غير متاح"}
        sl_tp = compute_sl_tp(daily, ds)
        ai_text = await ai_analyze_stock(daily, ds, weekly)
        reasons = "\n".join([f"  • {r}" for r in ds["reasons"]])
        ce = "📈" if daily["change"] >= 0 else "📉"
        text = f"""{ce} *{daily['name']}* ({symbol}) 💰 {daily['price']:.2f} | {daily['change_pct']:+.2f}%
RSI:{daily['rsi']} SMA20:{daily['sma20']} SMA50:{daily['sma50']} MACD:{daily['macd']} BB:{daily['bb_lower']}↔{daily['bb_upper']}
📅 أسبوعي: {ws['emoji']} {ws['label']} | {ds['emoji']} *{ds['label']}* (Score:{ds['score']}/8)
{reasons}
🛡️SL:{sl_tp['stop_loss']} 🎯TP1:{sl_tp['take_profit_1']} TP2:{sl_tp['take_profit_2']} ⚖️R/R: 1:{sl_tp['risk_reward']}
🤖 {ai_text}"""
        await query.edit_message_text(text, parse_mode="Markdown")
    elif query.data.startswith("add_"):
        symbol = query.data.replace("add_", "")
        uid = str(query.from_user.id)
        if uid not in context.bot_data:
            context.bot_data[uid] = {}
        wl = context.bot_data[uid].get("watchlist", [])
        if symbol not in wl:
            wl.append(symbol)
            context.bot_data[uid]["watchlist"] = wl
            await query.answer("✅ تم إضافة " + symbol + "!", show_alert=True)
        else:
            await query.answer(symbol + " موجود بالفعل.", show_alert=True)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    print("🚀 EGX Pulse Bot - جاري التشغيل...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    handlers = [
        ("start", cmd_start),
        ("testapi", cmd_testapi),
        ("price", cmd_price),
        ("analyze", cmd_analyze),
        ("compare", cmd_compare),
        ("news", cmd_news),
        ("stocknews", cmd_stocknews),
        ("liquidity", cmd_liquidity),
        ("egx30", cmd_egx30),
        ("egx70", cmd_egx70),
        ("egx100", cmd_egx100),
        ("alert", cmd_alert),
        ("alerts", cmd_alerts),
        ("delalert", cmd_delalert),
        ("buy", cmd_buy),
        ("sell", cmd_sell),
        ("portfolio", cmd_portfolio),
        ("watchlist", cmd_watchlist),
        ("add", cmd_add),
        ("remove", cmd_remove),
        ("report", cmd_report),
        ("help", cmd_help),
    ]
    for cmd, handler in handlers:
        app.add_handler(CommandHandler(cmd, handler))
    app.add_handler(CallbackQueryHandler(on_callback))
    jq = app.job_queue
    jq.run_daily(job_daily_report, time=dtime(hour=8, minute=0))
    jq.run_repeating(job_check_alerts, interval=900, first=60)
    print("✅ البوت شغال!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
