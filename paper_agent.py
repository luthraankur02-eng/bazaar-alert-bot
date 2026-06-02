"""
╔══════════════════════════════════════════════════════════════════╗
║       📊 NSE PAPER TRADING AGENT — ₹20,000 Capital             ║
║   Full News Intelligence — Orders, Results, M&A, Commodities   ║
║   🔌 Angel One SmartAPI — Live Real-Time Prices                 ║
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

Price Source:
🥇 Angel One SmartAPI — Real-time LTP + OHLC + Volume
🥈 NSE Website Scraping — Fallback
🥉 yfinance — Last resort
"""

import os, json, asyncio, logging, datetime, re
import httpx, feedparser
import pyotp
from groq import AsyncGroq
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Global market state — bullish/bearish
market_bias = {"direction": "NEUTRAL", "reason": "", "updated": None}

# ══════════════════════════════════════════════════════════════════════
# ⚙️  CONFIG
# ══════════════════════════════════════════════════════════════════════

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
GROQ_API_KEY       = os.environ.get("GROQ_API_KEY", "")
MY_CHAT_ID         = os.environ.get("MY_CHAT_ID", "")
COUSIN_CHAT_ID     = os.environ.get("COUSIN_CHAT_ID", "")
SCAN_INTERVAL_MIN  = int(os.environ.get("SCAN_INTERVAL_MIN", "60"))
PAPER_CAPITAL      = 20000.0
MAX_OPEN_POSITIONS = 2   # Max 2 open positions at a time

# ── Angel One SmartAPI config ──────────────────────────────────────
ANGEL_API_KEY    = os.environ.get("ANGEL_API_KEY", "")
ANGEL_CLIENT_ID  = os.environ.get("ANGEL_CLIENT_ID", "")
ANGEL_SECRET_KEY = os.environ.get("ANGEL_SECRET_KEY", "")   # 4-digit PIN
ANGEL_TOTP_KEY   = os.environ.get("ANGEL_TOTP_KEY", "")     # Base32 TOTP secret

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

# Blacklist — in stocks ko fallback signal mein mat lo (Angel One data unreliable)
SIGNAL_BLACKLIST = {"ADANIGREEN.NS"}

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
# 🔌 ANGEL ONE — Symbol Token Map (NSE symbol → Angel One token ID)
# ══════════════════════════════════════════════════════════════════════

NSE_SYMBOL_TOKENS = {
    "RELIANCE.NS":    {"token": "2885",   "symbol": "RELIANCE-EQ"},
    "TCS.NS":         {"token": "11536",  "symbol": "TCS-EQ"},
    "HDFCBANK.NS":    {"token": "1333",   "symbol": "HDFCBANK-EQ"},
    "ICICIBANK.NS":   {"token": "4963",   "symbol": "ICICIBANK-EQ"},
    "INFY.NS":        {"token": "1594",   "symbol": "INFY-EQ"},
    "SBIN.NS":        {"token": "3045",   "symbol": "SBIN-EQ"},
    "TATAMOTORS.NS":  {"token": "3432",   "symbol": "TATAMOTORS-EQ"},
    "BAJFINANCE.NS":  {"token": "317",    "symbol": "BAJFINANCE-EQ"},
    "WIPRO.NS":       {"token": "3787",   "symbol": "WIPRO-EQ"},
    "AXISBANK.NS":    {"token": "5900",   "symbol": "AXISBANK-EQ"},
    "KOTAKBANK.NS":   {"token": "1922",   "symbol": "KOTAKBANK-EQ"},
    "BHARTIARTL.NS":  {"token": "10604",  "symbol": "BHARTIARTL-EQ"},
    "ITC.NS":         {"token": "1660",   "symbol": "ITC-EQ"},
    "SUNPHARMA.NS":   {"token": "3351",   "symbol": "SUNPHARMA-EQ"},
    "TATASTEEL.NS":   {"token": "3499",   "symbol": "TATASTEEL-EQ"},
    "JSWSTEEL.NS":    {"token": "11723",  "symbol": "JSWSTEEL-EQ"},
    "HINDALCO.NS":    {"token": "1363",   "symbol": "HINDALCO-EQ"},
    "ONGC.NS":        {"token": "2475",   "symbol": "ONGC-EQ"},
    "NTPC.NS":        {"token": "11630",  "symbol": "NTPC-EQ"},
    "POWERGRID.NS":   {"token": "14977",  "symbol": "POWERGRID-EQ"},
    "LT.NS":          {"token": "11483",  "symbol": "LT-EQ"},
    "MARUTI.NS":      {"token": "10999",  "symbol": "MARUTI-EQ"},
    "M&M.NS":         {"token": "2031",   "symbol": "M&M-EQ"},
    "BAJAJ-AUTO.NS":  {"token": "16669",  "symbol": "BAJAJ-AUTO-EQ"},
    "HCLTECH.NS":     {"token": "7229",   "symbol": "HCLTECH-EQ"},
    "TECHM.NS":       {"token": "13538",  "symbol": "TECHM-EQ"},
    "DRREDDY.NS":     {"token": "881",    "symbol": "DRREDDY-EQ"},
    "CIPLA.NS":       {"token": "694",    "symbol": "CIPLA-EQ"},
    "DIVISLAB.NS":    {"token": "10940",  "symbol": "DIVISLAB-EQ"},
    "APOLLOHOSP.NS":  {"token": "157",    "symbol": "APOLLOHOSP-EQ"},
    "HINDUNILVR.NS":  {"token": "1394",   "symbol": "HINDUNILVR-EQ"},
    "NESTLEIND.NS":   {"token": "17963",  "symbol": "NESTLEIND-EQ"},
    "BRITANNIA.NS":   {"token": "547",    "symbol": "BRITANNIA-EQ"},
    "DABUR.NS":       {"token": "772",    "symbol": "DABUR-EQ"},
    "ULTRACEMCO.NS":  {"token": "11532",  "symbol": "ULTRACEMCO-EQ"},
    "GRASIM.NS":      {"token": "1232",   "symbol": "GRASIM-EQ"},
    "AMBUJACEM.NS":   {"token": "1270",   "symbol": "AMBUJACEM-EQ"},
    "ACC.NS":         {"token": "22",     "symbol": "ACC-EQ"},
    "ADANIENT.NS":    {"token": "25",     "symbol": "ADANIENT-EQ"},
    "ADANIPORTS.NS":  {"token": "15083",  "symbol": "ADANIPORTS-EQ"},
    "ADANIGREEN.NS":  {"token": "236339", "symbol": "ADANIGREEN-EQ"},
    "HAL.NS":         {"token": "2303",   "symbol": "HAL-EQ"},
    "BEL.NS":         {"token": "383",    "symbol": "BEL-EQ"},
    "IRCTC.NS":       {"token": "542048", "symbol": "IRCTC-EQ"},
    "COALINDIA.NS":   {"token": "20374",  "symbol": "COALINDIA-EQ"},
    "ZOMATO.NS":      {"token": "5097",   "symbol": "ZOMATO-EQ"},
    "DLF.NS":         {"token": "14732",  "symbol": "DLF-EQ"},
    "GODREJPROP.NS":  {"token": "3718",   "symbol": "GODREJPROP-EQ"},
    "VEDL.NS":        {"token": "3063",   "symbol": "VEDL-EQ"},
    "SAIL.NS":        {"token": "2963",   "symbol": "SAIL-EQ"},
    "GAIL.NS":        {"token": "1207",   "symbol": "GAIL-EQ"},
    "BPCL.NS":        {"token": "526",    "symbol": "BPCL-EQ"},
    "IOC.NS":         {"token": "1624",   "symbol": "IOC-EQ"},
    "TATAPOWER.NS":   {"token": "3426",   "symbol": "TATAPOWER-EQ"},
    "HEROMOTOCO.NS":  {"token": "1348",   "symbol": "HEROMOTOCO-EQ"},
    "EICHERMOT.NS":   {"token": "910",    "symbol": "EICHERMOT-EQ"},
    "INDUSINDBK.NS":  {"token": "5258",   "symbol": "INDUSINDBK-EQ"},
    "SBILIFE.NS":     {"token": "21808",  "symbol": "SBILIFE-EQ"},
    "HDFCLIFE.NS":    {"token": "467",    "symbol": "HDFCLIFE-EQ"},
    "LICI.NS":        {"token": "543526", "symbol": "LICI-EQ"},
    "DMART.NS":       {"token": "542867", "symbol": "DMART-EQ"},
    "NMDC.NS":        {"token": "2379",   "symbol": "NMDC-EQ"},
    "RVNL.NS":        {"token": "543395", "symbol": "RVNL-EQ"},
    "IRFC.NS":        {"token": "543257", "symbol": "IRFC-EQ"},
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
    "trades_today":     0,
    "today_date":       None,
}

def reset_daily_limit():
    today = datetime.date.today().isoformat()
    if portfolio["today_date"] != today:
        portfolio["today_date"]   = today
        portfolio["trades_today"] = 0

def can_trade() -> bool:
    reset_daily_limit()
    open_count = len(portfolio["positions"])
    return portfolio["trades_today"] < MAX_TRADES_PER_DAY and open_count < MAX_OPEN_POSITIONS

def trades_left() -> int:
    reset_daily_limit()
    return MAX_TRADES_PER_DAY - portfolio["trades_today"]

groq_client = AsyncGroq(api_key=GROQ_API_KEY)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger      = logging.getLogger(__name__)
bot_app     = None

# ══════════════════════════════════════════════════════════════════════
# 🔌 ANGEL ONE SESSION MANAGER
# ══════════════════════════════════════════════════════════════════════

class AngelOneSession:
    """
    Angel One SmartAPI — Live price data.
    Auto-login with TOTP, 24h session auto-refresh.
    """
    def __init__(self):
        self.obj           = None
        self.auth_token    = None
        self.refresh_token = None
        self.last_login    = None
        self.login_failed  = False
        self._lock         = asyncio.Lock()

    def _totp(self) -> str:
        return pyotp.TOTP(ANGEL_TOTP_KEY).now()

    async def login(self) -> bool:
        async with self._lock:
            try:
                if not all([ANGEL_API_KEY, ANGEL_CLIENT_ID, ANGEL_SECRET_KEY, ANGEL_TOTP_KEY]):
                    logger.warning("⚠️  Angel One credentials set nahi hain! Env vars check karo.")
                    self.login_failed = True
                    return False

                from SmartApi import SmartConnect
                self.obj  = SmartConnect(api_key=ANGEL_API_KEY)
                totp_code = self._totp()
                logger.info(f"🔐 Angel One login — Client: {ANGEL_CLIENT_ID}")

                loop = asyncio.get_event_loop()
                data = await loop.run_in_executor(
                    None,
                    lambda: self.obj.generateSession(ANGEL_CLIENT_ID, ANGEL_SECRET_KEY, totp_code)
                )

                if data and data.get("status") is True:
                    self.auth_token    = data["data"]["jwtToken"]
                    self.refresh_token = data["data"]["refreshToken"]
                    self.last_login    = datetime.datetime.now()
                    self.login_failed  = False
                    logger.info("✅ Angel One login successful!")
                    return True
                else:
                    msg = data.get("message", "Unknown") if data else "No response"
                    logger.error(f"❌ Angel One login failed: {msg}")
                    if "Invalid Token" in str(msg):
                        logger.error("   → ANGEL_TOTP_KEY check karo (Base32 format mein hona chahiye)")
                    elif "Invalid Client" in str(msg):
                        logger.error("   → ANGEL_CLIENT_ID check karo")
                    elif "Invalid Password" in str(msg) or "Invalid Pin" in str(msg):
                        logger.error("   → ANGEL_SECRET_KEY (4-digit PIN) check karo")
                    self.login_failed = True
                    return False
            except Exception as e:
                logger.error(f"❌ Angel One login exception: {e}")
                self.login_failed = True
                return False

    async def ensure_session(self) -> bool:
        if self.login_failed:
            return False
        if self.obj is None or self.auth_token is None:
            return await self.login()
        if self.last_login:
            age = (datetime.datetime.now() - self.last_login).total_seconds()
            if age > 23 * 3600:
                logger.info("🔄 Angel One session expire — re-login...")
                return await self.login()
        return True

    async def get_bulk_market_data(self, symbols: list[str]) -> dict:
        """
        Bulk market data — ek call mein max 50 tokens.
        Returns {symbol_ns: {price, change_pct, high, low, volume, volume_ratio, source}}
        """
        if not await self.ensure_session():
            return {}

        result   = {}
        tokens   = []
        sym_map  = {}  # token → symbol_ns

        for sym in symbols:
            info = NSE_SYMBOL_TOKENS.get(sym)
            if info:
                tokens.append(info["token"])
                sym_map[info["token"]] = sym

        if not tokens:
            return {}

        loop = asyncio.get_event_loop()
        try:
            for i in range(0, len(tokens), 50):
                batch = tokens[i:i+50]
                resp  = await loop.run_in_executor(
                    None,
                    lambda b=batch: self.obj.getMarketData("FULL", {"NSE": b})
                )

                if not (resp and resp.get("status") and resp.get("data")):
                    # Session expire check
                    if resp and resp.get("errorCode") in ["AB1010","AB1011","AG8001"]:
                        logger.info("🔄 Angel session expired — re-login...")
                        self.auth_token = None
                        self.last_login = None
                        if await self.login():
                            resp = await loop.run_in_executor(
                                None,
                                lambda b=batch: self.obj.getMarketData("FULL", {"NSE": b})
                            )
                    if not (resp and resp.get("status") and resp.get("data")):
                        continue

                for item in resp["data"].get("fetched", []):
                    token  = str(item.get("symbolToken", ""))
                    sym_ns = sym_map.get(token)
                    if not sym_ns:
                        continue

                    ltp   = float(item.get("ltp", 0))
                    close = float(item.get("close", ltp))
                    if ltp <= 0:
                        continue

                    change_pct = round((ltp - close) / close * 100, 2) if close else 0
                    vol        = float(item.get("tradeVolume", 0))
                    avg_vol    = float(item.get("avgTradeVolume", vol or 1))
                    vol_ratio  = round(vol / avg_vol, 2) if avg_vol > 0 else 1.0

                    result[sym_ns] = {
                        "price":        round(ltp, 2),
                        "change_pct":   change_pct,
                        "open":         round(float(item.get("open", ltp)), 2),
                        "high":         round(float(item.get("high", ltp)), 2),
                        "low":          round(float(item.get("low", ltp)), 2),
                        "prev_close":   round(close, 2),
                        "volume":       int(vol),
                        "volume_ratio": max(vol_ratio, 0.1),
                        "source":       "AngelOne",
                    }

                await asyncio.sleep(0.3)

        except Exception as e:
            logger.error(f"Angel bulk data error: {e}")
            if "token" in str(e).lower() or "session" in str(e).lower():
                self.auth_token = None
                self.last_login = None

        logger.info(f"✅ AngelOne: {len(result)}/{len(symbols)} prices fetched")
        return result

    def status_text(self) -> str:
        if not all([ANGEL_API_KEY, ANGEL_CLIENT_ID, ANGEL_SECRET_KEY, ANGEL_TOTP_KEY]):
            return "❌ Angel One credentials set nahi hain Railway mein"
        if self.login_failed:
            return "❌ Angel One login failed — credentials check karo"
        if self.auth_token:
            t = self.last_login.strftime("%I:%M %p") if self.last_login else "?"
            return f"✅ Angel One connected — Login: {t}"
        return "⏳ Angel One: connecting..."


# Global Angel One session
angel = AngelOneSession()

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

async def fetch_nse_announcements(client: httpx.AsyncClient) -> list[dict]:
    """NSE official real-time corporate announcements"""
    articles = []
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://www.nseindia.com",
        }
        await client.get("https://www.nseindia.com", headers=headers)
        resp = await client.get(
            "https://www.nseindia.com/api/corporate-announcements?index=equities",
            headers=headers
        )
        if resp.status_code == 200:
            data = resp.json()
            for item in data[:30]:
                symbol  = item.get("symbol", "")
                subject = item.get("subject", "")
                company = item.get("company", "")
                bm_desc = item.get("desc", "")
                if not subject:
                    continue
                articles.append({
                    "source":   "NSE Official",
                    "type":     "corporate",
                    "headline": f"{company} ({symbol}): {subject}",
                    "summary":  bm_desc[:400] if bm_desc else subject,
                    "link":     "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
                    "symbol":   symbol,
                    "realtime": True,
                })
            logger.info(f"NSE announcements: {len(articles)} fetched")
    except Exception as e:
        logger.debug(f"NSE announcements failed: {e}")
    return articles


async def fetch_bse_announcements(client: httpx.AsyncClient) -> list[dict]:
    """BSE official real-time corporate announcements"""
    articles = []
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = await client.get(
            "https://api.bseindia.com/BseIndiaAPI/api/AnnGetData/w?strCat=-1&strType=C&strScrip=&strSector=&strPeriod=D",
            headers=headers, timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("Table", [])[:20]:
                company = item.get("SLONGNAME", "")
                subject = item.get("HEADLINE", "")
                if not subject:
                    continue
                articles.append({
                    "source":   "BSE Official",
                    "type":     "corporate",
                    "headline": f"{company}: {subject}",
                    "summary":  subject,
                    "link":     "https://www.bseindia.com/corporates/ann.html",
                    "realtime": True,
                })
            logger.info(f"BSE announcements: {len(articles)} fetched")
    except Exception as e:
        logger.debug(f"BSE announcements failed: {e}")
    return articles


async def fetch_all_news() -> list[dict]:
    all_articles = []
    portfolio["seen_headlines"] = set()

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        nse_articles = await fetch_nse_announcements(client)
        bse_articles = await fetch_bse_announcements(client)
        all_articles.extend(nse_articles)
        all_articles.extend(bse_articles)

        for feed in NEWS_FEEDS:
            try:
                resp   = await client.get(feed["url"])
                parsed = feedparser.parse(resp.text)
                for entry in parsed.entries[:10]:
                    headline = entry.get("title", "").strip()
                    if not headline:
                        continue
                    all_articles.append({
                        "source":   feed["name"],
                        "type":     feed["type"],
                        "headline": headline,
                        "summary":  entry.get("summary", "")[:400],
                        "link":     entry.get("link", ""),
                        "realtime": False,
                    })
            except Exception as e:
                logger.debug(f"Feed failed {feed['name']}: {e}")

    portfolio["last_news_time"] = datetime.datetime.now().strftime("%I:%M %p")
    realtime_count = sum(1 for a in all_articles if a.get("realtime"))
    logger.info(f"Total: {len(all_articles)} articles ({realtime_count} real-time NSE/BSE)")
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
# 💹 PRICE DATA — Angel One Primary + NSE Fallback
# ══════════════════════════════════════════════════════════════════════

async def get_nse_price(symbol: str, client: httpx.AsyncClient) -> dict | None:
    """NSE India scraping — fallback"""
    try:
        nse_sym = symbol.replace(".NS", "").replace("&", "%26")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "*/*",
            "Referer": "https://www.nseindia.com",
        }
        resp = await client.get(
            f"https://www.nseindia.com/api/quote-equity?symbol={nse_sym}",
            headers=headers, timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            pd   = data.get("priceInfo", {})
            curr = float(pd.get("lastPrice", 0))
            prev = float(pd.get("previousClose", curr))
            high = float(pd.get("intraDayHighLow", {}).get("max", curr))
            low  = float(pd.get("intraDayHighLow", {}).get("min", curr))
            if curr > 0:
                return {
                    "price":        round(curr, 2),
                    "change_pct":   round((curr - prev) / prev * 100, 2) if prev else 0,
                    "volume_ratio": 1.5,
                    "high":         round(high, 2),
                    "low":          round(low, 2),
                    "source":       "NSE-Scrape",
                }
    except Exception as e:
        logger.debug(f"NSE price failed {symbol}: {e}")
    return None


async def _nse_yfinance_fallback(symbols: list[str]) -> dict:
    """NSE scraping + yfinance fallback prices"""
    result = {}
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        try:
            await client.get("https://www.nseindia.com", headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
        except:
            pass

        for sym in symbols:
            data = await get_nse_price(sym, client)
            if data:
                result[sym] = data
            else:
                try:
                    import yfinance as yf
                    t    = yf.Ticker(sym)
                    hist = t.history(period="1d", interval="5m")
                    if not hist.empty:
                        curr = round(float(hist["Close"].iloc[-1]), 2)
                        prev = round(float(hist["Close"].iloc[0]), 2)
                        result[sym] = {
                            "price":        curr,
                            "change_pct":   round((curr - prev) / prev * 100, 2) if prev else 0,
                            "volume_ratio": 1.0,
                            "high":         round(float(hist["High"].max()), 2),
                            "low":          round(float(hist["Low"].min()), 2),
                            "source":       "yfinance",
                        }
                except:
                    pass
            await asyncio.sleep(0.15)

    logger.info(f"Fallback: {len(result)}/{len(symbols)} stocks")
    return result


async def get_price_data(symbols: list[str]) -> dict:
    """
    Live NSE prices — 3 tier system:
    1. Angel One SmartAPI (real-time LTP + OHLC + Volume) ← PRIMARY
    2. NSE website scraping ← FALLBACK
    3. yfinance ← LAST RESORT
    """
    result = {}

    # ── Tier 1: Angel One bulk market data ────────────────────────
    angel_data = await angel.get_bulk_market_data(symbols)
    result.update(angel_data)

    # ── Tier 2+3: NSE scraping + yfinance for missed symbols ──────
    missed = [s for s in symbols if s not in result]
    if missed:
        logger.info(f"📡 Fallback for {len(missed)} stocks (NSE + yfinance)...")
        fallback_data = await _nse_yfinance_fallback(missed)
        result.update(fallback_data)

    # Summary log
    angel_count    = sum(1 for d in result.values() if d.get("source") == "AngelOne")
    fallback_count = len(result) - angel_count
    logger.info(
        f"📊 Prices: {len(result)}/{len(symbols)} | "
        f"AngelOne: {angel_count} | Fallback: {fallback_count}"
    )
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

    movers_text = ""
    if price_data:
        sorted_by_move = sorted(price_data.items(), key=lambda x: abs(x[1]['change_pct']), reverse=True)
        movers_text = "\n".join([
            f"• {STOCKS.get(sym,{}).get('name',sym)}: ₹{d['price']} ({d['change_pct']:+.2f}%, Vol {d['volume_ratio']}x)"
            for sym, d in sorted_by_move[:15] if sym in STOCKS
        ])

    prompt = f"""Tu ek expert NSE swing trader hai. Sirf tab trade suggest karo jab STRONG news catalyst ho.

RULES:
- Sirf tab trade do jab strong news ho (order, result, merger, FII, policy, RBI)
- Pure price movement pe trade MAT do — found_signal: false karo
- BUY: global bullish + positive news catalyst
- SELL: global bearish + negative news catalyst
- SL: 3.5% | Target: 10.5% | R:R 1:3
- Large cap stocks only

MARKET NEWS:
{all_news_text}

STOCKS IN NEWS:
{stock_news_text if stock_news_text else "Koi specific stock news nahi"}

TOP MOVERS:
{movers_text if movers_text else "Price data unavailable"}

Respond ONLY in JSON (no markdown):
{{
  "found_signal": true,
  "global_market": "BULLISH",
  "global_reason": "SGX Nifty green",
  "symbol": "HDFCBANK.NS",
  "name": "HDFC Bank",
  "sector": "Banking",
  "direction": "BUY",
  "news_type": "FII_DII",
  "news_type_hindi": "FII ne banking mein buying ki",
  "entry": 1750.00,
  "stop_loss": 1688.75,
  "target": 1933.75,
  "risk_reward": "1:3",
  "confidence_pct": 78,
  "confidence": "HIGH",
  "smc_setup": "Strong news catalyst + volume confirmation",
  "key_news": ["FII ne ₹3200 Cr buying ki", "Volume 2x normal"],
  "impact_reason": "Strong news catalyst based trade",
  "risk_factors": "Global selloff",
  "other_stocks_impacted": ["ICICIBANK.NS"]
}}"""

    try:
        resp = await groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=800,
            temperature=0.3,
            messages=[
                {"role": "system", "content": "You are an expert NSE swing trader. Respond in valid JSON only. No markdown, no explanation."},
                {"role": "user", "content": prompt}
            ]
        )
        raw  = resp.choices[0].message.content.strip()
        raw  = raw.replace("```json","").replace("```","").strip()
        data = json.loads(raw)
        if data.get("global_market"):
            market_bias["direction"] = data["global_market"]
            market_bias["reason"]    = data.get("global_reason","")
            market_bias["updated"]   = datetime.datetime.now().strftime("%I:%M %p")
        return data if data.get("found_signal") else data
    except Exception as e:
        logger.error(f"Groq AI error: {e}")
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
    "SECTOR_ROTATION":    "🔄 Sector Rotation!",
}

def format_alert(signal: dict, stock_articles: list[dict]) -> list[str]:
    messages = []
    price    = signal["entry"]
    d_emo    = "📈" if signal["direction"] == "BUY" else "📉"
    conf_emo = "🔥" if signal["confidence"] == "HIGH" else "⚡"
    label    = NEWS_LABELS.get(signal.get("news_type",""), "📰 Market Alert!")
    qty      = max(1, int(portfolio["available"] * 0.4 / price))
    cost     = round(qty * price, 2)
    sl_pct   = round(abs(price - signal["stop_loss"]) / price * 100, 2)
    tgt_pct  = round(abs(signal["target"] - price) / price * 100, 2)
    others   = [STOCKS[s]["name"] for s in signal.get("other_stocks_impacted",[]) if s in STOCKS][:3]
    key_news = "\n".join([f"  • {n}" for n in signal.get("key_news", [])[:4]])

    g_mood   = signal.get("global_market", market_bias["direction"])
    g_emo    = {"BULLISH":"🟢 Bullish","BEARISH":"🔴 Bearish","NEUTRAL":"🟡 Neutral"}.get(g_mood,"🟡 Neutral")
    g_reason = signal.get("global_reason", market_bias.get("reason",""))

    msg1 = (
        f"🚨 *{label}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🌍 *Global Market:* {g_emo}\n"
        f"_{g_reason}_\n\n"
        f"{d_emo} *{signal['name']}* | {signal.get('sector','')}\n"
        f"{conf_emo} Confidence: {signal.get('confidence','MEDIUM')} ({signal.get('confidence_pct',65)}%)\n\n"
        f"📰 *{signal.get('news_type_hindi', signal.get('news_type',''))}*\n\n"
        + (f"🏗️ *SMC Setup:* `{signal.get('smc_setup','')}`\n\n" if signal.get('smc_setup') else "")
        + f"📌 *Key News:*\n{key_news}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 *Impact:*\n_{signal.get('impact_reason','')}_\n\n"
        f"⚠️ *Risk:* _{signal.get('risk_factors','N/A')}_\n"
        + (f"🔗 *Aur bhi dekhna:* {', '.join(others)}\n" if others else "")
        + f"\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"*{signal['direction']} Swing Trade Plan (2-3 din):*\n"
        f"📍 Entry:   ₹{signal['entry']:,.2f}\n"
        f"🛑 SL:      ₹{signal['stop_loss']:,.2f} (-{sl_pct}%)\n"
        f"🎯 Target:  ₹{signal['target']:,.2f} (+{tgt_pct}%)\n"
        f"⚖️ R:R:     {signal.get('risk_reward','1:2')}\n\n"
        f"📦 {qty} shares × ₹{price} = ₹{cost:,.0f}\n"
        f"💼 Balance: ₹{portfolio['available']:,.0f}\n"
        f"🔢 Aaj ke trades: {portfolio['trades_today']}/{MAX_TRADES_PER_DAY}\n\n"
        f"🤔 *YES* lena hai | *NO* skip karo"
    )
    messages.append(msg1)

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

async def smart_trade_manager(price_data: dict, articles: list[dict]):
    to_close = []

    for pos_key, pos in list(portfolio["positions"].items()):
        sym    = pos.get("symbol", pos_key.split("_")[0])
        if sym not in price_data:
            continue

        curr    = price_data[sym]["price"]
        is_buy  = pos["direction"] == "BUY"
        entry   = pos["entry"]
        sl      = pos["sl"]
        target  = pos["target"]
        qty     = pos["qty"]
        name    = pos["name"]
        user_id = pos.get("user_id")

        pnl     = (curr - entry) * qty if is_buy else (entry - curr) * qty
        pnl_pct = round((curr - entry) / entry * 100, 2) if is_buy else round((entry - curr) / entry * 100, 2)

        total_move   = abs(target - entry)
        curr_move    = abs(curr - entry) if (is_buy and curr > entry) or (not is_buy and curr < entry) else 0
        tgt_progress = round(curr_move / total_move * 100) if total_move > 0 else 0
        sl_dist_pct  = round(abs(curr - sl) / curr * 100, 2)

        hit_tgt = (is_buy and curr >= target) or (not is_buy and curr <= target)
        hit_sl  = (is_buy and curr <= sl)     or (not is_buy and curr >= sl)

        if hit_tgt:
            new_bal = portfolio["available"] + pos["cost"] + pnl
            msg = (
                f"🎯 *TARGET HIT! PROFIT!*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📊 *{name}*\n"
                f"Entry: ₹{entry:,.2f} → Exit: ₹{curr:,.2f}\n"
                f"Qty: {qty} | ✅ *Profit: +₹{pnl:,.0f}* (+{pnl_pct:.1f}%)\n"
                f"💼 New Balance: ₹{new_bal:,.0f}\n\n"
                f"🎉 Zabardast trade bhai!"
            )
            await _send_to_user(user_id, msg)
            to_close.append((pos_key, pnl, pos["cost"]))

        elif hit_sl:
            new_bal = portfolio["available"] + pos["cost"] + pnl
            msg = (
                f"🛑 *STOP LOSS HIT!*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📊 *{name}*\n"
                f"Entry: ₹{entry:,.2f} → Exit: ₹{curr:,.2f}\n"
                f"Qty: {qty} | ❌ *Loss: ₹{pnl:,.0f}* ({pnl_pct:.1f}%)\n"
                f"💼 Balance: ₹{new_bal:,.0f}\n\n"
                f"💪 SL ne protect kiya — agli trade mein recover karenge!"
            )
            await _send_to_user(user_id, msg)
            to_close.append((pos_key, pnl, pos["cost"]))

        else:
            stock_arts = [a for a in articles if sym.replace(".NS","").lower() in (a["headline"]+a["summary"]).lower()]
            bad_news_keywords  = ["loss","fall","down","decline","weak","negative","bearish","sell","downgrade","cut","concern","risk","crash","drop"]
            good_news_keywords = ["profit","rise","up","growth","strong","positive","bullish","buy","upgrade","order","win","record","high","beat"]
            news_text     = " ".join([a["headline"] for a in stock_arts]).lower()
            has_bad_news  = any(kw in news_text for kw in bad_news_keywords)
            has_good_news = any(kw in news_text for kw in good_news_keywords)

            is_going_toward_target = (is_buy and curr > entry) or (not is_buy and curr < entry)
            sharp_reversal = False

            if is_going_toward_target and tgt_progress >= 20 and has_bad_news:
                sharp_reversal = True
                bad_arts = [a for a in stock_arts if any(kw in a["headline"].lower() for kw in bad_news_keywords)]
                alert_msg = (
                    f"🚨 *TURANT ALERT — REVERSAL + BAD NEWS!*\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📊 *{name}*\n"
                    f"Entry: ₹{entry:,.2f} | Current: ₹{curr:,.2f}\n"
                    f"P&L abhi: {'+'if pnl>=0 else ''}₹{pnl:,.0f} ({pnl_pct:+.1f}%)\n"
                    f"Target: ₹{target:,.2f} | Progress: {tgt_progress}%\n\n"
                    f"⚠️ *Bad News aa gayi:*\n"
                    + "\n".join([f"  • _{a['headline'][:100]}_" for a in bad_arts[:3]])
                    + f"\n\n💡 *Kya karna hai:*\n"
                    f"• Profit hai → Exit consider karo\n"
                    f"• Loss hai → SL ka wait karo ya cut karo\n"
                    f"• Apna judgment use karo!"
                )
                await _send_to_user(user_id, alert_msg)

            elif not is_going_toward_target and has_good_news and not pos.get("good_news_alerted"):
                pos["good_news_alerted"] = True
                good_arts = [a for a in stock_arts if any(kw in a["headline"].lower() for kw in good_news_keywords)]
                alert_msg = (
                    f"💡 *GOOD NEWS — POSITION KE FAVOR MEIN!*\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📊 *{name}*\n"
                    f"Current: ₹{curr:,.2f} | P&L: {'+'if pnl>=0 else ''}₹{pnl:,.0f}\n\n"
                    f"✅ *Positive News:*\n"
                    + "\n".join([f"  • _{a['headline'][:100]}_" for a in good_arts[:3]])
                    + f"\n\n📈 *Position strong ho sakti hai — hold karo!*"
                )
                await _send_to_user(user_id, alert_msg)

            if not sharp_reversal and stock_arts:
                good_arts = [a for a in stock_arts if any(kw in a["headline"].lower() for kw in good_news_keywords)]
                bad_arts  = [a for a in stock_arts if any(kw in a["headline"].lower() for kw in bad_news_keywords)]

                # Spam fix — sirf naya news bhejo, same news baar baar nahi
                last_sent = pos.get("last_news_headlines", set())
                new_good  = [a for a in good_arts if a["headline"] not in last_sent]
                new_bad   = [a for a in bad_arts  if a["headline"] not in last_sent]

                if new_good or new_bad:
                    news_msg  = f"📰 *{name} — News Update:*\n━━━━━━━━━━━━━━━━━━\n"
                    news_msg += f"Current: ₹{curr:,.2f} | P&L: {'+'if pnl>=0 else ''}₹{pnl:,.0f} ({pnl_pct:+.1f}%)\n"
                    news_msg += f"Target Progress: {tgt_progress}%\n\n"
                    if new_good:
                        news_msg += "✅ *Good News:*\n"
                        for a in new_good[:3]:
                            news_msg += f"  • _{a['headline'][:100]}_\n"
                    if new_bad:
                        news_msg += "\n⚠️ *Bad News:*\n"
                        for a in new_bad[:3]:
                            news_msg += f"  • _{a['headline'][:100]}_\n"
                    await _send_to_user(user_id, news_msg)

                    # Update seen headlines
                    pos["last_news_headlines"] = last_sent | {a["headline"] for a in good_arts+bad_arts}

            if tgt_progress >= 80 and has_bad_news:
                msg = (
                    f"⚠️ *EXIT NOW — TARGET NEAR + BAD NEWS!*\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📊 *{name}* — {tgt_progress}% target complete\n"
                    f"Current: ₹{curr:,.2f} | P&L: +₹{pnl:,.0f}\n\n"
                    f"📰 *Bad news aa rahi hai:*\n"
                    + "\n".join([f"• {a['headline'][:80]}" for a in stock_arts[:2]])
                    + f"\n\n💡 *Profit book karo abhi!*"
                )
                await _send_to_user(user_id, msg)

            elif sl_dist_pct <= 1.0 and has_good_news:
                msg = (
                    f"💡 *HOLD — NEWS SUPPORT HAI!*\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📊 *{name}* — SL ke paas hai\n"
                    f"Current: ₹{curr:,.2f} | SL: ₹{sl:,.2f}\n\n"
                    f"📰 *Good news support de rahi hai:*\n"
                    + "\n".join([f"• {a['headline'][:80]}" for a in stock_arts[:2]])
                    + f"\n\n⚡ Position hold karo!"
                )
                await _send_to_user(user_id, msg)

            elif tgt_progress >= 50 and not pos.get("trailed"):
                new_sl = round(entry * 1.01, 2) if is_buy else round(entry * 0.99, 2)
                pos["trailed"] = True
                msg = (
                    f"📈 *TRAIL SL KARO! {tgt_progress}% TARGET DONE!*\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📊 *{name}*\n"
                    f"Current: ₹{curr:,.2f} | P&L: +₹{pnl:,.0f}\n\n"
                    f"🛑 *Old SL: ₹{sl:,.2f}*\n"
                    f"✅ *New SL: ₹{new_sl:,.2f}* (breakeven)\n\n"
                    f"💡 Apne broker mein SL update karo — loss impossible ab!"
                )
                pos["sl"] = new_sl
                await _send_to_user(user_id, msg)

    for pos_key, pnl, cost in to_close:
        portfolio["available"] += cost + pnl
        if pnl > 0:
            portfolio["win_count"] += 1
        portfolio["closed_trades"].append({
            "sym":       pos_key,
            "pnl":       pnl,
            "time":      datetime.datetime.now().strftime("%d %b %Y %I:%M %p"),
            "open_time": portfolio["positions"].get(pos_key, {}).get("open_time", "N/A"),
            "entry":     portfolio["positions"].get(pos_key, {}).get("entry", 0),
            "exit":      price_data.get(pos_key.split("_")[0], {}).get("price", 0),
            "direction": portfolio["positions"].get(pos_key, {}).get("direction", ""),
        })
        if pos_key in portfolio["positions"]:
            del portfolio["positions"][pos_key]


async def _send_to_user(user_id: str | None, msg: str):
    if user_id:
        try:
            await bot_app.bot.send_message(chat_id=user_id, text=msg, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Send failed: {e}")
    else:
        await send_to_all(msg)


async def check_positions(price_data: dict, articles: list[dict] = []):
    await smart_trade_manager(price_data, articles)

# ══════════════════════════════════════════════════════════════════════
# 🔍 MAIN SCAN
# ══════════════════════════════════════════════════════════════════════

async def run_scan(silent: bool = False):
    portfolio["last_scan_time"] = datetime.datetime.now().strftime("%d %b, %I:%M %p")
    if not silent:
        await send_to_all(
            f"🔍 *Market scan shuru...*\n"
            f"⚡ NSE/BSE real-time announcements\n"
            f"📰 {len(NEWS_FEEDS)} RSS news sources\n"
            f"📊 {len(STOCKS)} NSE stocks\n"
            f"🔌 {angel.status_text()}"
        )

    articles   = await fetch_all_news()
    price_data = await get_price_data(list(STOCKS.keys()))
    if price_data:
        await check_positions(price_data, articles)

    stock_news = match_news_to_stocks(articles)
    result     = await ai_analyze_news(articles, stock_news, price_data)
    portfolio["total_signals"] += 1

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
        # Koi strong news signal nahi — koi trade nahi
        open_count = len(portfolio["positions"])
        await send_to_all(
            f"📭 *Scan complete — Koi strong signal nahi*\n"
            f"📰 {len(articles)} news analyze ki\n"
            f"🔗 {len(stock_news)} stocks mention hue\n"
            f"📂 Open positions: {open_count}/{MAX_OPEN_POSITIONS}\n"
            f"⏳ Agli scan {SCAN_INTERVAL_MIN} min mein\n"
            f"_Sirf strong news pe trade hoga — patience rakho!_ 💪"
        )



async def is_market_open() -> bool:
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
    if now.weekday() >= 5:
        return False
    market_open  = now.replace(hour=9,  minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open <= now <= market_close


async def position_monitor_loop():
    await asyncio.sleep(60)
    while True:
        try:
            if portfolio["positions"] and await is_market_open():
                price_data = await get_price_data(list(STOCKS.keys()))
                if price_data:
                    articles = await fetch_all_news()
                    await check_positions(price_data, articles)
        except Exception as e:
            logger.error(f"Position monitor error: {e}")
        await asyncio.sleep(5 * 60)


async def send_daily_report():
    """3:30 PM pe automatic Daily P&L Report — dono ko"""
    IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    now = datetime.datetime.now(IST)

    closed    = portfolio["closed_trades"]
    open_pos  = portfolio["positions"]
    net_worth = portfolio["available"] + sum(p["cost"] for p in open_pos.values())
    total_pnl = sum(t["pnl"] for t in closed)
    overall_pnl_pct = round((net_worth - PAPER_CAPITAL) / PAPER_CAPITAL * 100, 2)

    today_str    = now.strftime("%d %b %Y")
    today_trades = [t for t in closed if today_str in t.get("time", "")]
    today_pnl    = sum(t["pnl"] for t in today_trades)
    today_wins   = sum(1 for t in today_trades if t["pnl"] > 0)
    today_losses = len(today_trades) - today_wins

    open_pnl   = 0
    price_data = {}
    if open_pos:
        syms       = list(set(p.get("symbol", k.split("_")[0]) for k, p in open_pos.items()))
        price_data = await get_price_data(syms)
        for pos_key, pos in open_pos.items():
            sym    = pos.get("symbol", pos_key.split("_")[0])
            curr   = price_data.get(sym, {}).get("price", pos["entry"])
            is_buy = pos["direction"] == "BUY"
            open_pnl += (curr - pos["entry"]) * pos["qty"] if is_buy else (pos["entry"] - curr) * pos["qty"]

    wins         = portfolio["win_count"]
    total_closed = len(closed)
    win_rate     = round(wins / total_closed * 100, 1) if total_closed else 0
    day_emo      = "🎉" if today_pnl > 0 else ("😐" if today_pnl == 0 else "😔")
    tot_emo      = "🚀" if total_pnl > 0 else ("😐" if total_pnl == 0 else "📉")

    msg = (
        f"🌅 *AAJ KA REPORT — {today_str}* {day_emo}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📅 *Aaj ka P&L:*\n"
        f"{'✅' if today_pnl >= 0 else '❌'} Closed trades: {'+'if today_pnl>=0 else ''}₹{today_pnl:,.0f}\n"
        f"📂 Open positions P&L: {'+'if open_pnl>=0 else ''}₹{open_pnl:,.0f}\n"
        f"🏆 Aaj ke trades: {len(today_trades)} (✅{today_wins} ❌{today_losses})\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{tot_emo} *Overall Performance:*\n"
        f"💰 Capital: ₹{PAPER_CAPITAL:,.0f}\n"
        f"💼 Net Worth: ₹{net_worth:,.0f}\n"
        f"{'📈' if total_pnl>=0 else '📉'} Total P&L: {'+'if total_pnl>=0 else ''}₹{total_pnl:,.0f} ({'+' if overall_pnl_pct>=0 else ''}{overall_pnl_pct}%)\n"
        f"🎯 Win Rate: {win_rate}% ({wins}W/{total_closed-wins}L)\n\n"
    )

    if open_pos:
        msg += f"📂 *Open Positions (carry forward):*\n"
        for pos_key, pos in open_pos.items():
            sym      = pos.get("symbol", pos_key.split("_")[0])
            curr     = price_data.get(sym, {}).get("price", pos["entry"])
            is_buy   = pos["direction"] == "BUY"
            live_pnl = (curr - pos["entry"]) * pos["qty"] if is_buy else (pos["entry"] - curr) * pos["qty"]
            live_pct = round(live_pnl / pos["cost"] * 100, 2)
            total_move = abs(pos["target"] - pos["entry"])
            curr_move  = abs(curr - pos["entry"]) if (is_buy and curr > pos["entry"]) or (not is_buy and curr < pos["entry"]) else 0
            progress   = round(curr_move / total_move * 100) if total_move > 0 else 0
            msg += (
                f"{'📈' if is_buy else '📉'} *{pos['name']}*\n"
                f"   Entry: ₹{pos['entry']:,.2f} | Now: ₹{curr:,.2f}\n"
                f"   P&L: {'+'if live_pnl>=0 else ''}₹{live_pnl:,.0f} ({'+' if live_pct>=0 else ''}{live_pct}%)\n"
                f"   Progress: {progress}% | SL: ₹{pos['sl']:,.2f} | T: ₹{pos['target']:,.2f}\n\n"
            )

    if today_trades:
        msg += f"📜 *Aaj ke Closed Trades:*\n"
        for t in today_trades:
            emo = "✅" if t["pnl"] >= 0 else "❌"
            msg += f"{emo} {t['sym'].split('_')[0]}: {'+'if t['pnl']>=0 else ''}₹{t['pnl']:,.0f}\n"

    msg += f"\n_Market kal 9:15 AM pe khulega. Good night! 🌙_"
    await send_to_all(msg)
    logger.info("📊 Daily report sent!")


async def daily_report_loop():
    """Roz 3:30 PM IST pe daily report — market close ke baad"""
    IST           = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    reported_today = None
    await asyncio.sleep(120)
    while True:
        try:
            now   = datetime.datetime.now(IST)
            today = now.date()
            market_close_time = now.replace(hour=15, minute=31, second=0, microsecond=0)
            if now >= market_close_time and now.weekday() < 5 and reported_today != today:
                reported_today = today
                await send_daily_report()
        except Exception as e:
            logger.error(f"Daily report error: {e}")
        await asyncio.sleep(60)


async def scan_loop():
    await asyncio.sleep(30)
    while True:
        try:
            if await is_market_open():
                await run_scan()
            else:
                IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
                now = datetime.datetime.now(IST)
                logger.info(f"Market band hai — {now.strftime('%I:%M %p')} IST | Next open: 9:15 AM")
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
        "Commands: /scan /news /portfolio /summary /status /help",
        parse_mode="Markdown"
    )


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Angel One + Agent live status"""
    market_status = "🟢 OPEN" if await is_market_open() else "🔴 CLOSED"
    reset_daily_limit()

    # Source breakdown
    source_info = ""
    if angel.auth_token:
        source_info = "📊 Price Source: Angel One SmartAPI (Live)"
    elif angel.login_failed:
        source_info = "📊 Price Source: NSE Fallback (Angel One failed)"
    else:
        source_info = "📊 Price Source: NSE Scraping (Angel One connecting...)"

    msg = (
        f"🔌 *Angel One SmartAPI*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{angel.status_text()}\n\n"
        f"📈 *Market:* {market_status}\n"
        f"{source_info}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💼 *Portfolio:*\n"
        f"💰 Available: ₹{portfolio['available']:,.0f}\n"
        f"📂 Open Positions: {len(portfolio['positions'])}\n"
        f"🔢 Aaj ke Trades: {portfolio['trades_today']}/{MAX_TRADES_PER_DAY}\n"
        f"🕐 Last Scan: {portfolio.get('last_scan_time', 'N/A')}\n\n"
        f"🌍 *Market Bias:* {market_bias['direction']}\n"
        f"_{market_bias.get('reason', 'N/A')}_"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


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
    losses    = len(closed) - wins
    win_rate  = round(wins / len(closed) * 100, 1) if closed else 0
    open_pos  = portfolio["positions"]
    net_worth = portfolio["available"] + sum(p["cost"] for p in open_pos.values())
    overall_pnl_pct = round((net_worth - PAPER_CAPITAL) / PAPER_CAPITAL * 100, 2)

    price_data = {}
    if open_pos:
        syms       = list(set(p.get("symbol", k.split("_")[0]) for k, p in open_pos.items()))
        price_data = await get_price_data(syms)

    msg1 = (
        f"📊 *FULL TRADING DASHBOARD*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 *Capital:* ₹{PAPER_CAPITAL:,.0f}\n"
        f"💼 *Net Worth:* ₹{net_worth:,.0f}\n"
        f"{'📈' if total_pnl>=0 else '📉'} *Total P&L:* {'+'if total_pnl>=0 else ''}₹{total_pnl:,.0f} ({'+' if overall_pnl_pct>=0 else ''}{overall_pnl_pct}%)\n"
        f"💵 *Available:* ₹{portfolio['available']:,.0f}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 *Trade Stats:*\n"
        f"✅ Wins:    {wins}\n"
        f"❌ Losses:  {losses}\n"
        f"🎯 Win Rate: {win_rate}%\n"
        f"📦 Total Trades: {len(closed)}\n"
        f"🔢 Aaj ke trades: {portfolio['trades_today']}/{MAX_TRADES_PER_DAY}\n"
        f"\n🔌 {angel.status_text()}"
    )
    await update.message.reply_text(msg1, parse_mode="Markdown")

    if open_pos:
        lines = ["📂 *OPEN POSITIONS:*\n━━━━━━━━━━━━━━━━━━"]
        for pos_key, pos in open_pos.items():
            sym    = pos.get("symbol", pos_key.split("_")[0])
            curr   = price_data.get(sym, {}).get("price", pos["entry"])
            is_buy = pos["direction"] == "BUY"
            live_pnl     = (curr - pos["entry"]) * pos["qty"] if is_buy else (pos["entry"] - curr) * pos["qty"]
            live_pnl_pct = round(live_pnl / pos["cost"] * 100, 2)
            total_move   = abs(pos["target"] - pos["entry"])
            curr_move    = abs(curr - pos["entry"]) if (is_buy and curr > pos["entry"]) or (not is_buy and curr < pos["entry"]) else 0
            progress     = round(curr_move / total_move * 100) if total_move > 0 else 0

            bars     = int(progress / 10)
            prog_bar = "🟢" * bars + "⬜" * (10 - bars)

            open_date = pos.get("open_date")
            if open_date:
                days_open  = (datetime.datetime.now() - datetime.datetime.fromisoformat(open_date)).days
                hours_open = int((datetime.datetime.now() - datetime.datetime.fromisoformat(open_date)).seconds / 3600)
                time_str   = f"{days_open} din {hours_open} ghante" if days_open > 0 else f"{hours_open} ghante"
            else:
                time_str = "N/A"

            # Price source tag
            src = price_data.get(sym, {}).get("source", "?")
            lines.append(
                f"\n{'📈' if is_buy else '📉'} *{pos['name']}*\n"
                f"🕐 Open: {pos.get('open_time', 'N/A')} ({time_str} se)\n"
                f"Entry: ₹{pos['entry']:,.2f} | Now: ₹{curr:,.2f} _[{src}]_\n"
                f"SL: ₹{pos['sl']:,.2f} | Target: ₹{pos['target']:,.2f}\n"
                f"P&L: {'+'if live_pnl>=0 else ''}₹{live_pnl:,.0f} ({'+' if live_pnl_pct>=0 else ''}{live_pnl_pct}%)\n"
                f"Progress: {prog_bar} {progress}%\n"
                f"Qty: {pos['qty']} shares | Cost: ₹{pos['cost']:,.0f}"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    else:
        await update.message.reply_text("📭 *Koi open position nahi hai abhi*", parse_mode="Markdown")

    if closed:
        lines = ["📜 *CLOSED TRADES HISTORY:*\n━━━━━━━━━━━━━━━━━━"]
        for i, t in enumerate(closed[-10:], 1):
            emoji = "✅" if t["pnl"] >= 0 else "❌"
            lines.append(
                f"\n{emoji} *{i}. {t['sym'].split('_')[0]}*\n"
                f"   {'📈 BUY' if t.get('direction')=='BUY' else '📉 SELL'} | "
                f"Entry: ₹{t.get('entry',0):,.2f} → Exit: ₹{t.get('exit',0):,.2f}\n"
                f"   P&L: {'+'if t['pnl']>=0 else ''}₹{t['pnl']:,.0f}\n"
                f"   🕐 Open: {t.get('open_time','N/A')}\n"
                f"   🏁 Close: {t.get('time','N/A')}"
            )
        lines.append(f"\n💰 *Total Closed P&L: {'+'if total_pnl>=0 else ''}₹{total_pnl:,.0f}*")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    else:
        await update.message.reply_text("📭 *Abhi tak koi trade close nahi hua*", parse_mode="Markdown")


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
        "/summary — P&L dashboard\n"
        "/status — Angel One + agent status",
        parse_mode="Markdown"
    )

# ══════════════════════════════════════════════════════════════════════
# 💬 YES / NO
# ══════════════════════════════════════════════════════════════════════

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text    = update.message.text.strip().upper()
    signal  = portfolio.get("pending_signal")
    user_id = str(update.effective_user.id)

    if not signal:
        await update.message.reply_text("⚠️ Koi pending signal nahi. /scan karo.")
        return

    if text == "YES":
        if not can_trade():
            await update.message.reply_text(
                f"⛔ Aaj ke {MAX_TRADES_PER_DAY} trades ho gaye!\n"
                f"Kal subah naya din — phir le lena. 😄"
            )
            return

        trade_key = f"{signal['symbol']}_{user_id}"
        if trade_key in portfolio.get("user_trades", set()):
            await update.message.reply_text("⚠️ Tune yeh trade already le liya hai!")
            return

        price = signal["entry"]
        qty   = max(1, int(portfolio["available"] * 0.4 / price))
        cost  = round(qty * price, 2)

        if cost > portfolio["available"]:
            await update.message.reply_text(
                f"❌ Capital kam! Cost: ₹{cost:,.0f} | Bal: ₹{portfolio['available']:,.0f}"
            )
            return

        portfolio["available"] -= cost
        portfolio["positions"][f"{signal['symbol']}_{user_id}"] = {
            "name":      signal["name"],
            "symbol":    signal["symbol"],
            "qty":       qty,
            "entry":     price,
            "sl":        signal["stop_loss"],
            "target":    signal["target"],
            "direction": signal["direction"],
            "cost":      cost,
            "user_id":   user_id,
            "open_time": datetime.datetime.now().strftime("%d %b %Y, %I:%M %p"),
            "open_date": datetime.datetime.now().isoformat(),
        }
        if "user_trades" not in portfolio:
            portfolio["user_trades"] = set()
        portfolio["user_trades"].add(trade_key)

        portfolio["trades_today"] += 1
        left = trades_left()

        bot: Bot = bot_app.bot
        try:
            await bot.send_message(
                chat_id=user_id,
                text=(
                    f"✅ *Tera Trade Open!*\n"
                    f"{'📈' if signal['direction']=='BUY' else '📉'} *{signal['name']}*\n"
                    f"{signal['direction']} {qty} shares @ ₹{price:,.2f}\n"
                    f"SL: ₹{signal['stop_loss']:,.2f} | T: ₹{signal['target']:,.2f}\n"
                    f"💼 Balance: ₹{portfolio['available']:,.0f}\n"
                    f"🔢 Trades: {portfolio['trades_today']}/{MAX_TRADES_PER_DAY}"
                    + (f" | {left} aur bache" if left > 0 else " | Aaj bas itne!")
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Confirm msg failed: {e}")

        user_name = update.effective_user.first_name or "Someone"
        await send_to_all(
            f"📊 *{user_name} ne trade liya!*\n"
            f"{'📈' if signal['direction']=='BUY' else '📉'} *{signal['name']}*\n"
            f"{signal['direction']} {qty} shares @ ₹{price:,.2f}\n\n"
            f"_Doosra bhi YES bhej sakta hai apna trade lene ke liye!_"
        )

        closed    = portfolio["closed_trades"]
        total_pnl = sum(t["pnl"] for t in closed)
        wins      = portfolio["win_count"]
        win_rate  = round(wins / len(closed) * 100, 1) if closed else 0
        open_pos  = len(portfolio["positions"])
        net_worth = portfolio["available"] + sum(p["cost"] for p in portfolio["positions"].values())

        await send_to_all(
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📈 *Portfolio Summary*\n"
            f"💰 Capital: ₹{PAPER_CAPITAL:,.0f}\n"
            f"💼 Net Worth: ₹{net_worth:,.0f}\n"
            f"{'📈' if total_pnl>=0 else '📉'} Total P&L: {'+'if total_pnl>=0 else ''}₹{total_pnl:,.0f}\n"
            f"📂 Open Positions: {open_pos}\n"
            f"✅ Wins: {wins} | ❌ Loss: {len(closed)-wins} | 🎯 {win_rate}%\n"
            f"🔢 Aaj ke trades: {portfolio['trades_today']}/{MAX_TRADES_PER_DAY}"
        )

    elif text == "NO":
        user_name = update.effective_user.first_name or "Someone"
        bot: Bot = bot_app.bot
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"👍 *{user_name}* ne skip kiya — *{signal['name']}*",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(e)
    else:
        await update.message.reply_text("Sirf *YES* ya *NO* bhejo! 😄", parse_mode="Markdown")

# ══════════════════════════════════════════════════════════════════════
# 🚀 LAUNCH
# ══════════════════════════════════════════════════════════════════════

async def main():
    global bot_app
    missing = [k for k in ["TELEGRAM_BOT_TOKEN", "MY_CHAT_ID", "GROQ_API_KEY"] if not os.environ.get(k)]
    if missing:
        raise ValueError(f"Missing env vars: {missing}")

    # ── Angel One startup login ──────────────────────────────────────
    logger.info("🔌 Angel One SmartAPI se connect ho raha hoon...")
    angel_ok = await angel.login()
    if angel_ok:
        logger.info("✅ Angel One connected — Live prices milenge!")
    else:
        logger.warning("⚠️  Angel One login failed — NSE fallback use hoga")

    # ── Telegram bot setup ───────────────────────────────────────────
    bot_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    for cmd, fn in [
        ("start",     cmd_start),
        ("status",    cmd_status),
        ("scan",      cmd_scan),
        ("news",      cmd_news),
        ("portfolio", cmd_portfolio),
        ("summary",   cmd_summary),
        ("help",      cmd_help),
    ]:
        bot_app.add_handler(CommandHandler(cmd, fn))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling(drop_pending_updates=True)

    # ── Startup message ──────────────────────────────────────────────
    angel_line = (
        "🔌 Angel One: ✅ Connected — Live prices ON!"
        if angel_ok else
        "🔌 Angel One: ⚠️ Fallback mode (NSE scraping)"
    )
    await send_to_all(
        f"🟢 *NSE News Intelligence Agent Online!*\n"
        f"💼 Capital: ₹{PAPER_CAPITAL:,.0f}\n"
        f"📰 {len(NEWS_FEEDS)} news sources monitor ho rahi hain\n"
        f"📊 {len(STOCKS)} NSE stocks track ho rahe hain\n"
        f"🔍 Scan: Har {SCAN_INTERVAL_MIN} min\n"
        f"🤖 AI: Groq (Llama 3.3 70B) — FREE!\n"
        f"📂 Max Open Positions: {MAX_OPEN_POSITIONS}\n"
        f"⚡ Sirf strong news pe trade hoga!\n"
        f"{angel_line}\n\n"
        "Pehla scan 30 sec mein! 🚀"
    )

    asyncio.create_task(scan_loop())
    asyncio.create_task(position_monitor_loop())
    asyncio.create_task(daily_report_loop())
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
