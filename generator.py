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
}

NSE_HOLIDAYS_2026 = {
    datetime.date(2026, 1, 26): "Republic Day",
    datetime.date(2026, 3, 6): "Holi",
    datetime.date(2026, 4, 3): "Good Friday",
    datetime.date(2026, 4, 14): "Dr. Ambedkar Jayanti",
    datetime.date(2026, 5, 1): "Maharashtra Day",
    datetime.date(2026, 8, 15): "Independence Day",
    datetime.date(2026, 10, 2): "Mahatma Gandhi Jayanti",
    datetime.date(2026, 10, 20): "Dussehra",
    datetime.date(2026, 11, 10): "Diwali Laxmi Pujan",
    datetime.date(2026, 12, 25): "Christmas",
}

# Macro, Economic, Statutory Tax & Regulatory Events
MACRO_POLICY_TAX_EVENTS = [
    # 1. Advance Tax Statutory Deadlines (Income Tax Dept)
    {
        "date": datetime.date(2026, 6, 15),
        "summary": "[TAX] Advance Tax Q1 Instalment Due (15%)",
        "desc": "Statutory deadline to deposit 15% of estimated income tax liability for FY26-27 under Section 208/211.",
        "url": "https://eportal.incometax.gov.in/"
    },
    {
        "date": datetime.date(2026, 9, 15),
        "summary": "[TAX] Advance Tax Q2 Instalment Due (45% Cumulative)",
        "desc": "Statutory deadline to deposit cumulative 45% of estimated advance tax. Massive corporate liquidity withdrawal day.",
        "url": "https://eportal.incometax.gov.in/"
    },
    {
        "date": datetime.date(2026, 12, 15),
        "summary": "[TAX] Advance Tax Q3 Instalment Due (75% Cumulative)",
        "desc": "Statutory deadline to deposit cumulative 75% of advance tax. Avoid Section 234C interest penalties.",
        "url": "https://eportal.incometax.gov.in/"
    },
    {
        "date": datetime.date(2027, 3, 15),
        "summary": "[TAX] Advance Tax Q4 Final Instalment (100%)",
        "desc": "Final 100% advance tax payment deadline for FY2026-27 before financial year closing.",
        "url": "https://eportal.incometax.gov.in/"
    },

    # 2. SEBI / Exchange Frameworks & Budget
    {
        "date": datetime.date(2026, 4, 1),
        "summary": "[SEBI / TAX] Revised F&O STT & Contract Sizing Rules Active",
        "desc": "Securities Transaction Tax (STT) hike effective: 0.02% to 0.05% on Futures, and 0.10% to 0.15% on Option Premiums.",
        "url": "https://www.sebi.gov.in/"
    },
    {
        "date": datetime.date(2027, 2, 1),
        "summary": "[POLICY] Union Budget 2027-28 Presentation",
        "desc": "Finance Minister presents Union Budget in Parliament (11:00 AM IST). Extreme volatility expected across all equity indices.",
        "url": "https://www.indiabudget.gov.in/"
    },

    # 3. Domestic Macro (RBI MPC, CPI Inflation & GDP)
    {
        "date": datetime.date(2026, 8, 7),
        "summary": "[MACRO] RBI Monetary Policy Committee (MPC) Outcome",
        "desc": "RBI repo rate decision & policy statement.",
        "url": "https://rbi.org.in/"
    },
    {
        "date": datetime.date(2026, 8, 31),
        "summary": "[MACRO] India GDP Data Release (Q1 FY27)",
        "desc": "MOSPI quarterly economic output print.",
        "url": "https://www.mospi.gov.in/"
    },
    {
        "date": datetime.date(2026, 9, 14),
        "summary": "[MACRO] India CPI Inflation Print",
        "desc": "Retail inflation numbers directly impacting RBI interest rate outlook.",
        "url": "https://www.mospi.gov.in/"
    },
    {
        "date": datetime.date(2026, 10, 8),
        "summary": "[MACRO] RBI Monetary Policy Committee (MPC) Outcome",
        "desc": "RBI repo rate decision & policy statement. Crucial for banking and rate-sensitive sectors.",
        "url": "https://rbi.org.in/"
    },
    {
        "date": datetime.date(2026, 10, 12),
        "summary": "[MACRO] India CPI Inflation Print",
        "desc": "Domestic retail inflation print.",
        "url": "https://www.mospi.gov.in/"
    },
    {
        "date": datetime.date(2026, 11, 12),
        "summary": "[MACRO] India CPI Inflation Print",
        "desc": "Domestic retail inflation print.",
        "url": "https://www.mospi.gov.in/"
    },
    {
        "date": datetime.date(2026, 11, 30),
        "summary": "[MACRO] India GDP Data Release (Q2 FY27)",
        "desc": "MOSPI quarterly economic output print.",
        "url": "https://www.mospi.gov.in/"
    },
    {
        "date": datetime.date(2026, 12, 10),
        "summary": "[MACRO] RBI Monetary Policy Committee (MPC) Outcome",
        "desc": "RBI repo rate decision & policy statement.",
        "url": "https://rbi.org.in/"
    },

    # 4. Global Macro Drivers (Fed, US CPI, NFP, OPEC+)
    {
        "date": datetime.date(2026, 9, 4),
        "summary": "[MACRO] US Non-Farm Payrolls (NFP) Jobs Report",
        "desc": "Monthly US labor snapshot influencing Dollar Index (DXY) and FII emerging market allocations.",
        "url": "https://www.bls.gov/"
    },
    {
        "date": datetime.date(2026, 9, 11),
        "summary": "[MACRO] US Consumer Price Index (CPI) Inflation Data",
        "desc": "Key US inflation print dictating global interest rate expectations.",
        "url": "https://www.bls.gov/"
    },
    {
        "date": datetime.date(2026, 9, 16),
        "summary": "[MACRO] US Federal Reserve FOMC Rate Decision",
        "desc": "Fed interest rate announcement & press conference.",
        "url": "https://www.federalreserve.gov/"
    },
    {
        "date": datetime.date(2026, 10, 2),
        "summary": "[MACRO] US Non-Farm Payrolls (NFP) Jobs Report",
        "desc": "Monthly US labor report.",
        "url": "https://www.bls.gov/"
    },
    {
        "date": datetime.date(2026, 10, 13),
        "summary": "[MACRO] US Consumer Price Index (CPI) Inflation Data",
        "desc": "Key US inflation print.",
        "url": "https://www.bls.gov/"
    },
    {
        "date": datetime.date(2026, 11, 4),
        "summary": "[MACRO] US Federal Reserve FOMC Rate Decision",
        "desc": "FOMC interest rate decision.",
        "url": "https://www.federalreserve.gov/"
    },
    {
        "date": datetime.date(2026, 11, 6),
        "summary": "[MACRO] US Non-Farm Payrolls (NFP) Jobs Report",
        "desc": "Monthly US labor report.",
        "url": "https://www.bls.gov/"
    },
    {
        "date": datetime.date(2026, 11, 12),
        "summary": "[MACRO] US Consumer Price Index (CPI) Inflation Data",
        "desc": "Key US inflation print.",
        "url": "https://www.bls.gov/"
    },
    {
        "date": datetime.date(2026, 11, 20),
        "summary": "[MACRO] MSCI Semi-Annual Index Rebalancing Effective",
        "desc": "Passive institutional adjustments across Indian equities during the 15:00-15:30 closing auction.",
        "url": "https://www.msci.com/"
    },
    {
        "date": datetime.date(2026, 12, 3),
        "summary": "[MACRO] OPEC+ Joint Ministerial Meeting",
        "desc": "Crude oil production quotas review impacting Brent crude and Indian OMCs.",
        "url": "https://www.opec.org/"
    },
    {
        "date": datetime.date(2026, 12, 16),
        "summary": "[MACRO] US Federal Reserve FOMC Rate Decision",
        "desc": "FOMC rate decision & economic projections.",
        "url": "https://www.federalreserve.gov/"
    },
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

def build_tradingview_links(symbol, is_macro=False):
    clean = re.sub(r'[^A-Za-z0-9]', '', str(symbol))
    if is_macro:
        app_link = f"tradingview://chart?symbol={clean}"
        web_link = f"https://in.tradingview.com/chart/?symbol={clean}"
    else:
        app_link = f"tradingview://chart?symbol=NSE:{clean}"
        web_link = f"https://in.tradingview.com/chart/?symbol=NSE:{clean}"
    return app_link, web_link

def build_ipo_tradingview_links(company_name):
    clean = re.sub(r'[^A-Za-z0-9\s]', '', str(company_name))
    first_word = clean.split()[0].upper()
    app_link = f"tradingview://chart?symbol=NSE:{first_word}"
    web_link = f"https://in.tradingview.com/chart/?symbol=NSE:{first_word}"
    return app_link, web_link

def build_screener_links(symbol):
    clean = str(symbol).split()[0].replace("&", "")
    statements_url = f"https://www.screener.in/company/{clean}/consolidated/"
    pdf_archive_url = f"https://www.screener.in/company/{clean}/consolidated/#announcements"
    return statements_url, pdf_archive_url

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
            "ADANIPORTS", "TATASTEEL", "JSWSTEEL", "HCLTECH", "WIPRO", "TECHM"
        ]
    return symbols

def get_fy2026_comprehensive_ipo_database():
    return [
        {
            "name": "Veegaland Developers",
            "price": "₹130 - 140",
            "lot": "100 Shares",
            "gmp": "+18.5%",
            "type": "Mainboard",
            "open": datetime.date(2026, 9, 10),
            "close": datetime.date(2026, 9, 15),
            "allotment": datetime.date(2026, 9, 16),
            "listing": datetime.date(2026, 9, 18),
            "rhp": "https://www.bseindia.com/markets/PublicIssues/IPOIssue_new.aspx",
            "registrar": "https://linkintime.co.in/initial_offer/public-issues.html"
        },
        {
            "name": "Pranav Constructions",
            "price": "₹315 - 325",
            "lot": "45 Shares",
            "gmp": "+22.4%",
            "type": "Mainboard",
            "open": datetime.date(2026, 9, 7),
            "close": datetime.date(2026, 9, 9),
            "allotment": datetime.date(2026, 9, 10),
            "listing": datetime.date(2026, 9, 14),
            "rhp": "https://www.bseindia.com/markets/PublicIssues/IPOIssue_new.aspx",
            "registrar": "https://ris.kfintech.com/ipostatus/"
        },
        {
            "name": "Qualiance International",
            "price": "₹120 - 127",
            "lot": "1000 Shares",
            "gmp": "+31.5%",
            "type": "SME",
            "open": datetime.date(2026, 9, 4),
            "close": datetime.date(2026, 9, 8),
            "allotment": datetime.date(2026, 9, 9),
            "listing": datetime.date(2026, 9, 11),
            "rhp": "https://www.nseindia.com/market-data/all-upcoming-issues-ipo",
            "registrar": "https://www.bigshareonline.com/ipo_Allotment.html"
        },
        {
            "name": "Rays of Belief",
            "price": "₹227 - 239",
            "lot": "60 Shares",
            "gmp": "+16.7%",
            "type": "Mainboard",
            "open": datetime.date(2026, 9, 1),
            "close": datetime.date(2026, 9, 3),
            "allotment": datetime.date(2026, 9, 4),
            "listing": datetime.date(2026, 9, 8),
            "rhp": "https://www.bseindia.com/markets/PublicIssues/IPOIssue_new.aspx",
            "registrar": "https://linkintime.co.in/initial_offer/public-issues.html"
        },
        {
            "name": "Deepa Jewellers",
            "price": "₹168 - 177",
            "lot": "80 Shares",
            "gmp": "+12.8%",
            "type": "Mainboard",
            "open": datetime.date(2026, 9, 1),
            "close": datetime.date(2026, 9, 3),
            "allotment": datetime.date(2026, 9, 4),
            "listing": datetime.date(2026, 9, 8),
            "rhp": "https://www.bseindia.com/markets/PublicIssues/IPOIssue_new.aspx",
            "registrar": "https://ris.kfintech.com/ipostatus/"
        },
        {
            "name": "Farm Peace",
            "price": "₹59",
            "lot": "2000 Shares",
            "gmp": "+24.0%",
            "type": "SME",
            "open": datetime.date(2026, 9, 1),
            "close": datetime.date(2026, 9, 3),
            "allotment": datetime.date(2026, 9, 4),
            "listing": datetime.date(2026, 9, 8),
            "rhp": "https://www.bseindia.com/markets/PublicIssues/IPOIssue_new.aspx",
            "registrar": "https://www.bigshareonline.com/ipo_Allotment.html"
        },
        {
            "name": "Fly-Hi Maritime Travels",
            "price": "₹102",
            "lot": "1200 Shares",
            "gmp": "+14.5%",
            "type": "SME",
            "open": datetime.date(2026, 9, 1),
            "close": datetime.date(2026, 9, 3),
            "allotment": datetime.date(2026, 9, 4),
            "listing": datetime.date(2026, 9, 8),
            "rhp": "https://www.nseindia.com/market-data/all-upcoming-issues-ipo",
            "registrar": "https://linkintime.co.in/initial_offer/public-issues.html"
        },
        {
            "name": "Purple Style Labs",
            "price": "₹546 - 575",
            "lot": "25 Shares",
            "gmp": "+28.2%",
            "type": "Mainboard",
            "open": datetime.date(2026, 8, 31),
            "close": datetime.date(2026, 9, 2),
            "allotment": datetime.date(2026, 9, 3),
            "listing": datetime.date(2026, 9, 7),
            "rhp": "https://www.bseindia.com/markets/PublicIssues/IPOIssue_new.aspx",
            "registrar": "https://ris.kfintech.com/ipostatus/"
        },
        {
            "name": "ESDS Software Solution",
            "price": "₹429",
            "lot": "35 Shares",
            "gmp": "+15.2%",
            "type": "Mainboard",
            "open": datetime.date(2026, 8, 28),
            "close": datetime.date(2026, 9, 1),
            "allotment": datetime.date(2026, 9, 2),
            "listing": datetime.date(2026, 9, 4),
            "rhp": "https://www.bseindia.com/markets/PublicIssues/IPOIssue_new.aspx",
            "registrar": "https://linkintime.co.in/initial_offer/public-issues.html"
        },
        {
            "name": "Lumino Industries",
            "price": "₹82",
            "lot": "150 Shares",
            "gmp": "+52.0%",
            "type": "Mainboard",
            "open": datetime.date(2026, 8, 27),
            "close": datetime.date(2026, 8, 31),
            "allotment": datetime.date(2026, 9, 1),
            "listing": datetime.date(2026, 9, 3),
            "rhp": "https://www.bseindia.com/markets/PublicIssues/IPOIssue_new.aspx",
            "registrar": "https://ris.kfintech.com/ipostatus/"
        },
        {
            "name": "Kwick Forensic Solutions",
            "price": "₹90",
            "lot": "1600 Shares",
            "gmp": "+68.5%",
            "type": "SME",
            "open": datetime.date(2026, 8, 27),
            "close": datetime.date(2026, 8, 31),
            "allotment": datetime.date(2026, 9, 1),
            "listing": datetime.date(2026, 9, 3),
            "rhp": "https://www.nseindia.com/market-data/all-upcoming-issues-ipo",
            "registrar": "https://www.bigshareonline.com/ipo_Allotment.html"
        },
        {
            "name": "Augmont Enterprises",
            "price": "₹345",
            "lot": "40 Shares",
            "gmp": "+21.4%",
            "type": "Mainboard",
            "open": datetime.date(2026, 8, 14),
            "close": datetime.date(2026, 8, 18),
            "allotment": datetime.date(2026, 8, 19),
            "listing": datetime.date(2026, 8, 21),
            "rhp": "https://www.bseindia.com/markets/PublicIssues/IPOIssue_new.aspx",
            "registrar": "https://linkintime.co.in/initial_offer/public-issues.html"
        },
        {
            "name": "Tempsens Instruments",
            "price": "₹550",
            "lot": "25 Shares",
            "gmp": "+44.0%",
            "type": "Mainboard",
            "open": datetime.date(2026, 8, 13),
            "close": datetime.date(2026, 8, 17),
            "allotment": datetime.date(2026, 8, 18),
            "listing": datetime.date(2026, 8, 20),
            "rhp": "https://www.bseindia.com/markets/PublicIssues/IPOIssue_new.aspx",
            "registrar": "https://ris.kfintech.com/ipostatus/"
        },
        {
            "name": "Gaja Alternative Asset",
            "price": "₹195",
            "lot": "75 Shares",
            "gmp": "+18.0%",
            "type": "Mainboard",
            "open": datetime.date(2026, 8, 12),
            "close": datetime.date(2026, 8, 14),
            "allotment": datetime.date(2026, 8, 17),
            "listing": datetime.date(2026, 8, 19),
            "rhp": "https://www.bseindia.com/markets/PublicIssues/IPOIssue_new.aspx",
            "registrar": "https://linkintime.co.in/initial_offer/public-issues.html"
        },
        {
            "name": "Technocrats Plasma Systems",
            "price": "₹132",
            "lot": "1000 Shares",
            "gmp": "+53.0%",
            "type": "SME",
            "open": datetime.date(2026, 8, 14),
            "close": datetime.date(2026, 8, 18),
            "allotment": datetime.date(2026, 8, 19),
            "listing": datetime.date(2026, 8, 21),
            "rhp": "https://www.nseindia.com/market-data/all-upcoming-issues-ipo",
            "registrar": "https://www.bigshareonline.com/ipo_Allotment.html"
        }
    ]

def process_single_ticker(sym, today, cutoff_past, cutoff_future):
    """Processes corporate actions, payouts, splits, and quarterly board results into Feed 1."""
    corp_events = []
    ticker_str = f"{sym}.NS"
    app_link, web_link = build_tradingview_links(sym)
    statements_url, pdf_archive_url = build_screener_links(sym)
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
                        f"• Screener Statements & PDF Filings:\n  {pdf_archive_url}\n\n"
                        f"• Official NSE Company Desk:\n  {nse_quote_url}\n"
                    ))
                    ev_sp.add('location', 'NSE / BSE')
                    add_market_alarm(ev_sp, f"Today is the buy cutoff for {sym} Split/Bonus.")
                    corp_events.append(ev_sp)

        # 3. Results & Earnings Board Meetings (Moved into Feed 1)
        try:
            q_fin = t.quarterly_financials
            if q_fin is not None and not q_fin.empty:
                for col in q_fin.columns:
                    f_date = col.date() if hasattr(col, "date") else None
                    if f_date and cutoff_past <= f_date <= cutoff_future:
                        ev_res = Event()
                        ev_res.add('uid', f"res-q-{sym}-{f_date.isoformat()}")
                        ev_res.add('summary', f"[RESULTS / VOLATILITY] {sym} - Financial Results")
                        ev_res.add('dtstart', f_date)
                        ev_res.add('dtend', f_date + datetime.timedelta(days=1))
                        ev_res.add('url', web_link)
                        ev_res.add('description', (
                            f"EARNINGS RELEASE & OUTCOME DECLARATION\n\n"
                            f"• Symbol: {sym}\n"
                            f"• Open in TradingView App (Native):\n  {app_link}\n\n"
                            f"• Screener Balance Sheet:\n  {statements_url}\n\n"
                            f"• Official NSE Filings & Outcome PDFs:\n  {nse_quote_url}\n"
                        ))
                        ev_res.add('location', 'NSE / BSE')
                        add_market_alarm(ev_res, f"Quarterly Results Day: {sym}")
                        corp_events.append(ev_res)

            cal_df = t.calendar
            if cal_df is not None and not cal_df.empty:
                if "Earnings Date" in cal_df.index:
                    for ed in cal_df.loc["Earnings Date"]:
                        if hasattr(ed, "date"):
                            e_date = ed.date()
                            if cutoff_past <= e_date <= cutoff_future:
                                ev_bm = Event()
                                ev_bm.add('uid', f"results-bm-{sym}-{e_date.isoformat()}")
                                ev_bm.add('summary', f"[RESULTS / VOLATILITY] {sym} - Board Meeting")
                                ev_bm.add('dtstart', e_date)
                                ev_bm.add('dtend', e_date + datetime.timedelta(days=1))
                                ev_bm.add('url', web_link)
                                ev_bm.add('description', (
                                    f"HIGH VOLATILITY ALERT: Board of Directors Meeting for financial results.\n\n"
                                    f"• Symbol: {sym}\n"
                                    f"• Open in TradingView App (Native):\n  {app_link}\n\n"
                                    f"• Screener Profile: {statements_url}\n\n"
                                    f"• Official NSE Filings & Outcome PDFs:\n  {nse_quote_url}\n"
                                ))
                                ev_bm.add('location', 'NSE / BSE')
                                add_market_alarm(ev_bm, f"Board Meeting today: {sym}")
                                corp_events.append(ev_bm)
        except Exception:
            pass

    except Exception:
        pass

    return corp_events

def build_calendars():
    # -------------------------------------------------------------------------
    # FEED 1: Dividends, Results & Corporate Actions
    # -------------------------------------------------------------------------
    cal_div = Calendar()
    cal_div.add('prodid', '-//NSE Dividends, Results & Corporate Actions//EN')
    cal_div.add('version', '2.0')
    cal_div.add('x-wr-calname', '1. Dividends, Results & Corporate Actions')
    cal_div.add('x-wr-timezone', 'Asia/Kolkata')

    # -------------------------------------------------------------------------
    # FEED 2: IPOs, GMP & Listings
    # -------------------------------------------------------------------------
    cal_ipo = Calendar()
    cal_ipo.add('prodid', '-//Live Indian IPOs & GMP Hub//EN')
    cal_ipo.add('version', '2.0')
    cal_ipo.add('x-wr-calname', '2. Indian IPOs, GMP & Listings')
    cal_ipo.add('x-wr-timezone', 'Asia/Kolkata')

    # -------------------------------------------------------------------------
    # FEED 3: Macro, Economic Policy & Tax Framework
    # -------------------------------------------------------------------------
    cal_macro = Calendar()
    cal_macro.add('prodid', '-//Macro, Economic Policy & Tax Hub//EN')
    cal_macro.add('version', '2.0')
    cal_macro.add('x-wr-calname', '3. Macro, Policy & Tax Deadlines')
    cal_macro.add('x-wr-timezone', 'Asia/Kolkata')

    # -------------------------------------------------------------------------
    # FEED 4: Intraday, F&O Expiries & Momentum
    # -------------------------------------------------------------------------
    cal_fno = Calendar()
    cal_fno.add('prodid', '-//Intraday, Derivatives Expiry & Momentum//EN')
    cal_fno.add('version', '2.0')
    cal_fno.add('x-wr-calname', '4. Intraday, F&O Expiries & Momentum')
    cal_fno.add('x-wr-timezone', 'Asia/Kolkata')

    today = datetime.date.today()
    cutoff_past = datetime.date(2026, 4, 1)
    cutoff_future = today + datetime.timedelta(days=120)

    # Ingest Macro, Policy, Tax, and Holidays into Feed 3
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
            ev_m.add('description', f"{m['desc']}\n\n• Information Portal:\n  {m.get('url')}")
            add_market_alarm(ev_m, f"Market Alert: {m['summary']}")
            cal_macro.add_component(ev_m)

    # Ingest Weekly & Monthly Expiries into Feed 4 (Intraday & Derivatives)
    nifty_app, nifty_web = build_tradingview_links("NIFTY", is_macro=False)
    sensex_app, sensex_web = build_tradingview_links("SENSEX", is_macro=False)

    curr_scan = cutoff_past
    while curr_scan <= cutoff_future:
        # NSE Nifty Weekly Expiry (Tuesday)
        if CONFIG.get("ENABLE_NIFTY_WEEKLY_EXPIRY", True) and curr_scan.weekday() == 1:
            exp_date = curr_scan if is_trading_day(curr_scan) else get_previous_trading_day(curr_scan)
            ev_exp = Event()
            ev_exp.add('uid', f"exp-nifty-{curr_scan.isoformat()}")
            ev_exp.add('summary', "[F&O] NSE Nifty 50 Weekly Expiry (Tuesday)")
            ev_exp.add('dtstart', exp_date)
            ev_exp.add('dtend', exp_date + datetime.timedelta(days=1))
            ev_exp.add('url', nifty_web)
            ev_exp.add('description', (
                f"NSE NIFTY 50 WEEKLY DERIVATIVES EXPIRY\n"
                f"-----------------------------------------\n"
                f"• Benchmark Index Options Expiry.\n"
                f"• Expect gamma expansions and heightened theta decay after 01:30 PM IST.\n\n"
                f"• Open in TradingView App (Native):\n  {nifty_app}\n"
            ))
            cal_fno.add_component(ev_exp)

        # BSE Sensex Weekly Expiry (Thursday)
        if CONFIG.get("ENABLE_SENSEX_WEEKLY_EXPIRY", True) and curr_scan.weekday() == 3:
            exp_date = curr_scan if is_trading_day(curr_scan) else get_previous_trading_day(curr_scan)
            ev_exp = Event()
            ev_exp.add('uid', f"exp-sensex-{curr_scan.isoformat()}")
            ev_exp.add('summary', "[F&O] BSE Sensex Weekly Expiry (Thursday)")
            ev_exp.add('dtstart', exp_date)
            ev_exp.add('dtend', exp_date + datetime.timedelta(days=1))
            ev_exp.add('url', sensex_web)
            ev_exp.add('description', (
                f"BSE SENSEX WEEKLY DERIVATIVES EXPIRY\n"
                f"-----------------------------------------\n"
                f"• Benchmark Index Options Expiry.\n\n"
                f"• Open in TradingView App (Native):\n  {sensex_app}\n"
            ))
            cal_fno.add_component(ev_exp)

        curr_scan += datetime.timedelta(days=1)

    # NSE Monthly Single Stock F&O Expiry (Feed 4)
    if CONFIG.get("ENABLE_STOCK_FO_MONTHLY_EXPIRY", True):
        for yr in [2026, 2027]:
            for m in range(1, 13):
                first_next = datetime.date(yr + (1 if m == 12 else 0), 1 if m == 12 else m + 1, 1)
                last_d = first_next - datetime.timedelta(days=1)
                while last_d.weekday() != 3:
                    last_d -= datetime.timedelta(days=1)
                final_stock_exp = last_d if is_trading_day(last_d) else get_previous_trading_day(last_d)

                if cutoff_past <= final_stock_exp <= cutoff_future:
                    fo_app, fo_web = build_tradingview_links("NIFTY_FUT", is_macro=True)
                    ev_stk = Event()
                    ev_stk.add('uid', f"fo-stock-exp-{final_stock_exp.isoformat()}")
                    ev_stk.add('summary', f"[F&O STOCKS] NSE Monthly Stock Derivatives Expiry ({final_stock_exp.strftime('%b %Y')})")
                    ev_stk.add('dtstart', final_stock_exp)
                    ev_stk.add('dtend', final_stock_exp + datetime.timedelta(days=1))
                    ev_stk.add('url', fo_web)
                    ev_stk.add('description', (
                        f"NSE MONTHLY STOCK DERIVATIVES EXPIRY\n"
                        f"-----------------------------------------\n"
                        f"• Contract Expiry: All Single Stock Futures & Options contracts expire today (3:30 PM IST).\n"
                        f"• Physical Delivery: Compulsory physical delivery for in-the-money (ITM) long/short options.\n"
                        f"• Margin Escalation: Physical delivery margins apply to near-the-money and ITM strikes.\n"
                        f"-----------------------------------------\n"
                        f"• Open in TradingView App (Native):\n  {fo_app}\n"
                    ))
                    add_market_alarm(ev_stk, f"Stock F&O Expiry Today: Manage ITM delivery exposure.")
                    cal_fno.add_component(ev_stk)

    # Ingest Nifty 500 Actions & Results into Feed 1
    universe = get_live_nifty_500_symbols()
    print(f"Loaded {len(universe)} symbols from Nifty 500.")

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(process_single_ticker, sym, today, cutoff_past, cutoff_future): sym for sym in universe}
        for fut in as_completed(futures):
            for ev in fut.result():
                cal_div.add_component(ev)

    # Ingest IPO Lifecycle into Feed 2
    ipos = get_fy2026_comprehensive_ipo_database()
    print(f"Loaded {len(ipos)} comprehensive IPOs covering FY2026-27.")
    for ipo in ipos:
        ipo_app, ipo_web = build_ipo_tradingview_links(ipo['name'])

        # OPEN
        if cutoff_past <= ipo['open'] <= cutoff_future:
            ev_o = Event()
            ev_o.add('uid', f"ipo-open-{ipo['name'].replace(' ', '')}-{ipo['open'].isoformat()}")
            ev_o.add('summary', f"[IPO OPEN] {ipo['name']} ({ipo['type']})")
            ev_o.add('dtstart', ipo['open'])
            ev_o.add('dtend', ipo['open'] + datetime.timedelta(days=1))
            ev_o.add('url', ipo_web)
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
                f"• Open in TradingView App (Native):\n  {ipo_app}\n\n"
                f"• Official Exchange Prospectus & RHP:\n  {ipo['rhp']}\n\n"
                f"• Live GMP & Subscription Tracker:\n  https://www.investorgain.com/report/live-ipo-gmp/331/\n"
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
            ev_c.add('url', ipo_web)
            ev_c.add('description', (
                f"FINAL BIDDING & MANDATE APPROVAL DAY\n"
                f"-----------------------------------------\n"
                f"• Final Cutoff: 5:00 PM IST (UPI Mandate Authorization)\n"
                f"• Issue: {ipo['name']}\n"
                f"• Price Band: {ipo['price']}\n"
                f"• Final Grey Market Premium: {ipo['gmp']}\n"
                f"-----------------------------------------\n"
                f"• Open in TradingView App (Native):\n  {ipo_app}\n\n"
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
            ev_a.add('url', ipo_web)
            ev_a.add('description', (
                f"BASIS OF ALLOTMENT FINALIZATION\n"
                f"-----------------------------------------\n"
                f"Check status with PAN on designated registrar desks:\n\n"
                f"• Designated Registrar Desk:\n  {ipo['registrar']}\n\n"
                f"• Open in TradingView App (Native):\n  {ipo_app}\n\n"
                f"• Alternate Link Intime Desk:\n  https://linkintime.co.in/initial_offer/public-issues.html\n\n"
                f"• Alternate KFintech Desk:\n  https://ris.kfintech.com/ipostatus/\n"
            ))
            add_market_alarm(ev_a, f"Check Allotment Today: {ipo['name']}")
            cal_ipo.add_component(ev_a)

        # LISTING
        if cutoff_past <= ipo['listing'] <= cutoff_future:
            listing_url = "https://www.nseindia.com/market-data/new-stock-exchange-listings-today"
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
                f"• Issue: {ipo['name']}\n"
                f"• Category: {ipo['type']}\n"
                f"• Issue Price: {ipo['price']}\n"
                f"• Final Grey Market Premium (GMP): {ipo['gmp']}\n"
                f"-----------------------------------------\n"
                f"• Open in TradingView App (Native):\n  {ipo_app}\n\n"
                f"• Official NSE/BSE New Listing Tracker:\n  {listing_url}\n"
            ))
            add_market_alarm(ev_l, f"Listing Debut Today (10 AM): {ipo['name']}")
            cal_ipo.add_component(ev_l)

    # -------------------------------------------------------------------------
    # WRITE ALL 4 MODULAR ICS FILES
    # -------------------------------------------------------------------------
    with open("dividends_actions.ics", "wb") as f:
        f.write(cal_div.to_ical())
    with open("ipos_listings.ics", "wb") as f:
        f.write(cal_ipo.to_ical())
    with open("macro_policy_tax.ics", "wb") as f:
        f.write(cal_macro.to_ical())
    with open("intraday_fno_momentum.ics", "wb") as f:
        f.write(cal_fno.to_ical())

    # -------------------------------------------------------------------------
    # WRITE MASTER CONSOLIDATED CALENDAR (Everything combined)
    # -------------------------------------------------------------------------
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

    print("All 4 modular feeds and Master calendar compiled successfully.")

if __name__ == "__main__":
    build_calendars()
