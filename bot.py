"""
🤖 EGX Stock Analysis Telegram Bot
بيجيب أسعار البورصة المصرية ويحللها بـ AI
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

# ==================== GET STOCK PRICE ====================
async def get_stock_price(symbol: str) -> dict:
    """بيجيب سعر السهم من Yahoo Finance"""
    try:
        # Yahoo Finance بيدعم الأسهم المصرية بـ .CA
        yahoo_symbol = f"{symbol}.CA"
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}"
        
        async with httpx.AsyncClient(timeout=10) as http:
            response = await http.get(url, headers={
                "User-Agent": "Mozilla/5.0"
            })
            data = response.json()
        
        result = data.get("chart", {}).get("result", [])
        if not result:
            return {"error": "السهم مش موجود أو السوق مقفول"}
        
        meta = result[0].get("meta", {})
        price = meta.get("regularMarketPrice", 0)
        prev_close = meta.get("previousClose", 0) or meta.get("chartPreviousClose", 0)
        change = price - prev_close if prev_close else 0
        change_pct = (change / prev_close * 100) if prev_close else 0
        volume = meta.get("regularMarketVolume", 0)
        
        return {
            "symbol": symbol,
            "name": ALL_STOCKS.get(symbol, symbol),
            "price": price,
            "prev_close": prev_close,
            "change": change,
            "change_pct": change_pct,
            "volume": volume,
            "currency": "EGP",
            "time": datetime.now().strftime("%H:%M:%S"),
        }
    except Exception as e:
        return {"error": str(e)}


# ==================== AI ANALYSIS ====================
async def analyze_stock_with_ai(stock_data: dict) -> str:
    """بيبعت بيانات السهم لـ ChatGPT ويرجع تحليل"""
    if "error" in stock_data:
        return f"❌ مش قادر أحلل: {stock_data['error']}"
    
    change_pct = stock_data.get("change_pct", 0)
    
    prompt = f"""أنت محلل مالي خبير في البورصة المصرية (EGX).
حلل السهم التالي وأعطني توصية واضحة:

السهم: {stock_data['name']} ({stock_data['symbol']})
السعر الحالي: {stock_data['price']:.2f} جنيه
سعر الإغلاق السابق: {stock_data['prev_close']:.2f} جنيه
التغيير: {stock_data['change']:+.2f} جنيه ({change_pct:+.2f}%)
حجم التداول: {stock_data['volume']:,}

قدم تحليلاً قصيراً (3-4 جمل) يشمل:
1. تقييم الحركة الحالية
2. إشارة: شراء 🟢 / بيع 🔴 / انتظار 🟡
3. سبب موجز للتوصية

ملاحظة: وضح دائماً أن هذا تحليل فني بسيط وليس نصيحة استثمارية رسمية."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.3,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ خطأ في التحليل: {str(e)}"


# ==================== TELEGRAM COMMANDS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /start"""
    welcome = """🏦 *أهلاً في بوت البورصة المصرية!*

أنا بساعدك تتابع أسهم EGX 30 و EGX 70 بتحليل AI فوري.

*الأوامر المتاحة:*
/price COMI - سعر سهم معين
/analyze COMI - تحليل AI للسهم
/egx30 - أسعار EGX 30
/watchlist - قائمة المتابعة بتاعتك
/add COMI - أضف سهم للمتابعة
/remove COMI - شيل سهم من المتابعة
/help - المساعدة

*مثال:*
/analyze ETEL لتحليل سهم المصرية للاتصالات

⚠️ _التحليل للمعلومات الشخصية فقط وليس نصيحة استثمارية_"""
    
    await update.message.reply_text(welcome, parse_mode="Markdown")


async def get_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/price SYMBOL"""
    if not context.args:
        await update.message.reply_text("⚠️ اكتب اسم السهم مثلاً:\n/price COMI")
        return
    
    symbol = context.args[0].upper()
    if symbol not in ALL_STOCKS:
        await update.message.reply_text(
            f"❌ السهم '{symbol}' مش موجود في قائمتنا.\n"
            f"استخدم /egx30 لتشوف الأسهم المتاحة."
        )
        return
    
    msg = await update.message.reply_text("⏳ بجيب السعر...")
    data = await get_stock_price(symbol)
    
    if "error" in data:
        await msg.edit_text(f"❌ خطأ: {data['error']}")
        return
    
    change_emoji = "📈" if data['change'] >= 0 else "📉"
    change_sign = "+" if data['change'] >= 0 else ""
    
    text = f"""{change_emoji} *{data['name']}* ({data['symbol']})

💰 *السعر:* {data['price']:.2f} جنيه
📊 *التغيير:* {change_sign}{data['change']:.2f} ({change_sign}{data['change_pct']:.2f}%)
📉 *إغلاق أمس:* {data['prev_close']:.2f} جنيه
📦 *حجم التداول:* {data['volume']:,}
🕐 *آخر تحديث:* {data['time']}

_اضغط /analyze {symbol} للتحليل الكامل_"""

    keyboard = [[
        InlineKeyboardButton("🤖 تحليل AI", callback_data=f"analyze_{symbol}"),
        InlineKeyboardButton("➕ أضف للمتابعة", callback_data=f"add_{symbol}")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await msg.edit_text(text, parse_mode="Markdown", reply_markup=reply_markup)


async def analyze_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/analyze SYMBOL"""
    if not context.args:
        await update.message.reply_text("⚠️ اكتب اسم السهم مثلاً:\n/analyze COMI")
        return
    
    symbol = context.args[0].upper()
    if symbol not in ALL_STOCKS:
        await update.message.reply_text(f"❌ السهم '{symbol}' مش موجود.")
        return
    
    msg = await update.message.reply_text("🤖 بحلل السهم بـ AI... ثانية!")
    
    data = await get_stock_price(symbol)
    analysis = await analyze_stock_with_ai(data)
    
    change_emoji = "📈" if data.get('change', 0) >= 0 else "📉"
    
    text = f"""{change_emoji} *تحليل {data.get('name', symbol)}*

💰 *السعر:* {data.get('price', 'N/A'):.2f} جنيه
📊 *التغيير:* {data.get('change_pct', 0):+.2f}%

🤖 *تحليل AI:*
{analysis}

⚠️ _هذا تحليل شخصي وليس نصيحة استثمارية رسمية_"""

    await msg.edit_text(text, parse_mode="Markdown")


async def egx30_prices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/egx30 - بيعرض أسهم EGX 30"""
    msg = await update.message.reply_text("⏳ بجيب أسعار EGX 30...")
    
    results = []
    # بناخد أول 8 أسهم بس عشان مانبطلش
    for symbol in list(EGX30_STOCKS.keys())[:8]:
        data = await get_stock_price(symbol)
        if "error" not in data:
            change_emoji = "📈" if data['change'] >= 0 else "📉"
            results.append(
                f"{change_emoji} *{symbol}* - {data['price']:.2f} EGP ({data['change_pct']:+.2f}%)"
            )
    
    if not results:
        await msg.edit_text("❌ مش قادر أجيب الأسعار دلوقتي. جرب بعد شوية.")
        return
    
    text = "📊 *أسعار EGX 30*\n" + f"🕐 {datetime.now().strftime('%H:%M')}\n\n"
    text += "\n".join(results)
    text += "\n\n_للتحليل الكامل: /analyze SYMBOL_"
    
    await msg.edit_text(text, parse_mode="Markdown")


async def watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/watchlist - قائمة المتابعة"""
    user_id = str(update.effective_user.id)
    user_data = context.bot_data.get(user_id, {})
    stocks = user_data.get("watchlist", [])
    
    if not stocks:
        await update.message.reply_text(
            "📋 قائمة المتابعة فاضية!\n\nأضف أسهم بـ:\n/add COMI\n/add ETEL"
        )
        return
    
    msg = await update.message.reply_text("⏳ بجيب قائمة المتابعة...")
    
    results = []
    for symbol in stocks:
        data = await get_stock_price(symbol)
        if "error" not in data:
            change_emoji = "📈" if data['change'] >= 0 else "📉"
            results.append(
                f"{change_emoji} *{symbol}* - {data['price']:.2f} EGP ({data['change_pct']:+.2f}%)"
            )
    
    text = "⭐ *قائمة المتابعة بتاعتك*\n\n" + "\n".join(results)
    await msg.edit_text(text, parse_mode="Markdown")


async def add_to_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/add SYMBOL"""
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
        await update.message.reply_text(f"✅ تم إضافة {ALL_STOCKS[symbol]} ({symbol}) للمتابعة!")
    else:
        await update.message.reply_text(f"⚠️ {symbol} موجود بالفعل في قائمتك.")


async def remove_from_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/remove SYMBOL"""
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
        await update.message.reply_text(f"✅ تم حذف {symbol} من قائمتك.")
    else:
        await update.message.reply_text(f"❌ {symbol} مش موجود في قائمتك.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/help"""
    text = """📖 *دليل الاستخدام*

*أوامر الأسعار:*
/price COMI - سعر سهم معين
/egx30 - أسعار EGX 30

*التحليل بـ AI:*
/analyze COMI - تحليل شامل للسهم

*قائمة المتابعة:*
/watchlist - شوف قائمتك
/add COMI - أضف سهم
/remove COMI - احذف سهم

*أسهم متاحة مثلاً:*
COMI, ETEL, HRHO, SWDY, ESRS
ABUK, EAST, MNHD, AMOC, PHDC

⚠️ *تنبيه:* التحليل للمعلومات الشخصية فقط"""
    
    await update.message.reply_text(text, parse_mode="Markdown")


# ==================== CALLBACK BUTTONS ====================
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بيتعامل مع الأزرار"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith("analyze_"):
        symbol = data.replace("analyze_", "")
        context.args = [symbol]
        # نعمل fake update للـ analyze command
        stock_data = await get_stock_price(symbol)
        analysis = await analyze_stock_with_ai(stock_data)
        
        change_emoji = "📈" if stock_data.get('change', 0) >= 0 else "📉"
        text = f"""{change_emoji} *تحليل {stock_data.get('name', symbol)}*

💰 *السعر:* {stock_data.get('price', 0):.2f} جنيه
📊 *التغيير:* {stock_data.get('change_pct', 0):+.2f}%

🤖 *تحليل AI:*
{analysis}"""
        
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
    print("🚀 بيشتغل البوت...")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("price", get_price))
    app.add_handler(CommandHandler("analyze", analyze_stock))
    app.add_handler(CommandHandler("egx30", egx30_prices))
    app.add_handler(CommandHandler("watchlist", watchlist))
    app.add_handler(CommandHandler("add", add_to_watchlist))
    app.add_handler(CommandHandler("remove", remove_from_watchlist))
    app.add_handler(CommandHandler("help", help_command))
    
    # Buttons
    app.add_handler(CallbackQueryHandler(button_callback))
    
    print("✅ البوت شغال! انتظر الرسائل...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
