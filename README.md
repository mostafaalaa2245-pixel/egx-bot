# EGX Pulse Bot

بوت تليجرام لتحليل البورصة المصرية: مؤشرات فنية، تحليل AI، تنبيهات، محفظة، أخبار، تقارير يومية.

## المميزات

- **تحليل أسهم:** سعر، RSI، MACD، Bollinger، SMA، ATR، إشارة شراء/بيع/انتظار، Stop Loss & Take Profit
- **تحليل AI:** تحليل يومي + أسبوعي مع OpenAI (gpt-4o-mini)
- **مقارنة سهمين:** /compare COMI ETEL
- **أخبار:** أخبار السوق العامة + أخبار شركة معينة (Mubasher) + تلخيص AI
- **سيولة السوق:** حجم التداول وأعلى الأسهم تداولاً
- **تنبيهات سعر:** /alert COMI 80 — يرسل تنبيه عند الوصول للسعر
- **محفظة:** تسجيل شراء/بيع ومراقبة الربح والخسارة
- **قائمة متابعة:** /watchlist | /add COMI | /remove COMI
- **تقارير:** تقرير فوري + تقرير يومي 10 ص (لمن ضغط /start أو /report)
- **أسواق:** /egx30 | /egx70 | /egx100
- **التحقق من API:** /testapi — للتأكد من اتصال OpenAI

## التشغيل

### متغيرات البيئة

- `TELEGRAM_TOKEN` — من BotFather
- `OPENAI_API_KEY` — من platform.openai.com (API keys)

### محلياً

```bash
pip install -r requirements.txt
set TELEGRAM_TOKEN=...
set OPENAI_API_KEY=...
python bot.py
```

### على Railway

1. رفع المشروع (أو ربط GitHub).
2. إضافة Variables: `TELEGRAM_TOKEN`, `OPENAI_API_KEY`.
3. الـ Procfile يشغّل: `worker: python bot.py`.

## الملفات

- `bot.py` — الكود الكامل
- `requirements.txt` — التبعيات
- `Procfile` — أمر التشغيل (Railway/Heroku)
- `runtime.txt` — إصدار Python (مثلاً 3.11)
- `railway.toml` — إعدادات Railway

## أوامر سريعة

| الأمر | الوظيفة |
|-------|----------|
| /start | ترحيب وقائمة الأوامر |
| /price COMI | سعر + مؤشرات + SL/TP |
| /analyze COMI | تحليل يومي + أسبوعي + AI |
| /testapi | التحقق من اتصال OpenAI |
| /compare COMI ETEL | مقارنة سهمين |
| /news | أخبار السوق (AI) |
| /stocknews COMI | أخبار الشركة + AI |
| /liquidity | سيولة السوق |
| /alert COMI 80 | تنبيه عند 80 جنيه |
| /portfolio | المحفظة |
| /report | التقرير اليومي فوراً |

⚠️ للمعلومات الشخصية فقط — ليس نصيحة استثمارية.
