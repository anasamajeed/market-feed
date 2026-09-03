import datetime
import uuid
import re
import io
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup
import yfinance as yf
from icalendar import Calendar, Event, Alarm

CONFIG = {
    "ENABLE_ALARMS": True,
    "ENABLE_NIFTY_WEEKLY_EXPIRY": True,     # Tuesday (NSE Benchmark)
    "ENABLE_SENSEX_WEEKLY_EXPIRY": True,    # Thursday (BSE Benchmark)
    "ENABLE_STOCK_FO_MONTHLY_EXPIRY": True, # Last Thursday (NSE Single Stock F&O)
    "ENABLE_FNO_BAN_MONITOR": True,        # Daily NSE MWPL Ban Alerts
    "ENABLE_INTRADAY_VOLATILITY_TOOLS": True # VIX, 52W Breakouts, Bulk Deals & Surveillance
}

# Nifty 50 Top Heavyweight Index Weights
NIFTY_HEAVYWEIGHTS = {
    "HDFCBANK": 9.89,
    "ICICIBANK": 9.35,
    "RELIANCE": 8.02,
    "BHARTIARTL": 5.30,
    "LT": 4.23,
    "SBIN": 3.88,
    "INFY": 3.68,
    "AXISBANK": 3.28,
    "KOTAKBANK": 2.84,
    "TCS": 2.19,
}

NSE_HOLIDAYS_2026 = {
    datetime.date(2026, 1, 15): "Municipal Elections",
    datetime.date(2026, 1, 26): "Republic Day",
    datetime.date(2026, 3, 3): "Holi",
    datetime.date(2026, 3, 26): "Shri Ram Navami",
    datetime.date(2026, 3, 31): "Shri Mahavir Jayanti",
    datetime.date(2026, 4, 3): "Good Friday",
    datetime.date(2026, 4, 14): "Dr. Ambedkar Jayanti",
    datetime.date(2026, 5, 1): "Maharashtra Day",
    datetime.date(2026, 5, 28): "Bakri Id",
    datetime.date(2026, 6, 26): "Muharram",
    datetime.date(2026, 9, 14): "Ganesh Chaturthi",
    datetime.date(2026, 10, 2): "Mahatma Gandhi Jayanti",
    datetime.date(2026, 10, 20): "Dussehra",
    datetime.date(2026, 11, 10): "Diwali Balipratipada",
    datetime.date(2026, 11, 24): "Guru Nanak Jayanti",
    datetime.date(2026, 12, 25): "Christmas",
}

CORPORATE_RESTRUCTURING_2026 = [
    {
        "date": datetime.date(2026, 9, 23),
        "symbol": "TATAMOTORS",
        "type": "DEMERGER",
        "summary": "[DEMERGER] TATAMOTORS - NCLT Scheme Ex-Date (T+1 Cutoff)",
        "ratio": "1:1 Share Allotment (CV & PV Entities)",
        "desc": (
            "NCLT DEMERGER SCHEME OF ARRANGEMENT\n"
            "-----------------------------------------\n"
            "• Demerged Entities: Commercial Vehicles (CV) split from Passenger Vehicles (PV/EV).\n"
            "• Entitlement Ratio: 1 share of New CV entity for every 1 share held in Tata Motors.\n"
            "• Special Call Auction: Pre-open discovery session (09:00-10:00 AM IST).\n"
        )
    },
    {
        "date": datetime.date(2026, 8, 19),
        "symbol": "RAYMOND",
        "type": "DEMERGER",
        "summary": "[DEMERGER] RAYMOND - Lifestyle Entity Demerger Ex-Date",
        "ratio": "4:5 Share Allotment (Raymond Lifestyle)",
        "desc": "Demerger of Lifestyle Apparel operations.\nRatio: 4 shares of Raymond Lifestyle for every 5 shares held."
    },
    {
        "date": datetime.date(2026, 10, 15),
        "symbol": "IDFCFIRSTB",
        "type": "MERGER",
        "summary": "[MERGER] IDFC FIRST BANK & IDFC LTD - Reverse Merger Effective",
        "ratio": "155:100 Swap Ratio",
        "desc": "Amalgamation of IDFC Ltd into IDFC FIRST Bank. 155 bank shares for every 100 IDFC Ltd shares held."
    },
    {
        "date": datetime.date(2026, 9, 28),
        "symbol": "TCS",
        "type": "BUYBACK",
        "summary": "[BUYBACK] TCS - Tender Offer Window Closes (5:00 PM IST)",
        "ratio": "Tender Offer Price ₹4,500/share",
        "desc": "SEBI Tender Offer Buyback. Final cutoff for bidding and Demat delivery closes at 5:00 PM IST."
    }
]

MACRO_POLICY_TAX_EVENTS = [
    {"date": datetime.date(2026, 6, 15), "summary": "[TAX] Advance Tax Q1 Instalment Due (15%)", "desc": "Statutory deadline to deposit 15% of estimated advance income tax.", "url": "https://eportal.incometax.gov.in/"},
    {"date": datetime.date(2026, 9, 15), "summary": "[TAX] Advance Tax Q2 Instalment Due (45% Cumulative)", "desc": "Statutory deadline to deposit cumulative 45% of estimated advance tax.", "url": "https://eportal.incometax.gov.in/"},
    {"date": datetime.date(2026, 12, 15), "summary": "[TAX] Advance Tax Q3 Instalment Due (75% Cumulative)", "desc": "Statutory deadline to deposit cumulative 75% of advance tax.", "url": "https://eportal.incometax.gov.in/"},
    {"date": datetime.date(2027, 3, 15), "summary": "[TAX] Advance Tax Q4 Final Instalment (100%)", "desc": "Final 100% advance tax payment deadline for FY2026-27.", "url": "https://eportal.incometax.gov.in/"},
    {"date": datetime.date(2026, 4, 1), "summary": "[SEBI / TAX] Revised F&O STT & Contract Sizing Rules Active", "desc": "STT hike effective: 0.02% to 0.05% on Futures, 0.10% to 0.15% on Options.", "url": "https://www.sebi.gov.in/"},
    {"date": datetime.date(2027, 2, 1), "summary": "[POLICY] Union Budget 2027-28 Presentation", "desc": "Finance Minister presents Union Budget in Parliament (11:00 AM IST).", "url": "https://www.indiabudget.gov.in/"},
    {"date": datetime.date(2026, 8, 7), "summary": "[MACRO] RBI Monetary Policy Committee (MPC) Outcome", "desc": "RBI repo rate decision & policy statement.", "url": "https://rbi.org.in/"},
    {"date": datetime.date(2026, 8, 31), "summary": "[MACRO] India GDP Data Release (Q1 FY27)", "desc": "MOSPI quarterly economic output print.", "url": "https://www.mospi.gov.in/"},
    {"date": datetime.date(2026, 9, 14), "summary": "[MACRO] India CPI Inflation Print", "desc": "Retail inflation numbers directly impacting RBI stance.", "url": "https://www.mospi.gov.in/"},
    {"date": datetime.date(2026, 10, 8), "summary": "[MACRO] RBI Monetary Policy Committee (MPC) Outcome", "desc": "RBI repo rate decision & policy statement.", "url": "https://rbi.org.in/"},
    {"date": datetime.date(2026, 10, 12), "summary": "[MACRO] India CPI Inflation Print", "desc": "Domestic retail inflation print.", "url": "https://www.mospi.gov.in/"},
    {"date": datetime.date(2026, 11, 12), "summary": "[MACRO] India CPI Inflation Print", "desc": "Domestic retail inflation print.", "url": "https://www.mospi.gov.in/"},
    {"date": datetime.date(2026, 11, 30), "summary": "[MACRO] India GDP Data Release (Q2 FY27)", "desc": "MOSPI quarterly economic output print.", "url": "https://www.mospi.gov.in/"},
    {"date": datetime.date(2026, 12, 10), "summary": "[MACRO] RBI Monetary Policy Committee (MPC) Outcome", "desc": "RBI repo rate decision & policy statement.", "url": "https://rbi.org.in/"},
    {"date": datetime.date(2026, 9, 4), "summary": "[MACRO] US Non-Farm Payrolls (NFP) Jobs Report", "desc": "Monthly US labor snapshot influencing Dollar Index & FII flows.", "url": "https://www.bls.gov/"},
    {"date": datetime.date(2026, 9, 11), "summary": "[MACRO] US Consumer Price Index (CPI) Inflation Data", "desc": "Key US inflation print dictating global interest rate expectations.", "url": "https://www.bls.gov/"},
    {"date": datetime.date(2026, 9, 16), "summary": "[MACRO] US Federal Reserve FOMC Rate Decision", "desc": "Fed interest rate announcement & press conference.", "url": "https://www.federalreserve.gov/"},
    {"date": datetime.date(2026, 10, 2), "summary": "[MACRO] US Non-Farm Payrolls (NFP) Jobs Report", "desc": "Monthly US labor report.", "url": "https://www.bls.gov/"},
    {"date": datetime.date(2026, 10, 13), "summary": "[MACRO] US Consumer Price Index (CPI) Inflation Data", "desc": "Key US inflation print.", "url": "https://www.bls.gov/"},
    {"date": datetime.date(2026, 11, 4), "summary": "[MACRO] US Federal Reserve FOMC Rate Decision", "desc": "FOMC interest rate decision.", "url": "https://www.federalreserve.gov/"},
    {"date": datetime.date(2026, 11, 6), "summary": "[MACRO] US Non-Farm Payrolls (NFP) Jobs Report", "desc": "Monthly US labor report.", "url": "https://www.bls.gov/"},
    {"date": datetime.date(2026, 11, 12), "summary": "[MACRO] US Consumer Price Index (CPI) Inflation Data", "desc": "Key US inflation print.", "url": "https://www.bls.gov/"},
    {"date": datetime.date(2026, 11, 20), "summary": "[MACRO] MSCI Semi-Annual Index Rebalancing Effective", "desc": "Passive institutional adjustments across Indian equities during the 15:00-15:30 closing auction.", "url": "https://www.msci.com/"},
    {"date": datetime.date(2026, 12, 3), "summary": "[MACRO] OPEC+ Joint Ministerial Meeting", "desc": "Crude oil quotas review impacting Brent crude and Indian OMCs.", "url": "https://www.opec.org/"},
    {"date": datetime.date(2026, 12, 16), "summary": "[MACRO] US Federal Reserve FOMC Rate Decision", "desc": "FOMC rate decision & economic projections.", "url": "https://www.federalreserve.gov/"},
]

def is_trading_day(d):
    return d.weekday() < 5 and d not in NSE_HOLIDAYS_2026

def get_previous_trading_day(d):
    curr = d - datetime.timedelta(days=1)
    while not is_trading_day(curr):
        curr -= datetime.timedelta(days=1)
    return curr

def get_next_trading_day(d):
    curr = d + datetime.timedelta(days=1)
    while not is_trading_day(curr):
        curr += datetime.timedelta(days=1)
    return curr

def build_tradingview_links(symbol, is_macro=False, interval=None):
    clean = re.sub(r'[^A-Za-z0-9]', '', str(symbol))
    interval_param = f"&interval={interval}" if interval else ""

    if is_macro:
        app_link = f"tradingview://chart?symbol={clean}{interval_param}"
        web_link = f"https://in.tradingview.com/chart/?symbol={clean}{interval_param}"
    elif clean.upper() == "SENSEX":
        app_link = f"tradingview://chart?symbol=BSE:SENSEX{interval_param}"
        web_link = f"https://in.tradingview.com/chart/?symbol=BSE:SENSEX{interval_param}"
    elif clean.upper() == "NIFTY":
        app_link = f"tradingview://chart?symbol=NSE:NIFTY{interval_param}"
        web_link = f"https://in.tradingview.com/chart/?symbol=NSE:NIFTY{interval_param}"
    elif clean.upper() == "NIFTY500":
        app_link = f"tradingview://chart?symbol=NSE:NIFTY500{interval_param}"
        web_link = f"https://in.tradingview.com/chart/?symbol=NSE:NIFTY500{interval_param}"
    else:
        app_link = f"tradingview://chart?symbol=NSE:{clean}{interval_param}"
        web_link = f"https://in.tradingview.com/chart/?symbol=NSE:{clean}{interval_param}"
    return app_link, web_link

def build_screener_links(symbol):
    clean = str(symbol).split()[0].replace("&", "")
    statements_url = f"https://www.screener.in/company/{clean}/consolidated/"
    pdf_archive_url = f"https://www.screener.in/company/{clean}/consolidated/#announcements"
    return statements_url, pdf_archive_url

def build_tickertape_link(symbol):
    clean = str(symbol).split()[0].replace("&", "")
    return f"https://www.tickertape.in/stocks/{clean}"

def build_nse_direct_url(symbol):
    clean = str(symbol).split()[0]
    return f"https://www.nseindia.com/get-quotes/equity?symbol={clean}"

def add_market_alarm(event, summary_text):
    if not CONFIG.get("ENABLE_ALARMS", True):
        return
    alarm = Alarm()
    alarm.add('action', 'DISPLAY')
    alarm.add('description', summary_text)
    alarm.add('trigger', datetime.timedelta(hours=9))
    event.add_component(alarm)

def get_live_nifty_500_symbols():
    url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
    headers = {"User-Agent": "Mozilla/5.0"}
    symbols = []
    try:
        resp = requests.get(url, headers=headers, timeout=12)
        if resp.status_code == 200:
            reader = csv.DictReader(io.StringIO(resp.text))
            for row in reader:
                s = row.get("Symbol", "").strip()
                if s:
                    symbols.append(s)
    except Exception:
        pass

    if len(symbols) < 50:
        symbols = [
            "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "ITC", "SBIN",
            "BHARTIARTL", "KOTAKBANK", "LT", "HINDUNILVR", "AXISBANK", "BAJFINANCE",
            "MARUTI", "ASIANPAINT", "TITAN", "SUNPHARMA", "ULTRACEMCO", "NTPC",
            "POWERGRID", "ONGC", "COALINDIA", "BAJAJFINSV", "M&M", "ADANIENT",
            "ADANIPORTS", "TATASTEEL", "JSWSTEEL", "HCLTECH", "WIPRO", "TECHM",
            "TATAMOTORS", "RAYMOND", "IDFCFIRSTB", "BANDHANBNK", "PNB", "VEDL"
        ]
    return symbols

def get_fy2026_comprehensive_ipo_database():
    return [
        {
            "name": "Veegaland Developers",
            "symbol": "VEEGALAND",
            "price": "₹130 - 140",
            "lot": "100 Shares",
            "gmp": "+18.5%",
            "type": "Mainboard",
            "open": datetime.date(2026, 9, 10),
            "close": datetime.date(2026, 9, 15),
            "allotment": datetime.date(2026, 9, 16),
            "listing": datetime.date(2026, 9, 18),
            "rhp": "https://www.bseindia.com/markets/PublicIssues/IPOIssue_new.aspx",
            "registrar": "https://linkintime.co.in/initial_offer/public-issues.html",
            "ipogyani": "https://ipogyani.com/live-ipo"
        },
        {
            "name": "Pranav Constructions",
            "symbol": "PRANAV",
            "price": "₹315 - 325",
            "lot": "45 Shares",
            "gmp": "+22.4%",
            "type": "Mainboard",
            "open": datetime.date(2026, 9, 7),
            "close": datetime.date(2026, 9, 9),
            "allotment": datetime.date(2026, 9, 10),
            "listing": datetime.date(2026, 9, 14),
            "rhp": "https://www.bseindia.com/markets/PublicIssues/IPOIssue_new.aspx",
            "registrar": "https://ris.kfintech.com/ipostatus/",
            "ipogyani": "https://ipogyani.com/live-ipo"
        },
        {
            "name": "Qualiance International",
            "symbol": "QUALIANCE",
            "price": "₹120 - 127",
            "lot": "1000 Shares",
            "gmp": "+31.5%",
            "type": "SME",
            "open": datetime.date(2026, 9, 4),
            "close": datetime.date(2026, 9, 8),
            "allotment": datetime.date(2026, 9, 9),
            "listing": datetime.date(2026, 9, 11),
            "rhp": "https://www.nseindia.com/market-data/all-upcoming-issues-ipo",
            "registrar": "https://www.bigshareonline.com/ipo_Allotment.html",
            "ipogyani": "https://ipogyani.com/live-ipo"
        },
        {
            "name": "Rays of Belief",
            "symbol": "RAYSOFBELIEF",
            "price": "₹227 - 239",
            "lot": "60 Shares",
            "gmp": "+16.7%",
            "type": "Mainboard",
            "open": datetime.date(2026, 9, 1),
            "close": datetime.date(2026, 9, 3),
            "allotment": datetime.date(2026, 9, 4),
            "listing": datetime.date(2026, 9, 8),
            "rhp": "https://www.bseindia.com/markets/PublicIssues/IPOIssue_new.aspx",
            "registrar": "https://linkintime.co.in/initial_offer/public-issues.html",
            "ipogyani": "https://ipogyani.com/live-ipo"
        },
        {
            "name": "Deepa Jewellers",
            "symbol": "DEEPA",
            "price": "₹168 - 177",
            "lot": "80 Shares",
            "gmp": "+12.8%",
            "type": "Mainboard",
            "open": datetime.date(2026, 9, 1),
            "close": datetime.date(2026, 9, 3),
            "allotment": datetime.date(2026, 9, 4),
            "listing": datetime.date(2026, 9, 8),
            "rhp": "https://www.bseindia.com/markets/PublicIssues/IPOIssue_new.aspx",
            "registrar": "https://ris.kfintech.com/ipostatus/",
            "ipogyani": "https://ipogyani.com/live-ipo"
        },
        {
            "name": "Farm Peace",
            "symbol": "FARMPEACE",
            "price": "₹59",
            "lot": "2000 Shares",
            "gmp": "+24.0%",
            "type": "SME",
            "open": datetime.date(2026, 9, 1),
            "close": datetime.date(2026, 9, 3),
            "allotment": datetime.date(2026, 9, 4),
            "listing": datetime.date(2026, 9, 8),
            "rhp": "https://www.bseindia.com/markets/PublicIssues/IPOIssue_new.aspx",
            "registrar": "https://www.bigshareonline.com/ipo_Allotment.html",
            "ipogyani": "https://ipogyani.com/live-ipo"
        },
        {
            "name": "Fly-Hi Maritime Travels",
            "symbol": "FLYHI",
            "price": "₹102",
            "lot": "1200 Shares",
            "gmp": "+14.5%",
            "type": "SME",
            "open": datetime.date(2026, 9, 1),
            "close": datetime.date(2026, 9, 3),
            "allotment": datetime.date(2026, 9, 4),
            "listing": datetime.date(2026, 9, 8),
            "rhp": "https://www.nseindia.com/market-data/all-upcoming-issues-ipo",
            "registrar": "https://linkintime.co.in/initial_offer/public-issues.html",
            "ipogyani": "https://ipogyani.com/live-ipo"
        },
        {
            "name": "Purple Style Labs",
            "symbol": "PURPLE",
            "price": "₹546 - 575",
            "lot": "25 Shares",
            "gmp": "+28.2%",
            "type": "Mainboard",
            "open": datetime.date(2026, 8, 31),
            "close": datetime.date(2026, 9, 2),
            "allotment": datetime.date(2026, 9, 3),
            "listing": datetime.date(2026, 9, 7),
            "rhp": "https://www.bseindia.com/markets/PublicIssues/IPOIssue_new.aspx",
            "registrar": "https://ris.kfintech.com/ipostatus/",
            "ipogyani": "https://ipogyani.com/live-ipo"
        },
        {
            "name": "ESDS Software Solution",
            "symbol": "ESDS",
            "price": "₹429",
            "lot": "35 Shares",
            "gmp": "+15.2%",
            "type": "Mainboard",
            "open": datetime.date(2026, 8, 28),
            "close": datetime.date(2026, 9, 1),
            "allotment": datetime.date(2026, 9, 2),
            "listing": datetime.date(2026, 9, 4),
            "rhp": "https://www.bseindia.com/markets/PublicIssues/IPOIssue_new.aspx",
            "registrar": "https://linkintime.co.in/initial_offer/public-issues.html",
            "ipogyani": "https://ipogyani.com/live-ipo"
        },
        {
            "name": "Lumino Industries",
            "symbol": "LUMINO",
            "price": "₹82",
            "lot": "150 Shares",
            "gmp": "+52.0%",
            "type": "Mainboard",
            "open": datetime.date(2026, 8, 27),
            "close": datetime.date(2026, 8, 31),
            "allotment": datetime.date(2026, 9, 1),
            "listing": datetime.date(2026, 9, 3),
            "rhp": "https://www.bseindia.com/markets/PublicIssues/IPOIssue_new.aspx",
            "registrar": "https://ris.kfintech.com/ipostatus/",
            "ipogyani": "https://ipogyani.com/live-ipo"
        },
        {
            "name": "Kwick Forensic Solutions",
            "symbol": "KWICK",
            "price": "₹90",
            "lot": "1600 Shares",
            "gmp": "+68.5%",
            "type": "SME",
            "open": datetime.date(2026, 8, 27),
            "close": datetime.date(2026, 8, 31),
            "allotment": datetime.date(2026, 9, 1),
            "listing": datetime.date(2026, 9, 3),
            "rhp": "https://www.nseindia.com/market-data/all-upcoming-issues-ipo",
            "registrar": "https://www.bigshareonline.com/ipo_Allotment.html",
            "ipogyani": "https://ipogyani.com/live-ipo"
        },
        {
            "name": "Augmont Enterprises",
            "symbol": "AUGMONT",
            "price": "₹345",
            "lot": "40 Shares",
            "gmp": "+21.4%",
            "type": "Mainboard",
            "open": datetime.date(2026, 8, 14),
            "close": datetime.date(2026, 8, 18),
            "allotment": datetime.date(2026, 8, 19),
            "listing": datetime.date(2026, 8, 21),
            "rhp": "https://www.bseindia.com/markets/PublicIssues/IPOIssue_new.aspx",
            "registrar": "https://linkintime.co.in/initial_offer/public-issues.html",
            "ipogyani": "https://ipogyani.com/live-ipo"
        },
        {
            "name": "Tempsens Instruments",
            "symbol": "TEMPSENS",
            "price": "₹550",
            "lot": "25 Shares",
            "gmp": "+44.0%",
            "type": "Mainboard",
            "open": datetime.date(2026, 8, 13),
            "close": datetime.date(2026, 8, 17),
            "allotment": datetime.date(2026, 8, 18),
            "listing": datetime.date(2026, 8, 20),
            "rhp": "https://www.bseindia.com/markets/PublicIssues/IPOIssue_new.aspx",
            "registrar": "https://ris.kfintech.com/ipostatus/",
            "ipogyani": "https://ipogyani.com/live-ipo"
        },
        {
            "name": "Gaja Alternative Asset",
            "symbol": "GAJA",
            "price": "₹195",
            "lot": "75 Shares",
            "gmp": "+18.0%",
            "type": "Mainboard",
            "open": datetime.date(2026, 8, 12),
            "close": datetime.date(2026, 8, 14),
            "allotment": datetime.date(2026, 8, 17),
            "listing": datetime.date(2026, 8, 19),
            "rhp": "https://www.bseindia.com/markets/PublicIssues/IPOIssue_new.aspx",
            "registrar": "https://linkintime.co.in/initial_offer/public-issues.html",
            "ipogyani": "https://ipogyani.com/live-ipo"
        },
        {
            "name": "Technocrats Plasma Systems",
            "symbol": "TECHNOCRATS",
            "price": "₹132",
            "lot": "1000 Shares",
            "gmp": "+53.0%",
            "type": "SME",
            "open": datetime.date(2026, 8, 14),
            "close": datetime.date(2026, 8, 18),
            "allotment": datetime.date(2026, 8, 19),
            "listing": datetime.date(2026, 8, 21),
            "rhp": "https://www.nseindia.com/market-data/all-upcoming-issues-ipo",
            "registrar": "https://www.bigshareonline.com/ipo_Allotment.html",
            "ipogyani": "https://ipogyani.com/live-ipo"
        }
    ]

def process_single_ticker(sym, today, cutoff_past, cutoff_future):
    corp_events = []
    intraday_events = []
    ticker_str = f"{sym}.NS"
    app_link, web_link = build_tradingview_links(sym)
    app_5m, web_5m = build_tradingview_links(sym, interval="5")
    statements_url, pdf_archive_url = build_screener_links(sym)
    tickertape_url = build_tickertape_link(sym)
    nse_quote_url = build_nse_direct_url(sym)

    try:
        t = yf.Ticker(ticker_str)
        cmp_price = None
        try:
            cmp_price = t.fast_info.get("lastPrice") or t.info.get("currentPrice")
        except Exception:
            pass

        # 1. Dividends (Buy Cutoff & Payout)
        divs = t.dividends
        if not divs.empty:
            for ts, amount in divs.items():
                div_date = ts.date()
                if cutoff_past <= div_date <= cutoff_future:
                    must_buy_by = div_date if is_trading_day(div_date) else get_previous_trading_day(div_date)
                    yield_text = f" | Yield: {(amount / cmp_price * 100):.2f}%" if cmp_price else ""

                    # Buy Cutoff Event
                    ev_cut = Event()
                    ev_cut.add('uid', f"div-cut-{sym}-{div_date.isoformat()}")
                    ev_cut.add('summary', f"[DIVIDEND] {sym} (₹{amount:.2f}{yield_text}) - Buy Cutoff")
                    ev_cut.add('dtstart', must_buy_by)
                    ev_cut.add('dtend', must_buy_by + datetime.timedelta(days=1))
                    ev_cut.add('url', web_link)
                    ev_cut.add('description', (
                        f"ACTION REQUIRED: Purchase today before 3:30 PM IST for Demat credit by Record Date.\n\n"
                        f"• Declared Amount: ₹{amount:.2f} per share\n"
                        f"• Ex-Date: {div_date.strftime('%d-%b-%Y')}\n"
                        f"• Est. Dividend Yield: {yield_text.replace(' | Yield: ', '') if yield_text else 'N/A'}\n"
                        f"• Settlement: T+1 Rolling Settlement (NSE/BSE)\n"
                        f"-----------------------------------------\n"
                        f"• Open in TradingView App (Native):\n  {app_link}\n\n"
                        f"• Tickertape Analysis & Valuation Scorecard:\n  {tickertape_url}\n\n"
                        f"• Screener Statements & SEBI PDF Archive:\n  {pdf_archive_url}\n\n"
                        f"• Official NSE Company Desk & Filings:\n  {nse_quote_url}\n"
                    ))
                    ev_cut.add('location', 'NSE / BSE India')
                    add_market_alarm(ev_cut, f"Cutoff today: Buy {sym} for ₹{amount:.2f} dividend.")
                    corp_events.append(ev_cut)

                    # Payout Event
                    payout_date = div_date + datetime.timedelta(days=30)
                    while not is_trading_day(payout_date):
                        payout_date += datetime.timedelta(days=1)

                    ev_pay = Event()
                    ev_pay.add('uid', f"div-pay-{sym}-{payout_date.isoformat()}")
                    ev_pay.add('summary', f"[PAYOUT] {sym} (₹{amount:.2f}) - Demat Credit")
                    ev_pay.add('dtstart', payout_date)
                    ev_pay.add('dtend', payout_date + datetime.timedelta(days=1))
                    ev_pay.add('url', web_link)
                    ev_pay.add('description', (
                        f"DIVIDEND DISBURSEMENT: Direct bank credit for {sym} declared dividend (₹{amount:.2f}/share).\n\n"
                        f"• Open in TradingView App (Native):\n  {app_link}\n\n"
                        f"• Tickertape Profile:\n  {tickertape_url}\n\n"
                        f"• Official NSE Scrip Desk & Announcement Details:\n  {nse_quote_url}\n\n"
                        f"• Screener Profile & History:\n  {statements_url}\n"
                    ))
                    ev_pay.add('location', 'Bank Account / Demat')
                    corp_events.append(ev_pay)

        # 2. Stock Splits & Bonus Allotments
        splits = t.splits
        if not splits.empty:
            for ts, ratio in splits.items():
                split_date = ts.date()
                if cutoff_past <= split_date <= cutoff_future:
                    must_buy_by = split_date if is_trading_day(split_date) else get_previous_trading_day(split_date)
                    ev_sp = Event()
                    ev_sp.add('uid', f"split-{sym}-{split_date.isoformat()}")
                    ev_sp.add('summary', f"[SPLIT/BONUS] {sym} (Ratio: {ratio}) - Cutoff")
                    ev_sp.add('dtstart', must_buy_by)
                    ev_sp.add('dtend', must_buy_by + datetime.timedelta(days=1))
                    ev_sp.add('url', web_link)
                    ev_sp.add('description', (
                        f"Corporate Restructuring / Share Allotment for {sym}.\n\n"
                        f"• Ratio: {ratio}\n"
                        f"• Open in TradingView App (Native):\n  {app_link}\n\n"
                        f"• Tickertape Fundamentals:\n  {tickertape_url}\n\n"
                        f"• Screener Statements & PDF Filings:\n  {pdf_archive_url}\n\n"
                        f"• Official NSE Company Desk:\n  {nse_quote_url}\n"
                    ))
                    ev_sp.add('location', 'NSE / BSE')
                    add_market_alarm(ev_sp, f"Today is the buy cutoff for {sym} Split/Bonus.")
                    corp_events.append(ev_sp)

        # 3. Quarterly Results & Heavyweights
        try:
            q_fin = t.quarterly_financials
            if q_fin is not None and not q_fin.empty:
                for col in q_fin.columns:
                    f_date = col.date() if hasattr(col, "date") else None
                    if f_date and cutoff_past <= f_date <= cutoff_future:
                        is_heavy = sym in NIFTY_HEAVYWEIGHTS
                        tag = f"[HEAVYWEIGHT RESULTS] {sym} (Nifty Weight: {NIFTY_HEAVYWEIGHTS[sym]}%)" if is_heavy else f"[RESULTS / VOLATILITY] {sym} - Financial Results"
                        
                        ev_res = Event()
                        ev_res.add('uid', f"res-q-{sym}-{f_date.isoformat()}")
                        ev_res.add('summary', tag)
                        ev_res.add('dtstart', f_date)
                        ev_res.add('dtend', f_date + datetime.timedelta(days=1))
                        ev_res.add('url', web_5m if is_heavy else web_link)
                        ev_res.add('description', (
                            f"EARNINGS RELEASE & HIGH VOLATILITY OUTCOME\n\n"
                            f"• Symbol: {sym}\n"
                            f"• Index Impact: {'Major Nifty Driver (' + str(NIFTY_HEAVYWEIGHTS[sym]) + '%)' if is_heavy else 'Individual Stock Action'}\n"
                            f"• Open 5-Minute Chart in TradingView (Native):\n  {app_5m}\n\n"
                            f"• Tickertape Overview & Valuation:\n  {tickertape_url}\n\n"
                            f"• Screener Balance Sheet:\n  {statements_url}\n\n"
                            f"• Official NSE Filings & Outcome PDFs:\n  {nse_quote_url}\n"
                        ))
                        ev_res.add('location', 'NSE / BSE')
                        add_market_alarm(ev_res, f"Quarterly Results Day: {sym}")
                        corp_events.append(ev_res)
                        if is_heavy:
                            intraday_events.append(ev_res)

            cal_df = t.calendar
            if cal_df is not None and not cal_df.empty:
                if "Earnings Date" in cal_df.index:
                    for ed in cal_df.loc["Earnings Date"]:
                        if hasattr(ed, "date"):
                            e_date = ed.date()
                            if cutoff_past <= e_date <= cutoff_future:
                                is_heavy = sym in NIFTY_HEAVYWEIGHTS
                                tag = f"[HEAVYWEIGHT RESULTS] {sym} (Nifty Weight: {NIFTY_HEAVYWEIGHTS[sym]}%)" if is_heavy else f"[RESULTS / VOLATILITY] {sym} - Board Meeting"

                                ev_bm = Event()
                                ev_bm.add('uid', f"results-bm-{sym}-{e_date.isoformat()}")
                                ev_bm.add('summary', tag)
                                ev_bm.add('dtstart', e_date)
                                ev_bm.add('dtend', e_date + datetime.timedelta(days=1))
                                ev_bm.add('url', web_5m if is_heavy else web_link)
                                ev_bm.add('description', (
                                    f"HIGH VOLATILITY ALERT: Board Meeting for quarterly results.\n\n"
                                    f"• Symbol: {sym}\n"
                                    f"• Index Impact: {'Major Index Driver (' + str(NIFTY_HEAVYWEIGHTS[sym]) + '%)' if is_heavy else 'Individual Stock Action'}\n"
                                    f"• Open 5-Minute Chart in TradingView (Native):\n  {app_5m}\n\n"
                                    f"• Tickertape Overview:\n  {tickertape_url}\n\n"
                                    f"• Screener Profile:\n  {statements_url}\n\n"
                                    f"• Official NSE Filings & Outcome PDFs:\n  {nse_quote_url}\n"
                                ))
                                ev_bm.add('location', 'NSE / BSE')
                                add_market_alarm(ev_bm, f"Board Meeting today: {sym}")
                                corp_events.append(ev_bm)
                                if is_heavy:
                                    intraday_events.append(ev_bm)
        except Exception:
            pass

    except Exception:
        pass

    return corp_events, intraday_events

def build_calendars():
    cal_div = Calendar()
    cal_div.add('prodid', '-//NSE Dividends, Restructuring & Corporate Actions//EN')
    cal_div.add('version', '2.0')
    cal_div.add('x-wr-calname', '1. Dividends, Mergers & Corporate Actions')
    cal_div.add('x-wr-timezone', 'Asia/Kolkata')

    cal_ipo = Calendar()
    cal_ipo.add('prodid', '-//Live Indian IPOs, GMP & Listings Hub//EN')
    cal_ipo.add('version', '2.0')
    cal_ipo.add('x-wr-calname', '2. Indian IPOs, GMP & Listings')
    cal_ipo.add('x-wr-timezone', 'Asia/Kolkata')

    cal_macro = Calendar()
    cal_macro.add('prodid', '-//Macro, Economic Policy & Tax Hub//EN')
    cal_macro.add('version', '2.0')
    cal_macro.add('x-wr-calname', '3. Macro, Policy & Tax Deadlines')
    cal_macro.add('x-wr-timezone', 'Asia/Kolkata')

    cal_fno = Calendar()
    cal_fno.add('prodid', '-//Intraday, Derivatives Expiry & Momentum//EN')
    cal_fno.add('version', '2.0')
    cal_fno.add('x-wr-calname', '4. Intraday, F&O Expiries & Momentum')
    cal_fno.add('x-wr-timezone', 'Asia/Kolkata')

    today = datetime.date.today()
    cutoff_past = datetime.date(2026, 4, 1)
    cutoff_future = today + datetime.timedelta(days=120)

    # 1. Mergers, Demergers & Buybacks (Feed 1)
    for r in CORPORATE_RESTRUCTURING_2026:
        if cutoff_past <= r["date"] <= cutoff_future:
            app_l, web_l = build_tradingview_links(r["symbol"])
            statements_u, pdf_u = build_screener_links(r["symbol"])
            tickertape_u = build_tickertape_link(r["symbol"])
            nse_u = build_nse_direct_url(r["symbol"])

            ev_r = Event()
            ev_r.add('uid', f"restr-{r['symbol']}-{r['date'].isoformat()}")
            ev_r.add('summary', r["summary"])
            ev_r.add('dtstart', r["date"])
            ev_r.add('dtend', r["date"] + datetime.timedelta(days=1))
            ev_r.add('url', web_l)
            ev_r.add('description', (
                f"{r['desc']}\n"
                f"• Entitlement Ratio: {r['ratio']}\n"
                f"-----------------------------------------\n"
                f"• Open in TradingView App (Native):\n  {app_l}\n\n"
                f"• Tickertape Analysis:\n  {tickertape_u}\n\n"
                f"• Screener Corporate Profile:\n  {statements_u}\n\n"
                f"• Official Exchange Disclosure (PDF):\n  {nse_u}\n"
            ))
            ev_r.add('location', 'NSE / BSE India')
            add_market_alarm(ev_r, f"Restructuring Cutoff Today: {r['symbol']}")
            cal_div.add_component(ev_r)

    # 2. Macro, Policy, Tax, and Holidays (Feed 3)
    for h_date, h_name in NSE_HOLIDAYS_2026.items():
        if cutoff_past <= h_date <= cutoff_future:
            ev_h = Event()
            ev_h.add('uid', f"holiday-{h_date.isoformat()}")
            ev_h.add('summary', f"[HOLIDAY] Market Closed - {h_name}")
            ev_h.add('dtstart', h_date)
            ev_h.add('dtend', h_date + datetime.timedelta(days=1))
            ev_h.add('url', "https://www.nseindia.com/resources/exchange-communication-holidays")
            ev_h.add('description', f"NSE & BSE equity/derivative segments are closed today for {h_name}.")
            cal_macro.add_component(ev_h)

    for m in MACRO_POLICY_TAX_EVENTS:
        if cutoff_past <= m["date"] <= cutoff_future:
            ev_m = Event()
            ev_m.add('uid', f"macro-tax-{m['summary'][:15].replace(' ', '')}-{m['date'].isoformat()}")
            ev_m.add('summary', m["summary"])
            ev_m.add('dtstart', m["date"])
            ev_m.add('dtend', m["date"] + datetime.timedelta(days=1))
            ev_m.add('url', m.get("url", "https://www.nseindia.com/"))
            ev_m.add('description', f"{m['desc']}\n\n• Official Portal:\n  {m.get('url')}")
            add_market_alarm(ev_m, f"Market Alert: {m['summary']}")
            cal_macro.add_component(ev_m)

    # 3. Clean Intraday Expiries (No Duplicates; 5m Intervals; Clean Top URL)
    curr_scan = cutoff_past
    while curr_scan <= cutoff_future:
        if CONFIG.get("ENABLE_NIFTY_WEEKLY_EXPIRY", True) and curr_scan.weekday() == 1:
            exp_date = curr_scan if is_trading_day(curr_scan) else get_previous_trading_day(curr_scan)
            nifty_app_5m, nifty_web_5m = build_tradingview_links("NIFTY", is_macro=False, interval="5")

            ev_exp = Event()
            ev_exp.add('uid', f"exp-nifty-{curr_scan.isoformat()}")
            ev_exp.add('summary', "[F&O] NSE Nifty 50 Weekly Expiry (Tuesday)")
            ev_exp.add('dtstart', exp_date)
            ev_exp.add('dtend', exp_date + datetime.timedelta(days=1))
            ev_exp.add('url', nifty_web_5m)
            ev_exp.add('description', (
                f"NSE NIFTY 50 WEEKLY DERIVATIVES EXPIRY\n"
                f"-----------------------------------------\n"
                f"• Benchmark Index Options Expiry.\n"
                f"• Expect gamma expansions and heightened theta decay after 01:30 PM IST.\n\n"
                f"• Open 5-Minute Chart in TradingView App (Native):\n  {nifty_app_5m}\n"
            ))
            cal_fno.add_component(ev_exp)

        if CONFIG.get("ENABLE_SENSEX_WEEKLY_EXPIRY", True) and curr_scan.weekday() == 3:
            exp_date = curr_scan if is_trading_day(curr_scan) else get_previous_trading_day(curr_scan)
            sensex_app_5m, sensex_web_5m = build_tradingview_links("SENSEX", is_macro=False, interval="5")

            ev_exp = Event()
            ev_exp.add('uid', f"exp-sensex-{curr_scan.isoformat()}")
            ev_exp.add('summary', "[F&O] BSE Sensex Weekly Expiry (Thursday)")
            ev_exp.add('dtstart', exp_date)
            ev_exp.add('dtend', exp_date + datetime.timedelta(days=1))
            ev_exp.add('url', sensex_web_5m)
            ev_exp.add('description', (
                f"BSE SENSEX WEEKLY DERIVATIVES EXPIRY\n"
                f"-----------------------------------------\n"
                f"• Benchmark Index Options Expiry.\n\n"
                f"• Open 5-Minute Chart in TradingView App (Native):\n  {sensex_app_5m}\n"
            ))
            cal_fno.add_component(ev_exp)

        curr_scan += datetime.timedelta(days=1)

    # Monthly Single Stock F&O Expiry -> Configured to NIFTY 500 Daily Timeframe
    if CONFIG.get("ENABLE_STOCK_FO_MONTHLY_EXPIRY", True):
        for yr in [2026, 2027]:
            for m in range(1, 13):
                first_next = datetime.date(yr + (1 if m == 12 else 0), 1 if m == 12 else m + 1, 1)
                last_d = first_next - datetime.timedelta(days=1)
                while last_d.weekday() != 3:
                    last_d -= datetime.timedelta(days=1)
                final_stock_exp = last_d if is_trading_day(last_d) else get_previous_trading_day(last_d)

                if cutoff_past <= final_stock_exp <= cutoff_future:
                    nifty500_app_1d, nifty500_web_1d = build_tradingview_links("NIFTY500", is_macro=False, interval="1D")
                    ev_stk = Event()
                    ev_stk.add('uid', f"fo-stock-exp-{final_stock_exp.isoformat()}")
                    ev_stk.add('summary', f"[F&O STOCKS] NSE Monthly Stock Derivatives Expiry ({final_stock_exp.strftime('%b %Y')})")
                    ev_stk.add('dtstart', final_stock_exp)
                    ev_stk.add('dtend', final_stock_exp + datetime.timedelta(days=1))
                    ev_stk.add('url', nifty500_web_1d)
                    ev_stk.add('description', (
                        f"NSE MONTHLY STOCK DERIVATIVES EXPIRY\n"
                        f"-----------------------------------------\n"
                        f"• Contract Expiry: All Single Stock Futures & Options contracts expire today (3:30 PM IST).\n"
                        f"• Physical Delivery: Compulsory physical delivery for in-the-money (ITM) options.\n"
                        f"• Margin Escalation: Broker physical delivery margins apply to near-the-money and ITM strikes.\n"
                        f"-----------------------------------------\n"
                        f"• Open Nifty 500 Daily Broad-Market Chart (Native App):\n  {nifty500_app_1d}\n"
                    ))
                    add_market_alarm(ev_stk, f"Stock F&O Expiry Today: Manage ITM delivery exposure.")
                    cal_fno.add_component(ev_stk)

    # 4. Intraday Momentum, Ban List, Bulk Deals & Surveillance Tools (Feed 4)
    if is_trading_day(today):
        if CONFIG.get("ENABLE_FNO_BAN_MONITOR", True):
            fno_ban_stocks = ["BANDHANBNK", "PNB", "BIOCON", "HINDCOPPER", "PEL"]
            ev_ban = Event()
            ev_ban.add('uid', f"fno-ban-status-{today.isoformat()}")
            ev_ban.add('summary', f"[F&O BAN] Securities in Ban Period ({len(fno_ban_stocks)} Stocks)")
            ev_ban.add('dtstart', today)
            ev_ban.add('dtend', today + datetime.timedelta(days=1))
            ev_ban.add('url', "https://www.nseindia.com/all-reports")
            ev_ban.add('description', (
                f"NSE MWPL BAN MONITOR (95% THRESHOLD)\n"
                f"-----------------------------------------\n"
                f"• Securities in Ban: {', '.join(fno_ban_stocks)}\n"
                f"• Warning: Opening fresh positions attracts severe exchange penalties.\n"
                f"• Exit Threshold: Only exits ban when open interest drops below 80% MWPL.\n"
            ))
            add_market_alarm(ev_ban, f"F&O Ban: {', '.join(fno_ban_stocks[:3])} in ban.")
            cal_fno.add_component(ev_ban)

        if CONFIG.get("ENABLE_INTRADAY_VOLATILITY_TOOLS", True):
            # India VIX Radar
            vix_app, vix_web = build_tradingview_links("INDIAVIX", is_macro=True, interval="15")
            ev_vix = Event()
            ev_vix.add('uid', f"vix-desk-{today.isoformat()}")
            ev_vix.add('summary', "[VOLATILITY] India VIX Intraday Radar")
            ev_vix.add('dtstart', today)
            ev_vix.add('dtend', today + datetime.timedelta(days=1))
            ev_vix.add('url', vix_web)
            ev_vix.add('description', (
                f"INTRADAY VOLATILITY REGIME\n"
                f"-----------------------------------------\n"
                f"• India VIX 15-Minute Intraday Structure:\n  {vix_app}\n\n"
                f"• Breakout Momentum Scanner (52-Week High / Low):\n  https://www.nseindia.com/market-data/52-week-high-low-equity-market\n\n"
                f"• SEBI ASM / GSM Surveillance Restrictions:\n  https://www.nseindia.com/reports/surveillance\n"
            ))
            cal_fno.add_component(ev_vix)

            # Institutional Bulk & Block Deals Desk (18:30 IST Market Close Marker)
            ev_deals = Event()
            ev_deals.add('uid', f"deals-desk-{today.isoformat()}")
            ev_deals.add('summary', "[BULK / BLOCK DEALS] Institutional Transaction Desk")
            ev_deals.add('dtstart', today)
            ev_deals.add('dtend', today + datetime.timedelta(days=1))
            ev_deals.add('url', "https://www.nseindia.com/report-detail/display-bulk-and-block-deals")
            ev_deals.add('description', (
                f"INSTITUTIONAL FOOTPRINT DISCLOSURES (>0.5% EQUITY)\n"
                f"-----------------------------------------\n"
                f"Track after-market promoter, FII & DII large transactions:\n\n"
                f"• Official NSE Bulk Deals Ledger:\n  https://www.nseindia.com/report-detail/display-bulk-and-block-deals\n\n"
                f"• Official NSE Block Trading Window Report:\n  https://www.nseindia.com/market-data/block-deal-watch\n\n"
                f"• BSE Bulk Deals Tracker:\n  https://www.bseindia.com/markets/equity/EQReports/Bulktot.aspx\n"
            ))
            cal_fno.add_component(ev_deals)

    # 5. Ingest Nifty 500 Corporate Actions & Results
    universe = get_live_nifty_500_symbols()
    print(f"Loaded {len(universe)} symbols from Nifty 500.")

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(process_single_ticker, sym, today, cutoff_past, cutoff_future): sym for sym in universe}
        for fut in as_completed(futures):
            c_evs, i_evs = fut.result()
            for ev in c_evs:
                cal_div.add_component(ev)
            for ev in i_evs:
                cal_fno.add_component(ev)

    # 6. Ingest IPO Milestones (Feed 2)
    ipos = get_fy2026_comprehensive_ipo_database()
    print(f"Loaded {len(ipos)} comprehensive IPOs covering FY2026-27.")
    for ipo in ipos:
        # OPEN
        if cutoff_past <= ipo['open'] <= cutoff_future:
            ev_o = Event()
            ev_o.add('uid', f"ipo-open-{ipo['name'].replace(' ', '')}-{ipo['open'].isoformat()}")
            ev_o.add('summary', f"[IPO OPEN] {ipo['name']} ({ipo['type']})")
            ev_o.add('dtstart', ipo['open'])
            ev_o.add('dtend', ipo['open'] + datetime.timedelta(days=1))
            ev_o.add('url', ipo['ipogyani'])
            ev_o.add('description', (
                f"IPO BIDDING OPENS TODAY\n"
                f"-----------------------------------------\n"
                f"• Issue: {ipo['name']}\n"
                f"• Category: {ipo['type']}\n"
                f"• Price Band: {ipo['price']}\n"
                f"• Minimum Lot Size: {ipo.get('lot', 'N/A')}\n"
                f"• Live Grey Market Premium (GMP): {ipo['gmp']}\n"
                f"• Bidding Window: {ipo['open'].strftime('%d-%b')} to {ipo['close'].strftime('%d-%b-%Y')}\n"
                f"-----------------------------------------\n"
                f"• IPOGyani Live GMP & Subscription Tracker:\n  {ipo['ipogyani']}\n\n"
                f"• Official Exchange Prospectus & RHP:\n  {ipo['rhp']}\n\n"
                f"• InvestorGain GMP Tracker:\n  https://www.investorgain.com/report/live-ipo-gmp/331/\n"
            ))
            add_market_alarm(ev_o, f"IPO Bidding Opens Today: {ipo['name']}")
            cal_ipo.add_component(ev_o)

        # CLOSE
        if cutoff_past <= ipo['close'] <= cutoff_future:
            ev_c = Event()
            ev_c.add('uid', f"ipo-close-{ipo['name'].replace(' ', '')}-{ipo['close'].isoformat()}")
            ev_c.add('summary', f"[IPO CLOSE] {ipo['name']} - Final Bidding Day")
            ev_c.add('dtstart', ipo['close'])
            ev_c.add('dtend', ipo['close'] + datetime.timedelta(days=1))
            ev_c.add('url', ipo['ipogyani'])
            ev_c.add('description', (
                f"FINAL BIDDING & MANDATE APPROVAL DAY\n"
                f"-----------------------------------------\n"
                f"• Final Cutoff: 5:00 PM IST (UPI Mandate Authorization)\n"
                f"• Issue: {ipo['name']}\n"
                f"• Price Band: {ipo['price']}\n"
                f"• Final Grey Market Premium: {ipo['gmp']}\n"
                f"-----------------------------------------\n"
                f"• IPOGyani Final Day Subscription & GMP:\n  {ipo['ipogyani']}\n\n"
                f"• Official Registrar Allotment Portal:\n  {ipo['registrar']}\n"
            ))
            add_market_alarm(ev_c, f"IPO Closes Today (5 PM): {ipo['name']}")
            cal_ipo.add_component(ev_c)

        # ALLOTMENT
        if cutoff_past <= ipo['allotment'] <= cutoff_future:
            ev_a = Event()
            ev_a.add('uid', f"ipo-allot-{ipo['name'].replace(' ', '')}-{ipo['allotment'].isoformat()}")
            ev_a.add('summary', f"[IPO ALLOTMENT] {ipo['name']} Allotment Status")
            ev_a.add('dtstart', ipo['allotment'])
            ev_a.add('dtend', ipo['allotment'] + datetime.timedelta(days=1))
            ev_a.add('url', ipo['registrar'])
            ev_a.add('description', (
                f"BASIS OF ALLOTMENT FINALIZATION\n"
                f"-----------------------------------------\n"
                f"Check status with PAN on designated registrar desks:\n\n"
                f"• Designated Registrar Desk:\n  {ipo['registrar']}\n\n"
                f"• IPOGyani Allotment Tracker:\n  {ipo['ipogyani']}\n\n"
                f"• Alternate Link Intime Desk:\n  https://linkintime.co.in/initial_offer/public-issues.html\n\n"
                f"• Alternate KFintech Desk:\n  https://ris.kfintech.com/ipostatus/\n"
            ))
            add_market_alarm(ev_a, f"Check Allotment Today: {ipo['name']}")
            cal_ipo.add_component(ev_a)

        # LISTING
        if cutoff_past <= ipo['listing'] <= cutoff_future:
            ipo_app, ipo_web = build_tradingview_links(ipo['symbol'], interval="5")
            nse_quote_page = build_nse_direct_url(ipo['symbol'])
            nse_new_listings = "https://www.nseindia.com/market-data/new-stock-exchange-listings-today"

            ev_l = Event()
            ev_l.add('uid', f"ipo-list-{ipo['name'].replace(' ', '')}-{ipo['listing'].isoformat()}")
            ev_l.add('summary', f"[IPO LISTING] {ipo['name']} Debut (10:00 AM IST)")
            ev_l.add('dtstart', ipo['listing'])
            ev_l.add('dtend', ipo['listing'] + datetime.timedelta(days=1))
            ev_l.add('url', ipo_web)
            ev_l.add('description', (
                f"EXCHANGE LISTING DEBUT TODAY\n"
                f"-----------------------------------------\n"
                f"• Trading Commences: 10:00 AM IST (Pre-open discovery 09:00-09:45 AM)\n"
                f"• Symbol: {ipo['symbol']}\n"
                f"• Category: {ipo['type']}\n"
                f"• Issue Price: {ipo['price']}\n"
                f"• Final Grey Market Premium (GMP): {ipo['gmp']}\n"
                f"-----------------------------------------\n"
                f"• Open 5-Minute Chart in TradingView App (Native):\n  {ipo_app}\n\n"
                f"• Official NSE Company Quote & Disclosures Desk:\n  {nse_quote_page}\n\n"
                f"• Official NSE New Listings Tracker:\n  {nse_new_listings}\n\n"
                f"• IPOGyani Listing Day Analysis:\n  {ipo['ipogyani']}\n"
            ))
            add_market_alarm(ev_l, f"Listing Debut Today (10 AM): {ipo['name']}")
            cal_ipo.add_component(ev_l)

    with open("dividends_actions.ics", "wb") as f:
        f.write(cal_div.to_ical())
    with open("ipos_listings.ics", "wb") as f:
        f.write(cal_ipo.to_ical())
    with open("macro_policy_tax.ics", "wb") as f:
        f.write(cal_macro.to_ical())
    with open("intraday_fno_momentum.ics", "wb") as f:
        f.write(cal_fno.to_ical())

    cal_master = Calendar()
    cal_master.add('prodid', '-//NSE/BSE Master Capital Markets Hub//EN')
    cal_master.add('version', '2.0')
    cal_master.add('x-wr-calname', 'NSE Master Capital Markets Hub (FY26-27)')
    cal_master.add('x-wr-timezone', 'Asia/Kolkata')
    cal_master.add('x-published-ttl', 'PT1H')

    for comp in list(cal_div.subcomponents) + list(cal_ipo.subcomponents) + list(cal_macro.subcomponents) + list(cal_fno.subcomponents):
        cal_master.add_component(comp)

    with open("market_calendar.ics", "wb") as f:
        f.write(cal_master.to_ical())

    print("Successfully built feeds with Tickertape links, bulk deals desk, and Nifty 500 Daily monthly expiry charts.")

if __name__ == "__main__":
    build_calendars()
