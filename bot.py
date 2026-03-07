"""
🤖 EGX Stock Analysis Telegram Bot - Enhanced Version
بيجيب أسعار البورصة المصرية ويحللها بـ AI + مؤشرات فنية حقيقية
"""

import os
import asyncio
import logging
from datetime import datetime
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from openai import OpenAI

# ==================== CONFIG ====================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_TELEGRAM_TOKEN_HERE")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_KEY_HERE")

client = OpenAI(api_key=OPENAI_API_KEY)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ==================== EGX 30 & 70 STOCKS ====================
EGX30_STOCKS = {
    "COMI": "CIB - البنك التجاري الدولي",
    "HRHO": "هيرميس",
    "ETEL": "المصرية للاتصالات",
    "OCDI": "أوراسكوم للإنشاء",
    "SWDY": "السويدي إليكتريك",
    "ESRS": "عز للصلب",
    "ABUK": "أبو قير للأسمدة",
    "EAST": "إيسترن",
    "MNHD": "مدينة نصر للإسكان",
    "SKPC": "سيدي كرير للبتروكيماويات",
    "AMOC": "مصر لتكرير البترول",
    "PHDC": "بالم هيلز",
    "CLHO": "سيتي إيدج",
    "JUFO": "جهينة",
    "EGCH": "إيجيكم",
}

EGX70_STOCKS = {
    "AMER": "أمر جروب",
    "BMRA": "بيتا إيجيبت",
    "BTFN": "بنك الاستثمار",
    "EKHO": "إيكو للتطوير",
    "GTHE": "جي تي إتش",
    "HELI": "هيليوبوليس",
    "ISPH": "آيزيس",
    "KABO": "كابو",
    "MFPC": "مصر للمستحضرات",
    "OFMD": "أوفمد",
}

ALL_STOCKS = {**EGX30_STOCKS, **EGX70_STOCKS}


# ==================== TECHNICAL INDICATORS ====================

def calculate_rsi(prices: list, period: int = 14) -> float:
    """حساب RSI"""
    if len(prices) < period + 1:
        return 50.0
    
    gains, losses = [], []
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def calculate_sma(prices: list, period: int) -> float:
    """حساب Simple Moving Average"""
    if len(prices) < period:
        return prices[-1] if prices else 0
    return round(sum(prices[-period:]) / period, 2)


def calculate_macd(prices: list):
    """حساب MACD"""
    def ema(data, period):
        if len(data) < period:
            return data[-1] if data else 0
        k = 2 / (period + 1)
        ema_val = sum(data[:period]) / period
        for price in data[period:]:
            ema_val = price * k + ema_val * (1 - k)
        return round(ema_val, 2)

    if len(prices) < 26:
        return 0, 0, 0

    ema12 = ema(prices, 12)
    ema26 = ema(prices, 26)
    macd_line = round(ema12 - ema26, 2)
    signal = round(ema(prices[-9:], 9), 2) if len(prices) >= 9 else macd_line
    histogram = round(macd_line - signal, 2)
    return macd_line, signal, histogram


def calculate_bollinger_bands(prices: list, period: int = 20):
    """حساب Bollinger Bands"""
    if len(prices) < period:
        p = prices[-1] if prices else 0
        return p, p, p

    sma = sum(prices[-period:]) / period
    variance = sum((p - sma) ** 2 for p in prices[-period:]) / period
    std = variance ** 0.5
    upper = round(sma + 2 * std, 2)
    lower = round(sma - 2 * std, 2)
    return round(upper, 2), round(sma, 2), round(lower, 2)


# ==================== GET STOCK DATA WITH HISTORY ====================
async def get_stock_data(symbol: str) -> dict:
    """بيجيب سعر السهم + تاريخ الأسعار للمؤشرات الفنية"""
    try:
        yahoo_symbol = f"{symbol}.CA"
        # بناخد بيانات آخر 60 يوم عشان نحسب المؤشرات
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?interval=1d&range=60d"

        async with httpx.AsyncClient(timeout=15) as http:
            response = await http.get(url, headers={"User-Agent": "Mozilla/5.0"})
            data = response.json()

        result = data.get("chart", {}).get("result", [])
        if not result:
            return {"error": "السهم مش موجود أو السوق مقفول"}

        meta = result[0].get("meta", {})
        closes_raw = result[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
        volumes_raw = result[0].get("indicators", {}).get("quote", [{}])[0].get("volume", [])

        # تنظيف القيم الفاضية
        closes = [c for c in closes_raw if c is not None]
        volumes = [v for v in volumes_raw if v is not None]

        if not closes:
            return {"error": "مفيش بيانات تاريخية"}

        price = meta.get("regularMarketPrice", closes[-1])
        prev_close = meta.get("previousClose", closes[-2] if len(closes) > 1 else price)
        change = price - prev_close if prev_close else 0
        change_pct = (change / prev_close * 100) if prev_close else 0
        volume = meta.get("regularMarketVolume", volumes[-1] if volumes else 0)

        # ==================== حساب المؤشرات ====================
        rsi = calculate_rsi(closes)
        sma20 = calculate_sma(closes, 20)
        sma50 = calculate_sma(closes, 50)
        macd_line, signal_line, histogram = calculate_macd(closes)
        bb_upper, bb_mid, bb_lower = calculate_bollinger_bands(closes)

        # متوسط حجم التداول (20 يوم)
        avg_volume = int(sum(volumes[-20:]) / len(volumes[-20:])) if volumes else 0
        volume_ratio = round(volume / avg_volume, 2) if avg_volume else 1.0

        # أعلى وأدنى سعر (52 week = آخر 60 يوم هنا)
        high_52 = round(max(closes), 2)
        low_52 = round(min(closes), 2)

        return {
            "symbol": symbol,
            "name": ALL_STOCKS.get(symbol, symbol),
            "price": round(price, 2),
            "prev_close": round(prev_close, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
            "volume": volume,
            "avg_volume": avg_volume,
            "volume_ratio": volume_ratio,
            "currency": "EGP",
            "time": datetime.now().strftime("%H:%M:%S"),
            # المؤشرات الفنية
            "rsi": rsi,
            "sma20": sma20,
            "sma50": sma50,
            "macd": macd_line,
            "macd_signal": signal_line,
            "macd_hist": histogram,
            "bb_upper": bb_upper,
            "bb_mid": bb_mid,
            "bb_lower": bb_lower,
            "high_60d": high_52,
            "low_60d": low_52,
            "closes_history": closes[-5:],  # آخر 5 إغلاقات
        }

    except Exception as e:
        return {"error": str(e)}


# ==================== SIGNAL ENGINE ====================
def calculate_signal(data: dict) -> dict:
    """بيحسب إشارة Buy/Sell/Wait بناءً على المؤشرات الفنية"""
    if "error" in data:
        return {"signal": "WAIT", "score": 0, "reasons": []}

    score = 0
    reasons = []

    price = data["price"]
    rsi = data["rsi"]
    sma20 = data["sma20"]
    sma50 = data["sma50"]
    macd = data["macd"]
    macd_signal = data["macd_signal"]
    bb_upper = data["bb_upper"]
    bb_lower = data["bb_lower"]
    volume_ratio = data["volume_ratio"]
    change_pct = data["change_pct"]

    # --- RSI ---
    if rsi < 30:
        score += 2
        reasons.append(f"RSI={rsi} (oversold - فرصة شراء)")
    elif rsi < 45:
        score += 1
        reasons.append(f"RSI={rsi} (منطقة شراء)")
    elif rsi > 70:
        score -= 2
        reasons.append(f"RSI={rsi} (overbought - خطر بيع)")
    elif rsi > 55:
        score -= 1
        reasons.append(f"RSI={rsi} (ضغط بيع محتمل)")

    # --- Moving Averages ---
    if price > sma20 and sma20 > sma50:
        score += 2
        reasons.append(f"السعر فوق SMA20({sma20}) و SMA50({sma50}) ✅")
    elif price > sma20:
        score += 1
        reasons.append(f"السعر فوق SMA20({sma20})")
    elif price < sma20 and sma20 < sma50:
        score -= 2
        reasons.append(f"السعر تحت SMA20({sma20}) و SMA50({sma50}) ❌")
    elif price < sma20:
        score -= 1
        reasons.append(f"السعر تحت SMA20({sma20})")

    # --- MACD ---
    if macd > macd_signal and data["macd_hist"] > 0:
        score += 2
        reasons.append(f"MACD إيجابي ({macd} > {macd_signal}) ✅")
    elif macd < macd_signal and data["macd_hist"] < 0:
        score -= 2
        reasons.append(f"MACD سلبي ({macd} < {macd_signal}) ❌")

    # --- Bollinger Bands ---
    if price <= bb_lower:
        score += 1
        reasons.append(f"السعر عند الحد الأدنى لـ Bollinger ({bb_lower})")
    elif price >= bb_upper:
        score -= 1
        reasons.append(f"السعر عند الحد الأعلى لـ Bollinger ({bb_upper})")

    # --- Volume ---
    if volume_ratio > 1.5:
        if change_pct > 0:
            score += 1
            reasons.append(f"حجم تداول مرتفع {volume_ratio}x مع ارتفاع السعر 🔥")
        else:
            score -= 1
            reasons.append(f"حجم تداول مرتفع {volume_ratio}x مع انخفاض السعر ⚠️")

    # --- Final Signal ---
    if score >= 3:
        signal = "BUY"
        emoji = "🟢"
        label = "شراء"
    elif score <= -3:
        signal = "SELL"
        emoji = "🔴"
        label = "بيع"
    else:
        signal = "WAIT"
        emoji = "🟡"
        label = "انتظار"

    return {
        "signal": signal,
        "emoji": emoji,
        "label": label,
        "score": score,
        "reasons": reasons,
    }


# ==================== AI ANALYSIS ====================
async def analyze_with_ai(data: dict, signal: dict) -> str:
    """بيبعت المؤشرات الفنية لـ ChatGPT"""
    if "error" in data:
        return f"❌ مش قادر أحلل: {data['error']}"

    prompt = f"""أنت محلل مالي خبير في البورصة المصرية (EGX).
بناءً على المؤشرات الفنية التالية، اكتب تحليلاً موجزاً (3 جمل فقط):

السهم: {data['name']} ({data['symbol']})
السعر: {data['price']} جنيه | التغيير: {data['change_pct']:+.2f}%
RSI: {data['rsi']} | SMA20: {data['sma20']} | SMA50: {data['sma50']}
MACD: {data['macd']} | Signal: {data['macd_signal']}
Bollinger: أعلى={data['bb_upper']} | أدنى={data['bb_lower']}
حجم التداول: {data['volume_ratio']}x المتوسط
الإشارة المحسوبة: {signal['label']} (score: {signal['score']})

التحليل يجب أن يكون:
1. تأكيد أو نقد للإشارة بناءً على المؤشرات
2. أهم نقطة دعم أو مقاومة
3. تحذير أو ملاحظة مهمة

لا تذكر أنك AI. اكتب كمحلل فني متخصص. انهِ دائماً بـ: ⚠️ ليس نصيحة استثمارية."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=250,
            temperature=0.2,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ خطأ في التحليل: {str(e)}"


# ==================== TELEGRAM COMMANDS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome = """🏦 *أهلاً في بوت البورصة المصرية!*

أنا بحلل أسهم EGX 30 و EGX 70 بمؤشرات فنية حقيقية:
📊 RSI | Moving Averages | MACD | Bollinger Bands

*الأوامر:*
/price COMI - سعر السهم
/analyze COMI - تحليل فني كامل + AI
/egx30 - أسعار EGX 30
/watchlist - قائمة المتابعة
/add COMI - أضف للمتابعة
/remove COMI - احذف من المتابعة
/help - المساعدة

⚠️ _التحليل للمعلومات الشخصية فقط وليس نصيحة استثمارية_"""
    await update.message.reply_text(welcome, parse_mode="Markdown")


async def get_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ مثلاً:\n/price COMI")
        return

    symbol = context.args[0].upper()
    if symbol not in ALL_STOCKS:
        await update.message.reply_text(f"❌ السهم '{symbol}' مش موجود.\nاستخدم /egx30 للقائمة.")
        return

    msg = await update.message.reply_text("⏳ بجيب السعر...")
    data = await get_stock_data(symbol)

    if "error" in data:
        await msg.edit_text(f"❌ خطأ: {data['error']}")
        return

    signal = calculate_signal(data)
    change_emoji = "📈" if data['change'] >= 0 else "📉"

    text = f"""{change_emoji} *{data['name']}* ({data['symbol']})

💰 *السعر:* {data['price']:.2f} جنيه
📊 *التغيير:* {data['change']:+.2f} ({data['change_pct']:+.2f}%)
📦 *حجم التداول:* {data['volume']:,} ({data['volume_ratio']}x المتوسط)

📉 *مؤشرات فنية:*
• RSI: {data['rsi']}
• SMA20: {data['sma20']} | SMA50: {data['sma50']}
• Bollinger: {data['bb_lower']} ↔ {data['bb_upper']}

{signal['emoji']} *الإشارة: {signal['label']}*

🕐 {data['time']}"""

    keyboard = [[
        InlineKeyboardButton("🤖 تحليل AI كامل", callback_data=f"analyze_{symbol}"),
        InlineKeyboardButton("➕ متابعة", callback_data=f"add_{symbol}")
    ]]
    await msg.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


async def analyze_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ مثلاً:\n/analyze COMI")
        return

    symbol = context.args[0].upper()
    if symbol not in ALL_STOCKS:
        await update.message.reply_text(f"❌ السهم '{symbol}' مش موجود.")
        return

    msg = await update.message.reply_text("🤖 بحلل المؤشرات الفنية... ثانية!")

    data = await get_stock_data(symbol)
    if "error" in data:
        await msg.edit_text(f"❌ خطأ: {data['error']}")
        return

    signal = calculate_signal(data)
    ai_analysis = await analyze_with_ai(data, signal)

    change_emoji = "📈" if data['change'] >= 0 else "📉"
    reasons_text = "\n".join([f"  • {r}" for r in signal['reasons']])

    text = f"""{change_emoji} *تحليل {data['name']}* ({data['symbol']})

💰 *السعر:* {data['price']:.2f} جنيه | {data['change_pct']:+.2f}%

📊 *المؤشرات الفنية:*
• RSI: {data['rsi']} {'🔴 Overbought' if data['rsi'] > 70 else '🟢 Oversold' if data['rsi'] < 30 else '🟡 محايد'}
• SMA20: {data['sma20']} | SMA50: {data['sma50']}
• MACD: {data['macd']} | Signal: {data['macd_signal']}
• Bollinger: {data['bb_lower']} ↔ {data['bb_upper']}
• حجم التداول: {data['volume_ratio']}x المتوسط

{signal['emoji']} *الإشارة: {signal['label']}* (Score: {signal['score']}/8)
{reasons_text}

🤖 *تحليل AI:*
{ai_analysis}"""

    await msg.edit_text(text, parse_mode="Markdown")


async def egx30_prices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ بجيب أسعار EGX 30 + إشارات...")

    results = []
    for symbol in list(EGX30_STOCKS.keys())[:8]:
        data = await get_stock_data(symbol)
        if "error" not in data:
            signal = calculate_signal(data)
            change_emoji = "📈" if data['change'] >= 0 else "📉"
            results.append(
                f"{change_emoji} *{symbol}* - {data['price']:.2f} EGP ({data['change_pct']:+.2f}%) {signal['emoji']}"
            )

    if not results:
        await msg.edit_text("❌ مش قادر أجيب الأسعار دلوقتي.")
        return

    text = f"📊 *أسعار EGX 30* 🕐 {datetime.now().strftime('%H:%M')}\n\n"
    text += "\n".join(results)
    text += "\n\n🟢شراء 🟡انتظار 🔴بيع\n_للتحليل: /analyze SYMBOL_"

    await msg.edit_text(text, parse_mode="Markdown")


async def watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_data = context.bot_data.get(user_id, {})
    stocks = user_data.get("watchlist", [])

    if not stocks:
        await update.message.reply_text("📋 قائمة المتابعة فاضية!\n\nأضف بـ:\n/add COMI")
        return

    msg = await update.message.reply_text("⏳ بجيب قائمة المتابعة...")
    results = []
    for symbol in stocks:
        data = await get_stock_data(symbol)
        if "error" not in data:
            signal = calculate_signal(data)
            change_emoji = "📈" if data['change'] >= 0 else "📉"
            results.append(
                f"{change_emoji} *{symbol}* - {data['price']:.2f} EGP ({data['change_pct']:+.2f}%) {signal['emoji']}"
            )

    text = "⭐ *قائمة المتابعة*\n\n" + "\n".join(results)
    text += "\n\n🟢شراء 🟡انتظار 🔴بيع"
    await msg.edit_text(text, parse_mode="Markdown")


async def add_to_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ مثلاً: /add COMI")
        return

    symbol = context.args[0].upper()
    if symbol not in ALL_STOCKS:
        await update.message.reply_text(f"❌ السهم '{symbol}' مش موجود.")
        return

    user_id = str(update.effective_user.id)
    if user_id not in context.bot_data:
        context.bot_data[user_id] = {"watchlist": []}

    watchlist_stocks = context.bot_data[user_id].get("watchlist", [])
    if symbol not in watchlist_stocks:
        watchlist_stocks.append(symbol)
        context.bot_data[user_id]["watchlist"] = watchlist_stocks
        await update.message.reply_text(f"✅ تم إضافة {ALL_STOCKS[symbol]} ({symbol})!")
    else:
        await update.message.reply_text(f"⚠️ {symbol} موجود بالفعل.")


async def remove_from_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ مثلاً: /remove COMI")
        return

    symbol = context.args[0].upper()
    user_id = str(update.effective_user.id)
    user_data = context.bot_data.get(user_id, {})
    watchlist_stocks = user_data.get("watchlist", [])

    if symbol in watchlist_stocks:
        watchlist_stocks.remove(symbol)
        context.bot_data[user_id]["watchlist"] = watchlist_stocks
        await update.message.reply_text(f"✅ تم حذف {symbol}.")
    else:
        await update.message.reply_text(f"❌ {symbol} مش موجود في قائمتك.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """📖 *دليل الاستخدام*

*أوامر الأسعار:*
/price COMI - سعر + مؤشرات سريعة
/egx30 - أسعار EGX 30 + إشارات

*التحليل الكامل:*
/analyze COMI - RSI + MACD + Bollinger + AI

*قائمة المتابعة:*
/watchlist | /add COMI | /remove COMI

*الإشارات:*
🟢 شراء | 🟡 انتظار | 🔴 بيع

*أسهم متاحة:*
COMI, ETEL, HRHO, SWDY, ESRS
ABUK, EAST, MNHD, AMOC, PHDC

⚠️ التحليل للمعلومات الشخصية فقط"""
    await update.message.reply_text(text, parse_mode="Markdown")


# ==================== CALLBACK BUTTONS ====================
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("analyze_"):
        symbol = data.replace("analyze_", "")
        await query.edit_message_text("🤖 بحلل المؤشرات الفنية... ثانية!")

        stock_data = await get_stock_data(symbol)
        if "error" in stock_data:
            await query.edit_message_text(f"❌ خطأ: {stock_data['error']}")
            return

        signal = calculate_signal(stock_data)
        ai_analysis = await analyze_with_ai(stock_data, signal)
        reasons_text = "\n".join([f"  • {r}" for r in signal['reasons']])
        change_emoji = "📈" if stock_data['change'] >= 0 else "📉"

        text = f"""{change_emoji} *تحليل {stock_data['name']}* ({symbol})

💰 *السعر:* {stock_data['price']:.2f} جنيه | {stock_data['change_pct']:+.2f}%

📊 *المؤشرات:*
• RSI: {stock_data['rsi']}
• SMA20: {stock_data['sma20']} | SMA50: {stock_data['sma50']}
• MACD: {stock_data['macd']} | Signal: {stock_data['macd_signal']}
• Bollinger: {stock_data['bb_lower']} ↔ {stock_data['bb_upper']}

{signal['emoji']} *الإشارة: {signal['label']}* (Score: {signal['score']}/8)
{reasons_text}

🤖 *تحليل AI:*
{ai_analysis}"""

        await query.edit_message_text(text, parse_mode="Markdown")

    elif data.startswith("add_"):
        symbol = data.replace("add_", "")
        user_id = str(query.from_user.id)
        if user_id not in context.bot_data:
            context.bot_data[user_id] = {"watchlist": []}
        watchlist_stocks = context.bot_data[user_id].get("watchlist", [])
        if symbol not in watchlist_stocks:
            watchlist_stocks.append(symbol)
            context.bot_data[user_id]["watchlist"] = watchlist_stocks
            await query.answer(f"✅ تم إضافة {symbol}!", show_alert=True)
        else:
            await query.answer(f"⚠️ {symbol} موجود بالفعل.", show_alert=True)


# ==================== MAIN ====================
def main():
    print("🚀 بيشتغل البوت - Enhanced Version...")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("price", get_price))
    app.add_handler(CommandHandler("analyze", analyze_stock))
    app.add_handler(CommandHandler("egx30", egx30_prices))
    app.add_handler(CommandHandler("watchlist", watchlist))
    app.add_handler(CommandHandler("add", add_to_watchlist))
    app.add_handler(CommandHandler("remove", remove_from_watchlist))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(button_callback))

    print("✅ البوت شغال! انتظر الرسائل...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
