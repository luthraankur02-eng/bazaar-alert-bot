"""
╔══════════════════════════════════════════════════════════════════╗
║       📊 NSE PAPER TRADING AGENT — ₹10,000 Capital             ║
║   Full News Intelligence — Orders, Results, M&A, Commodities   ║
╚══════════════════════════════════════════════════════════════════╝

Kya kya analyze karta hai:
✅ Naye orders / contracts mile
✅ Quarterly P&L results
✅ Mergers, Acquisitions, Takeovers
✅ Metal / Crude / Commodity prices → affected stocks
✅ FII / DII buying or selling
✅ Govt policy, Budget, RBI decisions
✅ Regulatory news (SEBI, CCI)
✅ Management changes, promoter activity
✅ Global market impact on Indian stocks
"""

import os, json, asyncio, logging, datetime, re
import httpx, feedparser
from anthropic import AsyncAnthropic
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ══════════════════════════════════════════════════════════════════════
# ⚙️  CONFIG
# ══════════════════════════════════════════════════════════════════════

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
MY_CHAT_ID         = os.environ.get("MY_CHAT_ID", "")
COUSIN_CHAT_ID     = os.environ.get("COUSIN_CHAT_ID", "")
SCAN_INTERVAL_MIN  = int(os.environ.get("SCAN_INTERVAL_MIN", "15"))
PAPER_CAPITAL      = 10000.0

# ══════════════════════════════════════════════════════════════════════
# 📰 NEWS SOURCES — India ke sab bade financial news
# ══════════════════════════════════════════════════════════════════════

NEWS_FEEDS = [
    {"url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",          "name": "ET Markets",     "type": "market"},
    {"url": "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",      "name": "ET Stocks",      "type": "stocks"},
    {"url": "https://economictimes.indiatimes.com/markets/commodities/rssfeeds/1808953.cms", "name": "ET Commodity",   "type": "commodity"},
    {"url": "https://economictimes.indiatimes.com/industry/rssfeeds/13352306.cms",           "name": "ET Industry",    "type": "industry"},
    {"url": "https://economictimes.indiatimes.com/news/company/rssfeeds/2143429.cms",        "name": "ET Corporate",   "type": "corporate"},
    {"url": "https://www.moneycontrol.com/rss/marketreports.xml",                            "name": "MC Markets",     "type": "market"},
    {"url": "https://www.moneycontrol.com/rss/results.xml",                                  "name": "MC Results",     "type": "results"},
    {"url": "https://www.moneycontrol.com/rss/MCtopstories.xml",                             "name": "MC Top",         "type": "general"},
    {"url": "https://www.livemint.com/rss/markets",                                          "name": "Mint Markets",   "type": "market"},
    {"url": "https://www.livemint.com/rss/companies",                                        "name": "Mint Companies", "type": "corporate"},
    {"url": "https://www.livemint.com/rss/economy",                                          "name": "Mint Economy",   "type": "macro"},
    {"url": "https://feeds.feedburner.com/ndtvprofit-latest",                                "name": "NDTV Profit",    "type": "general"},
    {"url": "https://www.thehindubusinessline.com/markets/feeder/default.rss",               "name": "BL Markets",     "type": "market"},
    {"url": "https://www.thehindubusinessline.com/companies/feeder/default.rss",             "name": "BL Companies",   "type": "corporate"},
    {"url": "https://feeds.reuters.com/reuters/INbusinessNews",                              "name": "Reuters India",  "type": "general"},
    {"url": "https://www.business-standard.com/rss/markets-106.rss",                        "name": "BS Markets",     "type": "market"},
    {"url": "https://www.business-standard.com/rss/companies-101.rss",                      "name": "BS Companies",   "type": "corporate"},
    {"url": "https://www.business-standard.com/rss/economy-policy-102.rss",                 "name": "BS Economy",     "type": "macro"},
]

# ══════════════════════════════════════════════════════════════════════
# 📋 NSE STOCKS — aliases for news matching
# ══════════════════════════════════════════════════════════════════════

STOCKS = {
    "RELIANCE.NS":   {"name": "Reliance Industries",  "aliases": ["reliance","ril","jio","mukesh ambani"],             "sector": "Energy/Retail"},
    "TCS.NS":        {"name": "TCS",                  "aliases": ["tcs","tata consultancy"],                           "sector": "IT"},
    "HDFCBANK.NS":   {"name": "HDFC Bank",            "aliases": ["hdfc bank","hdfcbank"],                             "sector": "Banking"},
    "ICICIBANK.NS":  {"name": "ICICI Bank",           "aliases": ["icici bank","icici"],                               "sector": "Banking"},
    "INFY.NS":       {"name": "Infosys",              "aliases": ["infosys","infy"],                                   "sector": "IT"},
    "SBIN.NS":       {"name": "SBI",                  "aliases": ["sbi","state bank","state bank of india"],           "sector": "Banking"},
    "TATAMOTORS.NS": {"name": "Tata Motors",          "aliases": ["tata motors","jaguar","jlr","ev tata"],             "sector": "Auto"},
    "BAJFINANCE.NS": {"name": "Bajaj Finance",        "aliases": ["bajaj finance"],                                    "sector": "Finance"},
    "WIPRO.NS":      {"name": "Wipro",                "aliases": ["wipro"],                                            "sector": "IT"},
    "AXISBANK.NS":   {"name": "Axis Bank",            "aliases": ["axis bank","axis"],                                 "sector": "Banking"},
    "KOTAKBANK.NS":  {"name": "Kotak Bank",           "aliases": ["kotak","kotak mahindra","kotak bank"],              "sector": "Banking"},
    "BHARTIARTL.NS": {"name": "Bharti Airtel",        "aliases": ["airtel","bharti","bharti airtel"],                  "sector": "Telecom"},
    "ITC.NS":        {"name": "ITC",                  "aliases": ["itc","itc limited"],                                "sector": "FMCG"},
    "SUNPHARMA.NS":  {"name": "Sun Pharma",           "aliases": ["sun pharma","sun pharmaceutical"],                  "sector": "Pharma"},
    "TATASTEEL.NS":  {"name": "Tata Steel",           "aliases": ["tata steel"],                                       "sector": "Metal"},
    "JSWSTEEL.NS":   {"name": "JSW Steel",            "aliases": ["jsw steel","jsw","sajjan jindal"],                  "sector": "Metal"},
    "HINDALCO.NS":   {"name": "Hindalco",             "aliases": ["hindalco","novelis","aluminium hindalco"],          "sector": "Metal"},
    "ONGC.NS":       {"name": "ONGC",                 "aliases": ["ongc","oil natural gas"],                           "sector": "Energy"},
    "NTPC.NS":       {"name": "NTPC",                 "aliases": ["ntpc","national thermal power"],                    "sector": "Power"},
    "POWERGRID.NS":  {"name": "Power Grid",           "aliases": ["power grid","powergrid"],                           "sector": "Power"},
    "LT.NS":         {"name": "L&T",                  "aliases": ["l&t","larsen","larsen toubro"],                     "sector": "Infra"},
    "MARUTI.NS":     {"name": "Maruti Suzuki",        "aliases": ["maruti","maruti suzuki","suzuki"],                  "sector": "Auto"},
    "M&M.NS":        {"name": "Mahindra",             "aliases": ["mahindra","m&m","anand mahindra"],                  "sector": "Auto"},
    "BAJAJ-AUTO.NS": {"name": "Bajaj Auto",           "aliases": ["bajaj auto","bajaj"],                               "sector": "Auto"},
    "HCLTECH.NS":    {"name": "HCL Tech",             "aliases": ["hcl","hcl technologies"],                           "sector": "IT"},
    "TECHM.NS":      {"name": "Tech Mahindra",        "aliases": ["tech mahindra","techm"],                            "sector": "IT"},
    "DRREDDY.NS":    {"name": "Dr. Reddy's",          "aliases": ["dr reddy","dr. reddy","drreddys"],                  "sector": "Pharma"},
    "CIPLA.NS":      {"name": "Cipla",                "aliases": ["cipla"],                                            "sector": "Pharma"},
    "DIVISLAB.NS":   {"name": "Divi's Labs",          "aliases": ["divi","divi's","divi lab"],                         "sector": "Pharma"},
    "APOLLOHOSP.NS": {"name": "Apollo Hospitals",     "aliases": ["apollo hospital","apollo hospitals"],               "sector": "Healthcare"},
    "HINDUNILVR.NS": {"name": "HUL",                  "aliases": ["hul","hindustan unilever","unilever"],              "sector": "FMCG"},
    "NESTLEIND.NS":  {"name": "Nestle India",         "aliases": ["nestle","maggi","nestle india"],                    "sector": "FMCG"},
    "BRITANNIA.NS":  {"name": "Britannia",            "aliases": ["britannia"],                                        "sector": "FMCG"},
    "DABUR.NS":      {"name": "Dabur",                "aliases": ["dabur"],                                            "sector": "FMCG"},
    "ULTRACEMCO.NS": {"name": "UltraTech Cement",     "aliases": ["ultratech","ultratech cement"],                     "sector": "Cement"},
    "GRASIM.NS":     {"name": "Grasim",               "aliases": ["grasim","aditya birla cement"],                     "sector": "Cement"},
    "AMBUJACEM.NS":  {"name": "Ambuja Cement",        "aliases": ["ambuja","ambuja cement"],                           "sector": "Cement"},
    "ACC.NS":        {"name": "ACC",                  "aliases": ["acc cement","acc"],                                  "sector": "Cement"},
    "ADANIENT.NS":   {"name": "Adani Enterprises",    "aliases": ["adani enterprises","adani"],                        "sector": "Conglomerate"},
    "ADANIPORTS.NS": {"name": "Adani Ports",          "aliases": ["adani ports","mundra port"],                        "sector": "Infra"},
    "ADANIGREEN.NS": {"name": "Adani Green",          "aliases": ["adani green","adani renewable"],                    "sector": "Power"},
    "HAL.NS":        {"name": "HAL",                  "aliases": ["hal","hindustan aeronautics"],                      "sector": "Defence"},
    "BEL.NS":        {"name": "BEL",                  "aliases": ["bel","bharat electronics"],                         "sector": "Defence"},
    "IRCTC.NS":      {"name": "IRCTC",                "aliases": ["irctc","indian railway catering"],                  "sector": "PSU"},
    "COALINDIA.NS":  {"name": "Coal India",           "aliases": ["coal india","coalindia"],                           "sector": "Mining"},
    "ZOMATO.NS":     {"name": "Zomato",               "aliases": ["zomato","blinkit"],                                 "sector": "Tech"},
    "DLF.NS":        {"name": "DLF",                  "aliases": ["dlf"],                                              "sector": "Realty"},
    "GODREJPROP.NS": {"name": "Godrej Properties",    "aliases": ["godrej properties","godrej prop"],                  "sector": "Realty"},
    "VEDL.NS":       {"name": "Vedanta",              "aliases": ["vedanta","vedl","anil agarwal"],                    "sector": "Mining/Metal"},
    "SAIL.NS":       {"name": "SAIL",                 "aliases": ["sail","steel authority"],                           "sector": "Metal"},
    "GAIL.NS":       {"name": "GAIL",                 "aliases": ["gail","gas authority"],                             "sector": "Energy"},
    "BPCL.NS":       {"name": "BPCL",                 "aliases": ["bpcl","bharat petroleum"],                          "sector": "Energy"},
    "IOC.NS":        {"name": "Indian Oil",           "aliases": ["indian oil","ioc","iocl"],                          "sector": "Energy"},
    "TATAPOWER.NS":  {"name": "Tata Power",           "aliases": ["tata power"],                                       "sector": "Power"},
    "HEROMOTOCO.NS": {"name": "Hero MotoCorp",        "aliases": ["hero","hero motocorp"],                             "sector": "Auto"},
    "EICHERMOT.NS":  {"name": "Eicher Motors",        "aliases": ["eicher","royal enfield"],                           "sector": "Auto"},
    "INDUSINDBK.NS": {"name": "IndusInd Bank",        "aliases": ["indusind","indusind bank"],                         "sector": "Banking"},
    "SBILIFE.NS":    {"name": "SBI Life",             "aliases": ["sbi life","sbilife"],                               "sector": "Insurance"},
    "HDFCLIFE.NS":   {"name": "HDFC Life",            "aliases": ["hdfc life"],                                        "sector": "Insurance"},
    "LICI.NS":       {"name": "LIC",                  "aliases": ["lic","life insurance corporation"],                 "sector": "Insurance"},
    "DMART.NS":      {"name": "DMart",                "aliases": ["dmart","avenue supermarts","d-mart"],               "sector": "Retail"},
    "NMDC.NS":       {"name": "NMDC",                 "aliases": ["nmdc","national mineral"],                          "sector": "Mining"},
    "RVNL.NS":       {"name": "RVNL",                 "aliases": ["rvnl","rail vikas nigam"],                          "sector": "Infra"},
    "IRFC.NS":       {"name": "IRFC",                 "aliases": ["irfc","indian railway finance"],                    "sector": "Finance"},
}

# Commodity price news → affected stocks
COMMODITY_IMPACT = {
    "steel":       ["TATASTEEL.NS","JSWSTEEL.NS","SAIL.NS"],
    "iron ore":    ["TATASTEEL.NS","JSWSTEEL.NS","SAIL.NS","NMDC.NS"],
    "aluminium":   ["HINDALCO.NS","VEDL.NS"],
    "copper":      ["HINDALCO.NS","VEDL.NS"],
    "zinc":        ["VEDL.NS","HINDALCO.NS"],
    "crude oil":   ["ONGC.NS","BPCL.NS","IOC.NS","GAIL.NS","RELIANCE.NS"],
    "natural gas": ["GAIL.NS","ONGC.NS","NTPC.NS"],
    "coal":        ["COALINDIA.NS","NTPC.NS","TATAPOWER.NS","SAIL.NS"],
    "cement":      ["ULTRACEMCO.NS","GRASIM.NS","AMBUJACEM.NS","ACC.NS"],
}

# ══════════════════════════════════════════════════════════════════════
# 💼 PORTFOLIO
# ══════════════════════════════════════════════════════════════════════

MAX_TRADES_PER_DAY = 3   # Din mein max 3 trades

portfolio = {
    "capital":          PAPER_CAPITAL,
    "available":        PAPER_CAPITAL,
    "positions":        {},
    "closed_trades":    [],
    "win_count":        0,
    "total_signals":    0,
    "pending_signal":   None,
    "last_scan_time":   None,
    "last_news_time":   None,
    "seen_headlines":   set(),
    "trades_today":     0,           # Aaj kitne trades liye
    "today_date":       None,        # Kaunse din ka count hai
}

def reset_daily_limit():
    """Naya din — counter reset"""
    today = datetime.date.today().isoformat()
    if portfolio["today_date"] != today:
        portfolio["today_date"]  = today
        portfolio["trades_today"] = 0

def can_trade() -> bool:
    """Aaj aur trade le sakte hain?"""
    reset_daily_limit()
    return portfolio["trades_today"] < MAX_TRADES_PER_DAY

def trades_left() -> int:
    reset_daily_limit()
    return MAX_TRADES_PER_DAY - portfolio["trades_today"]

claude  = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger  = logging.getLogger(__name__)
bot_app = None

# ══════════════════════════════════════════════════════════════════════
# 📤 SEND TO BOTH — Ankur + Cousin
# ══════════════════════════════════════════════════════════════════════

async def send_to_all(text: str, parse_mode: str = "Markdown"):
    bot: Bot = bot_app.bot
    for cid in [MY_CHAT_ID, COUSIN_CHAT_ID]:
        if cid:
            try:
                await bot.send_message(chat_id=cid, text=text, parse_mode=parse_mode)
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.error(f"Send failed {cid}: {e}")

# ══════════════════════════════════════════════════════════════════════
# 📰 FETCH ALL NEWS
# ══════════════════════════════════════════════════════════════════════

async def fetch_all_news() -> list[dict]:
    all_articles = []
    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        for feed in NEWS_FEEDS:
            try:
                resp   = await client.get(feed["url"])
                parsed = feedparser.parse(resp.text)
                for entry in parsed.entries[:8]:
                    headline = entry.get("title", "").strip()
                    if not headline or headline in portfolio["seen_headlines"]:
                        continue
                    portfolio["seen_headlines"].add(headline)
                    if len(portfolio["seen_headlines"]) > 2000:
                        portfolio["seen_headlines"] = set(list(portfolio["seen_headlines"])[-1000:])
                    all_articles.append({
                        "source":   feed["name"],
                        "type":     feed["type"],
                        "headline": headline,
                        "summary":  entry.get("summary", "")[:400],
                        "link":     entry.get("link", ""),
                    })
            except Exception as e:
                logger.debug(f"Feed failed {feed['name']}: {e}")

    portfolio["last_news_time"] = datetime.datetime.now().strftime("%I:%M %p")
    logger.info(f"Fetched {len(all_articles)} articles")
    return all_articles

# ══════════════════════════════════════════════════════════════════════
# 🔗 NEWS → STOCK MATCH
# ══════════════════════════════════════════════════════════════════════

def match_news_to_stocks(articles: list[dict]) -> dict:
    stock_news = {}
    for art in articles:
        text    = (art["headline"] + " " + art["summary"]).lower()
        matched = set()
        for sym, info in STOCKS.items():
            for alias in info["aliases"]:
                if alias in text:
                    matched.add(sym)
                    break
        for commodity, syms in COMMODITY_IMPACT.items():
            if commodity in text:
                for sym in syms:
                    if sym in STOCKS:
                        matched.add(sym)
        for sym in matched:
            stock_news.setdefault(sym, []).append(art)
    return stock_news

# ══════════════════════════════════════════════════════════════════════
# 💹 PRICE DATA
# ══════════════════════════════════════════════════════════════════════

async def get_price_data(symbols: list[str]) -> dict:
    result = {}
    try:
        import yfinance as yf
        tickers = yf.Tickers(" ".join(symbols))
        for sym in symbols:
            try:
                hist = tickers.tickers[sym].history(period="5d", interval="1d")
                if hist.empty or len(hist) < 2:
                    continue
                today_vol = int(hist["Volume"].iloc[-1])
                avg_vol   = int(hist["Volume"].iloc[:-1].mean()) if len(hist) > 1 else today_vol
                curr      = round(float(hist["Close"].iloc[-1]), 2)
                prev      = round(float(hist["Close"].iloc[-2]), 2)
                result[sym] = {
                    "price":        curr,
                    "change_pct":   round((curr - prev) / prev * 100, 2),
                    "volume_ratio": round(today_vol / avg_vol, 2) if avg_vol else 1.0,
                    "high":         round(float(hist["High"].iloc[-1]), 2),
                    "low":          round(float(hist["Low"].iloc[-1]), 2),
                }
            except:
                pass
    except ImportError:
        logger.warning("yfinance not installed")
    return result

# ══════════════════════════════════════════════════════════════════════
# 🧠 AI ANALYSIS — Full intelligence
# ══════════════════════════════════════════════════════════════════════

async def ai_analyze_news(articles: list[dict], stock_news: dict, price_data: dict) -> dict | None:

    all_news_text = "\n".join([
        f"[{a['source']} | {a['type'].upper()}] {a['headline']}\n  {a['summary'][:200]}"
        for a in articles[:50]
    ])

    stock_news_text = ""
    for sym, arts in list(stock_news.items())[:20]:
        name       = STOCKS[sym]["name"]
        headlines  = " | ".join([a["headline"] for a in arts[:3]])
        price_info = f"₹{price_data[sym]['price']} ({price_data[sym]['change_pct']:+.2f}%)" if sym in price_data else "NA"
        stock_news_text += f"\n• {name} ({sym}) [{price_info}]: {headlines}"

    price_text = "\n".join([
        f"• {STOCKS.get(sym,{}).get('name',sym)}: ₹{d['price']} ({d['change_pct']:+.2f}%, Vol {d['volume_ratio']}x)"
        for sym, d in price_data.items() if sym in STOCKS
    ][:30])

    prompt = f"""Tu ek expert NSE stock analyst hai. Neeche India ki latest financial news hai — ORDERS, RESULTS, M&A, COMMODITIES, POLICY sab kuch.

━━━━━━━━ SAARI MARKET NEWS ━━━━━━━━
{all_news_text}

━━━━━━━━ STOCKS IN NEWS ━━━━━━━━
{stock_news_text if stock_news_text else "Direct matches nahi — general market news dekh"}

━━━━━━━━ LIVE NSE PRICES ━━━━━━━━
{price_text if price_text else "Price data unavailable"}

TERI TASK:
1. Saari news padh — kaunse stock pe SABSE ZYADA impact hai aaj?
2. News type classify kar:
   ORDER_WIN | QUARTERLY_RESULT | MERGER_ACQUISITION | COMMODITY_IMPACT | POLICY_CHANGE | FII_DII | MANAGEMENT_CHANGE | GLOBAL_IMPACT | TECHNICAL_BREAKOUT
3. Sirf recommend kar agar 70%+ confident ho
4. SL tight rakho (1.5-2%), Target realistic (3-4%)
5. Paper capital ₹10,000 — position ₹4,000 tak

Respond ONLY in JSON — koi extra text nahi:
{{
  "found_signal": true,
  "symbol": "TATASTEEL.NS",
  "name": "Tata Steel",
  "sector": "Metal",
  "direction": "BUY",
  "news_type": "COMMODITY_IMPACT",
  "news_type_hindi": "Global steel prices barh rahe hain",
  "entry": 145.50,
  "stop_loss": 141.80,
  "target": 153.00,
  "risk_reward": "1:2",
  "confidence_pct": 78,
  "confidence": "HIGH",
  "key_news": [
    "Global steel prices 3% barhe — China production cut",
    "Tata Steel Q3 production record high",
    "Iron ore prices stable — margin improvement expected"
  ],
  "impact_reason": "Exactly kyon yeh stock move karega — 2-3 lines",
  "risk_factors": "Kya risk hai",
  "other_stocks_impacted": ["JSWSTEEL.NS", "SAIL.NS"]
}}

Agar strong signal nahi: {{"found_signal": false, "reason": "kyon nahi mila"}}"""

    try:
        resp = await claude.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}]
        )
        raw  = resp.content[0].text.strip().replace("```json","").replace("```","").strip()
        data = json.loads(raw)
        return data if data.get("found_signal") else data
    except Exception as e:
        logger.error(f"AI error: {e}")
        return None

# ══════════════════════════════════════════════════════════════════════
# 📤 FORMAT ALERT
# ══════════════════════════════════════════════════════════════════════

NEWS_LABELS = {
    "ORDER_WIN":          "📋 Naya Order / Contract Mila!",
    "QUARTERLY_RESULT":   "📊 Quarterly Result Aaya!",
    "MERGER_ACQUISITION": "🤝 Merger / Takeover News!",
    "COMMODITY_IMPACT":   "⚗️ Commodity Price Effect!",
    "POLICY_CHANGE":      "🏛️ Govt / RBI Policy Change!",
    "FII_DII":            "💰 FII/DII Buying/Selling!",
    "MANAGEMENT_CHANGE":  "👔 Management Change!",
    "GLOBAL_IMPACT":      "🌍 Global Market Impact!",
    "TECHNICAL_BREAKOUT": "📈 Technical Breakout!",
}

def format_alert(signal: dict, stock_articles: list[dict]) -> list[str]:
    messages = []
    price    = signal["entry"]
    d_emo    = "📈" if signal["direction"] == "BUY" else "📉"
    conf_emo = "🔥" if signal["confidence"] == "HIGH" else "⚡"
    label    = NEWS_LABELS.get(signal["news_type"], "📰 Market Alert!")
    qty      = max(1, int(portfolio["available"] * 0.4 / price))
    cost     = round(qty * price, 2)
    sl_pct   = round(abs(price - signal["stop_loss"]) / price * 100, 2)
    tgt_pct  = round(abs(signal["target"] - price) / price * 100, 2)
    others   = [STOCKS[s]["name"] for s in signal.get("other_stocks_impacted",[]) if s in STOCKS][:3]

    key_news = "\n".join([f"  • {n}" for n in signal.get("key_news", [])[:4]])

    # Message 1: Main alert
    msg1 = (
        f"🚨 *{label}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{d_emo} *{signal['name']}* | {signal.get('sector','')}\n"
        f"{conf_emo} Confidence: {signal['confidence']} ({signal['confidence_pct']}%)\n\n"
        f"📰 *{signal.get('news_type_hindi', signal['news_type'])}*\n\n"
        f"📌 *Key News:*\n{key_news}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 *Impact:*\n_{signal.get('impact_reason','')}_\n\n"
        f"⚠️ *Risk:* _{signal.get('risk_factors','N/A')}_\n"
        + (f"🔗 *Aur bhi dekhna:* {', '.join(others)}\n" if others else "")
        + f"\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"*{signal['direction']} Trade Plan:*\n"
        f"📍 Entry:   ₹{signal['entry']:,.2f}\n"
        f"🛑 SL:      ₹{signal['stop_loss']:,.2f} (-{sl_pct}%)\n"
        f"🎯 Target:  ₹{signal['target']:,.2f} (+{tgt_pct}%)\n"
        f"⚖️ R:R:     {signal['risk_reward']}\n\n"
        f"📦 {qty} shares × ₹{price} = ₹{cost:,.0f}\n"
        f"💼 Balance: ₹{portfolio['available']:,.0f}\n"
        f"🔢 Aaj ke trades: {portfolio['trades_today']}/{MAX_TRADES_PER_DAY} liye\n\n"
        f"🤔 *YES* lena hai | *NO* skip karo"
    )
    messages.append(msg1)

    # Message 2: All related news
    if stock_articles:
        lines = [f"📰 *{signal['name']} — Saari Related News:*\n━━━━━━━━━━━━━━━━━━"]
        for i, art in enumerate(stock_articles[:10], 1):
            lines.append(f"\n*{i}. [{art['source']}]*\n_{art['headline']}_")
            if art["summary"]:
                short = art["summary"][:150].replace("*","").replace("_","").strip()
                lines.append(f"   {short}...")
        messages.append("\n".join(lines))
    return messages

# ══════════════════════════════════════════════════════════════════════
# 🔄 POSITION MONITOR
# ══════════════════════════════════════════════════════════════════════

async def check_positions(price_data: dict):
    to_close = []
    for sym, pos in portfolio["positions"].items():
        if sym not in price_data:
            continue
        curr    = price_data[sym]["price"]
        is_buy  = pos["direction"] == "BUY"
        hit_tgt = (is_buy and curr >= pos["target"]) or (not is_buy and curr <= pos["target"])
        hit_sl  = (is_buy and curr <= pos["sl"])     or (not is_buy and curr >= pos["sl"])
        if hit_tgt or hit_sl:
            pnl     = (curr - pos["entry"]) * pos["qty"] if is_buy else (pos["entry"] - curr) * pos["qty"]
            label   = "🎯 TARGET HIT!" if hit_tgt else "🛑 STOP LOSS HIT"
            new_bal = portfolio["available"] + pos["cost"] + pnl
            await send_to_all(
                f"{label}\n━━━━━━━━━━━━━━━━━━\n"
                f"📊 *{pos['name']}*\n"
                f"Entry: ₹{pos['entry']:,.2f} → Exit: ₹{curr:,.2f}\n"
                f"Qty: {pos['qty']} | {'✅ Profit' if pnl>0 else '❌ Loss'}: {'+'if pnl>0 else ''}₹{pnl:,.0f}\n"
                f"💼 Balance: ₹{new_bal:,.0f}"
            )
            to_close.append((sym, pnl, pos["cost"]))
    for sym, pnl, cost in to_close:
        portfolio["available"] += cost + pnl
        if pnl > 0:
            portfolio["win_count"] += 1
        portfolio["closed_trades"].append({"sym":sym,"pnl":pnl,"time":str(datetime.datetime.now())})
        del portfolio["positions"][sym]

# ══════════════════════════════════════════════════════════════════════
# 🔍 MAIN SCAN
# ══════════════════════════════════════════════════════════════════════

async def run_scan(silent: bool = False):
    portfolio["last_scan_time"] = datetime.datetime.now().strftime("%d %b, %I:%M %p")
    if not silent:
        await send_to_all(
            f"🔍 *Full market intelligence scan...*\n"
            f"📰 {len(NEWS_FEEDS)} news sources\n"
            f"📊 {len(STOCKS)} NSE stocks"
        )

    articles   = await fetch_all_news()
    price_data = await get_price_data(list(STOCKS.keys()))
    if price_data:
        await check_positions(price_data)

    stock_news = match_news_to_stocks(articles)
    result     = await ai_analyze_news(articles, stock_news, price_data)
    portfolio["total_signals"] += 1

    # Daily trade limit check
    if not can_trade():
        await send_to_all(
            f"⛔ *Aaj ke {MAX_TRADES_PER_DAY} trades ho gaye!*\n"
            f"Kal subah 9 AM pe counter reset hoga.\n"
            f"Scan jaari hai — positions monitor hoti rahengi. 👀"
        )
        return

    if result and result.get("found_signal"):
        sym            = result.get("symbol","")
        stock_articles = stock_news.get(sym, [])
        msgs           = format_alert(result, stock_articles)
        portfolio["pending_signal"] = result
        for msg in msgs:
            await send_to_all(msg)
            await asyncio.sleep(1)
    else:
        reason = result.get("reason","Koi strong opportunity nahi mili") if result else "Koi strong opportunity nahi mili"
        await send_to_all(
            f"📭 *Koi strong signal nahi mila*\n"
            f"_{reason}_\n\n"
            f"📰 {len(articles)} news articles analyze ki\n"
            f"🔗 {len(stock_news)} stocks news mein mention hue\n"
            f"🔄 Agli scan {SCAN_INTERVAL_MIN} min mein"
        )

async def scan_loop():
    await asyncio.sleep(30)
    while True:
        try:
            await run_scan()
        except Exception as e:
            logger.error(f"Scan error: {e}")
        await asyncio.sleep(SCAN_INTERVAL_MIN * 60)

# ══════════════════════════════════════════════════════════════════════
# 💬 TELEGRAM COMMANDS
# ══════════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🇮🇳 *NSE News Intelligence Agent*\n━━━━━━━━━━━━━━━━\n"
        f"💼 Capital: ₹{PAPER_CAPITAL:,.0f} | Scan: Har {SCAN_INTERVAL_MIN} min\n\n"
        "📰 *Kya analyze hota hai:*\n"
        "📋 Company ko naye orders/contracts\n"
        "📊 Quarterly P&L results\n"
        "🤝 Mergers & Acquisitions\n"
        "⚗️ Metal/Crude → affected stocks\n"
        "🏛️ Govt/RBI policy changes\n"
        "💰 FII/DII buying selling\n"
        "🌍 Global market impact\n\n"
        "Commands: /scan /news /portfolio /summary /help",
        parse_mode="Markdown"
    )

async def cmd_scan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Full news scan shuru...")
    await run_scan(silent=False)

async def cmd_news(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📰 Latest news fetch ho rahi hai...")
    articles = await fetch_all_news()
    if not articles:
        await update.message.reply_text("⚠️ News nahi mili.")
        return
    by_type = {}
    for art in articles:
        by_type.setdefault(art["type"], []).append(art)
    icons = {"market":"📈","stocks":"📊","commodity":"⚗️","corporate":"🏢","results":"💹","macro":"🏛️","industry":"🏭","general":"📌"}
    lines = ["📰 *Latest Market News:*\n━━━━━━━━━━━━━━━━"]
    for typ, arts in by_type.items():
        ic = icons.get(typ,"📰")
        lines.append(f"\n{ic} *{typ.upper()}:*")
        for a in arts[:2]:
            lines.append(f"  • _{a['headline'][:100]}_")
    await update.message.reply_text("\n".join(lines[:60]), parse_mode="Markdown")

async def cmd_portfolio(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    pos = portfolio["positions"]
    if not pos:
        await update.message.reply_text(f"📭 Koi open position nahi.\n💼 Balance: ₹{portfolio['available']:,.0f}")
        return
    lines = [f"📊 *Open Positions:*\n💼 Available: ₹{portfolio['available']:,.0f}\n"]
    for sym, p in pos.items():
        lines.append(f"▪️ *{p['name']}* {p['qty']} shares @ ₹{p['entry']:,.2f}\n   SL: ₹{p['sl']:,.2f} | T: ₹{p['target']:,.2f}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_summary(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    closed    = portfolio["closed_trades"]
    total_pnl = sum(t["pnl"] for t in closed)
    wins      = portfolio["win_count"]
    win_rate  = round(wins/len(closed)*100,1) if closed else 0
    net_worth = portfolio["available"] + sum(p["cost"] for p in portfolio["positions"].values())
    await update.message.reply_text(
        f"📈 *Trading Summary*\n━━━━━━━━━━━━━━━━\n"
        f"💰 Start: ₹{PAPER_CAPITAL:,.0f}\n"
        f"💼 Net Worth: ₹{net_worth:,.0f}\n"
        f"{'📈' if total_pnl>=0 else '📉'} P&L: {'+'if total_pnl>=0 else ''}₹{total_pnl:,.0f}\n\n"
        f"✅ Win: {wins} | ❌ Loss: {len(closed)-wins} | 🎯 {win_rate}%\n"
        f"🕐 Last scan: {portfolio['last_scan_time'] or 'Abhi tak nahi'}\n"
        f"📰 News: {portfolio['last_news_time'] or 'Abhi tak nahi'}",
        parse_mode="Markdown"
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Help*\n━━━━━━━━━━━━━━━━\n"
        "Alert kab aata hai:\n"
        "• Company ko bada order/contract mila\n"
        "• Q result behtareen ya bekaar\n"
        "• Merger/takeover news\n"
        "• Steel/Crude/Coal price change → related stocks\n"
        "• RBI/Govt policy\n"
        "• FII badi buying/selling\n\n"
        "Alert aane par:\n"
        "*YES* → Paper trade + saari news\n"
        "*NO* → Skip\n\n"
        "/scan — Abhi scan\n"
        "/news — Latest headlines\n"
        "/portfolio — Open positions\n"
        "/summary — P&L",
        parse_mode="Markdown"
    )

# ══════════════════════════════════════════════════════════════════════
# 💬 YES / NO
# ══════════════════════════════════════════════════════════════════════

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text   = update.message.text.strip().upper()
    signal = portfolio.get("pending_signal")
    if not signal:
        await update.message.reply_text("⚠️ Koi pending signal nahi. /scan karo.")
        return
    if text == "YES":
        # Daily limit check
        if not can_trade():
            await update.message.reply_text(
                f"⛔ Aaj ke {MAX_TRADES_PER_DAY} trades ho gaye bhai!\n"
                f"Kal subah naya din — phir le lena trade. 😄"
            )
            portfolio["pending_signal"] = None
            return
        price = signal["entry"]
        qty   = max(1, int(portfolio["available"] * 0.4 / price))
        cost  = round(qty * price, 2)
        if cost > portfolio["available"]:
            await update.message.reply_text(f"❌ Capital kam! Cost: ₹{cost:,.0f} | Bal: ₹{portfolio['available']:,.0f}")
            return
        portfolio["available"] -= cost
        portfolio["positions"][signal["symbol"]] = {
            "name": signal["name"], "qty": qty, "entry": price,
            "sl": signal["stop_loss"], "target": signal["target"],
            "direction": signal["direction"], "cost": cost,
        }
        portfolio["pending_signal"] = None
        portfolio["trades_today"]  += 1   # Counter badhao
        left = trades_left()
        await send_to_all(
            f"✅ *Trade Open!*\n"
            f"{'📈' if signal['direction']=='BUY' else '📉'} *{signal['name']}*\n"
            f"{signal['direction']} {qty} shares @ ₹{price:,.2f}\n"
            f"SL: ₹{signal['stop_loss']:,.2f} | T: ₹{signal['target']:,.2f}\n"
            f"💼 Balance: ₹{portfolio['available']:,.0f}\n"
            f"🔢 Aaj ke trades: {portfolio['trades_today']}/{MAX_TRADES_PER_DAY}"
            + (f" | {left} aur bache" if left > 0 else " | Aaj bas itne!")
        )
    elif text == "NO":
        portfolio["pending_signal"] = None
        await send_to_all(f"👍 Skip — *{signal['name']}*")
    else:
        await update.message.reply_text("Sirf *YES* ya *NO* bhejo! 😄", parse_mode="Markdown")

# ══════════════════════════════════════════════════════════════════════
# 🚀 LAUNCH
# ══════════════════════════════════════════════════════════════════════

async def main():
    global bot_app
    missing = [k for k in ["TELEGRAM_BOT_TOKEN","ANTHROPIC_API_KEY","MY_CHAT_ID"] if not os.environ.get(k)]
    if missing:
        raise ValueError(f"Missing env vars: {missing}")

    bot_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    for cmd, fn in [("start",cmd_start),("scan",cmd_scan),("news",cmd_news),
                    ("portfolio",cmd_portfolio),("summary",cmd_summary),("help",cmd_help)]:
        bot_app.add_handler(CommandHandler(cmd, fn))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling(drop_pending_updates=True)

    await send_to_all(
        f"🟢 *NSE News Intelligence Agent Online!*\n"
        f"💼 Capital: ₹{PAPER_CAPITAL:,.0f}\n"
        f"📰 {len(NEWS_FEEDS)} news sources monitor ho rahi hain\n"
        f"📊 {len(STOCKS)} NSE stocks track ho rahe hain\n"
        f"🔍 Scan: Har {SCAN_INTERVAL_MIN} min\n\n"
        "Pehla scan 30 sec mein! 🚀\n"
        "/news dabao abhi ki headlines ke liye"
    )

    asyncio.create_task(scan_loop())
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
