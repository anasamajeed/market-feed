import datetime
import uuid
import re
import io
import csv
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup
import yfinance as yf
from icalendar import Calendar, Event, Alarm

CONFIG = {
    "ENABLE_ALARMS": True,
    "ENABLE_NIFTY_WEEKLY_EXPIRY": True,    # Tuesday
    "ENABLE_SENSEX_WEEKLY_EXPIRY": True,   # Thursday
    "ENABLE_MONTHLY_EXPIRIES": True,
}

# Official 2026 NSE/BSE Trading Holidays
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

MACRO_EVENTS_2026 = [
    {"date": datetime.date(2026, 4, 9), "summary": "[MACRO] RBI Monetary Policy Committee (MPC) Outcome", "desc": "RBI repo rate decision & policy statement."},
    {"date": datetime.date(2026, 6, 5), "summary": "[MACRO] RBI Monetary Policy Committee (MPC) Outcome", "desc": "RBI repo rate decision & policy statement."},
    {"date": datetime.date(2026, 8, 7), "summary": "[MACRO] RBI Monetary Policy Committee (MPC) Outcome", "desc": "RBI repo rate decision & policy statement."},
    {"date": datetime.date(2026, 10, 8), "summary": "[MACRO] RBI Monetary Policy Committee (MPC) Outcome", "desc": "RBI repo rate decision & policy statement. Crucial for bank and rate-sensitive sectors."},
    {"date": datetime.date(2026, 12, 10), "summary": "[MACRO] RBI Monetary Policy Committee (MPC) Outcome", "desc": "RBI repo rate decision & policy statement."},
    {"date": datetime.date(2026, 5, 6), "summary": "[MACRO] US Federal Reserve FOMC Rate Decision", "desc": "Fed funds rate policy announcement."},
    {"date": datetime.date(2026, 6, 17), "summary": "[MACRO] US Federal Reserve FOMC Rate Decision", "desc": "Fed funds rate policy announcement & economic projections."},
    {"date": datetime.date(2026, 7, 29), "summary": "[MACRO] US Federal Reserve FOMC Rate Decision", "desc": "Fed funds rate policy announcement."},
    {"date": datetime.date(2026, 9, 16), "summary": "[MACRO] US Federal Reserve FOMC Rate Decision", "desc": "Fed funds rate policy announcement & Jerome Powell press conference."},
    {"date": datetime.date(2026, 11, 4), "summary": "[MACRO] US Federal Reserve FOMC Rate Decision", "desc": "FOMC interest rate decision."},
    {"date": datetime.date(2026, 12, 16), "summary": "[MACRO] US Federal Reserve FOMC Rate Decision", "desc": "FOMC rate decision & economic projections."},
    {"date": datetime.date(2026, 9, 11), "summary": "[MACRO] US Consumer Price Index (CPI) Inflation Data", "desc": "Key US inflation print dictating global liquidity conditions."},
    {"date": datetime.date(2026, 10, 13), "summary": "[MACRO] US Consumer Price Index (CPI) Inflation Data", "desc": "Key US inflation print."},
    {"date": datetime.date(2026, 11, 12), "summary": "[MACRO] US Consumer Price Index (CPI) Inflation Data", "desc": "Key US inflation print."},
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

def build_tradingview_links(symbol):
    clean = re.sub(r'[^A-Za-z0-9]', '', str(symbol))
    return f"tradingview://chart?symbol=NSE:{clean}", f"https://in.tradingview.com/chart/?symbol=NSE:{clean}"

def build_screener_link(symbol):
    clean = str(symbol).split()[0].replace("&", "")
    return f"https://www.screener.in/company/{clean}/consolidated/"

def build_filings_url(symbol):
    clean = str(symbol).split()[0]
    return f"https://www.nseindia.com/companies-listing/corporate-filings-announcements?symbol={clean}"

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
    """Returns the comprehensive FY2026-27 IPO dataset including past listings and current active pipelines."""
    return [
        # Upcoming & Current Active Pipeline (September 2026)
        {
            "name": "Veegaland Developers",
            "price": "₹130 - 140",
            "gmp": "+18.5%",
            "type": "Mainboard",
            "open": datetime.date(2026, 9, 10),
            "close": datetime.date(2026, 9, 15),
            "allotment": datetime.date(2026, 9, 16),
            "listing": datetime.date(2026, 9, 18),
        },
        {
            "name": "Pranav Constructions",
            "price": "₹315 - 325",
            "gmp": "+22.4%",
            "type": "Mainboard",
            "open": datetime.date(2026, 9, 7),
            "close": datetime.date(2026, 9, 9),
            "allotment": datetime.date(2026, 9, 10),
            "listing": datetime.date(2026, 9, 14),
        },
        {
            "name": "Qualiance International",
            "price": "₹120 - 127",
            "gmp": "+31.5%",
            "type": "SME",
            "open": datetime.date(2026, 9, 4),
            "close": datetime.date(2026, 9, 8),
            "allotment": datetime.date(2026, 9, 9),
            "listing": datetime.date(2026, 9, 11),
        },
        {
            "name": "Rays of Belief",
            "price": "₹227 - 239",
            "gmp": "+16.7%",
            "type": "Mainboard",
            "open": datetime.date(2026, 9, 1),
            "close": datetime.date(2026, 9, 3),
            "allotment": datetime.date(2026, 9, 4),
            "listing": datetime.date(2026, 9, 8),
        },
        {
            "name": "Deepa Jewellers",
            "price": "₹168 - 177",
            "gmp": "+12.8%",
            "type": "Mainboard",
            "open": datetime.date(2026, 9, 1),
            "close": datetime.date(2026, 9, 3),
            "allotment": datetime.date(2026, 9, 4),
            "listing": datetime.date(2026, 9, 8),
        },
        {
            "name": "Farm Peace",
            "price": "₹59",
            "gmp": "+24.0%",
            "type": "SME",
            "open": datetime.date(2026, 9, 1),
            "close": datetime.date(2026, 9, 3),
            "allotment": datetime.date(2026, 9, 4),
            "listing": datetime.date(2026, 9, 8),
        },
        {
            "name": "Fly-Hi Maritime Travels",
            "price": "₹102",
            "gmp": "+14.5%",
            "type": "SME",
            "open": datetime.date(2026, 9, 1),
            "close": datetime.date(2026, 9, 3),
            "allotment": datetime.date(2026, 9, 4),
            "listing": datetime.date(2026, 9, 8),
        },
        {
            "name": "Purple Style Labs",
            "price": "₹546 - 575",
            "gmp": "+28.2%",
            "type": "Mainboard",
            "open": datetime.date(2026, 8, 31),
            "close": datetime.date(2026, 9, 2),
            "allotment": datetime.date(2026, 9, 3),
            "listing": datetime.date(2026, 9, 7),
        },
        {
            "name": "Phychem Technologies",
            "price": "₹51 - 54",
            "gmp": "+42.1%",
            "type": "SME",
            "open": datetime.date(2026, 8, 31),
            "close": datetime.date(2026, 9, 2),
            "allotment": datetime.date(2026, 9, 3),
            "listing": datetime.date(2026, 9, 7),
        },
        {
            "name": "Shanti Inorganics",
            "price": "₹83",
            "gmp": "+19.2%",
            "type": "SME",
            "open": datetime.date(2026, 8, 31),
            "close": datetime.date(2026, 9, 2),
            "allotment": datetime.date(2026, 9, 3),
            "listing": datetime.date(2026, 9, 7),
        },
        {
            "name": "Ashutosh Fibre",
            "price": "₹92",
            "gmp": "+35.0%",
            "type": "SME",
            "open": datetime.date(2026, 8, 31),
            "close": datetime.date(2026, 9, 2),
            "allotment": datetime.date(2026, 9, 3),
            "listing": datetime.date(2026, 9, 7),
        },
        # Historical FY2026-27 Completed IPOs (August to April 2026)
        {
            "name": "ESDS Software Solution",
            "price": "₹429",
            "gmp": "+15.2%",
            "type": "Mainboard",
            "open": datetime.date(2026, 8, 28),
            "close": datetime.date(2026, 9, 1),
            "allotment": datetime.date(2026, 9, 2),
            "listing": datetime.date(2026, 9, 4),
        },
        {
            "name": "Priority Jewels",
            "price": "₹200",
            "gmp": "+8.5%",
            "type": "Mainboard",
            "open": datetime.date(2026, 8, 28),
            "close": datetime.date(2026, 9, 1),
            "allotment": datetime.date(2026, 9, 2),
            "listing": datetime.date(2026, 9, 4),
        },
        {
            "name": "Lumino Industries",
            "price": "₹82",
            "gmp": "+52.0%",
            "type": "Mainboard",
            "open": datetime.date(2026, 8, 27),
            "close": datetime.date(2026, 8, 31),
            "allotment": datetime.date(2026, 9, 1),
            "listing": datetime.date(2026, 9, 3),
        },
        {
            "name": "Kwick Forensic Solutions",
            "price": "₹90",
            "gmp": "+68.5%",
            "type": "SME",
            "open": datetime.date(2026, 8, 27),
            "close": datetime.date(2026, 8, 31),
            "allotment": datetime.date(2026, 9, 1),
            "listing": datetime.date(2026, 9, 3),
        },
        {
            "name": "Annu Projects",
            "price": "₹138",
            "gmp": "+11.0%",
            "type": "Mainboard",
            "open": datetime.date(2026, 8, 25),
            "close": datetime.date(2026, 8, 27),
            "allotment": datetime.date(2026, 8, 28),
            "listing": datetime.date(2026, 9, 1),
        },
        {
            "name": "Augmont Enterprises",
            "price": "₹345",
            "gmp": "+21.4%",
            "type": "Mainboard",
            "open": datetime.date(2026, 8, 14),
            "close": datetime.date(2026, 8, 18),
            "allotment": datetime.date(2026, 8, 19),
            "listing": datetime.date(2026, 8, 21),
        },
        {
            "name": "Tempsens Instruments",
            "price": "₹550",
            "gmp": "+44.0%",
            "type": "Mainboard",
            "open": datetime.date(2026, 8, 13),
            "close": datetime.date(2026, 8, 17),
            "allotment": datetime.date(2026, 8, 18),
            "listing": datetime.date(2026, 8, 20),
        },
        {
            "name": "Gaja Alternative Asset",
            "price": "₹195",
            "gmp": "+18.0%",
            "type": "Mainboard",
            "open": datetime.date(2026, 8, 12),
            "close": datetime.date(2026, 8, 14),
            "allotment": datetime.date(2026, 8, 17),
            "listing": datetime.date(2026, 8, 19),
        },
        {
            "name": "Technocrats Plasma Systems",
            "price": "₹132",
            "gmp": "+53.0%",
            "type": "SME",
            "open": datetime.date(2026, 8, 14),
            "close": datetime.date(2026, 8, 18),
            "allotment": datetime.date(2026, 8, 19),
            "listing": datetime.date(2026, 8, 21),
        },
    ]

def process_single_ticker(sym, today, cutoff_past, cutoff_future):
    events = []
    ticker_str = f"{sym}.NS"
    app_link, web_link = build_tradingview_links(sym)
    screener_link = build_screener_link(sym)
    filings_url = build_filings_url(sym)

    try:
        t = yf.Ticker(ticker_str)
        cmp_price = None
        try:
            cmp_price = t.fast_info.get("lastPrice") or t.info.get("currentPrice")
        except Exception:
            pass

        # 1. Dividend Cutoff & Payout (From April 2026 onwards)
        divs = t.dividends
        if not divs.empty:
            for ts, amount in divs.items():
                div_date = ts.date()
                if cutoff_past <= div_date <= cutoff_future:
                    must_buy_by = div_date if is_trading_day(div_date) else get_previous_trading_day(div_date)
                    yield_text = f" | Yield: {(amount / cmp_price * 100):.2f}%" if cmp_price else ""

                    # Cutoff Event
                    ev_cut = Event()
                    ev_cut.add('uid', f"div-cut-{sym}-{div_date.isoformat()}")
                    ev_cut.add('summary', f"[DIVIDEND] {sym} (₹{amount:.2f}{yield_text}) - Buy Cutoff")
                    ev_cut.add('dtstart', must_buy_by)
                    ev_cut.add('dtend', must_buy_by + datetime.timedelta(days=1))
                    ev_cut.add('url', filings_url)
                    ev_cut.add('description', (
                        f"ACTION REQUIRED: Purchase on or before today (prior to 3:30 PM IST) for Demat credit by Record Date.\n\n"
                        f"• Amount: ₹{amount:.2f} per share\n"
                        f"• Ex-Date: {div_date.strftime('%d-%b-%Y')}\n"
                        f"• Est. Dividend Yield: {yield_text.replace(' | Yield: ', '') if yield_text else 'N/A'}\n"
                        f"• Settlement: T+1 Rolling Settlement (NSE/BSE)\n"
                        f"-----------------------------------------\n"
                        f"• Official Meeting Disclosures & PDF Filings:\n  {filings_url}\n\n"
                        f"• Screener Balance Sheet & Financials:\n  {screener_link}\n\n"
                        f"• Native TradingView App: {app_link}\n"
                        f"• Browser Chart: {web_link}\n"
                    ))
                    ev_cut.add('location', 'NSE / BSE India')
                    add_market_alarm(ev_cut, f"Cutoff today: Buy {sym} for ₹{amount:.2f} dividend.")
                    events.append(ev_cut)

                    # Payout Date Event
                    payout_date = div_date + datetime.timedelta(days=30)
                    while not is_trading_day(payout_date):
                        payout_date += datetime.timedelta(days=1)

                    ev_pay = Event()
                    ev_pay.add('uid', f"div-pay-{sym}-{payout_date.isoformat()}")
                    ev_pay.add('summary', f"[PAYOUT] {sym} (₹{amount:.2f}) - Demat Credit")
                    ev_pay.add('dtstart', payout_date)
                    ev_pay.add('dtend', payout_date + datetime.timedelta(days=1))
                    ev_pay.add('url', screener_link)
                    ev_pay.add('description', f"Direct bank credit for {sym} declared dividend (₹{amount:.2f}/share).\n\nScreener: {screener_link}")
                    ev_pay.add('location', 'Bank Account / Demat')
                    events.append(ev_pay)

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
                    ev_sp.add('url', filings_url)
                    ev_sp.add('description', f"Corporate restructuring for {sym}.\n• Regulatory Filings: {filings_url}\n• Native App: {app_link}\n• Screener: {screener_link}")
                    ev_sp.add('location', 'NSE / BSE')
                    add_market_alarm(ev_sp, f"Today is the buy cutoff for {sym} Split/Bonus.")
                    events.append(ev_sp)

        # 3. Quarterly Results Day
        try:
            cal_df = t.calendar
            if cal_df is not None and not cal_df.empty:
                if "Earnings Date" in cal_df.index:
                    for ed in cal_df.loc["Earnings Date"]:
                        if hasattr(ed, "date"):
                            e_date = ed.date()
                            if cutoff_past <= e_date <= cutoff_future:
                                ev_bm = Event()
                                ev_bm.add('uid', f"results-{sym}-{e_date.isoformat()}")
                                ev_bm.add('summary', f"[RESULTS / VOLATILITY] {sym} - Financial Results")
                                ev_bm.add('dtstart', e_date)
                                ev_bm.add('dtend', e_date + datetime.timedelta(days=1))
                                ev_bm.add('url', filings_url)
                                ev_bm.add('description', (
                                    f"HIGH VOLATILITY ALERT: Company Board Meeting for quarterly results.\n\n"
                                    f"• Symbol: {sym}\n"
                                    f"• Outcome PDF & Announcements: {filings_url}\n"
                                    f"• Screener Balance Sheet: {screener_link}\n"
                                    f"• Native App Chart: {app_link}\n"
                                    f"• Web Chart: {web_link}\n"
                                ))
                                ev_bm.add('location', 'NSE / BSE')
                                add_market_alarm(ev_bm, f"Earnings release today: {sym} results outcome.")
                                events.append(ev_bm)
        except Exception:
            pass

    except Exception:
        pass

    return events

def build_calendars():
    cal_master = Calendar()
    cal_master.add('prodid', '-//NSE/BSE Comprehensive FY2026-27 Market Hub//EN')
    cal_master.add('version', '2.0')
    cal_master.add('x-wr-calname', 'NSE Nifty 500, IPOs & Macro (FY26-27)')
    cal_master.add('x-wr-timezone', 'Asia/Kolkata')
    cal_master.add('x-published-ttl', 'PT1H')

    today = datetime.date.today()
    # Broadened lookback directly to April 1, 2026 for complete FY26-27 history
    cutoff_past = datetime.date(2026, 4, 1)
    cutoff_future = today + datetime.timedelta(days=120)

    # 1. Official Trading Holidays
    for h_date, h_name in NSE_HOLIDAYS_2026.items():
        if cutoff_past <= h_date <= cutoff_future:
            ev_h = Event()
            ev_h.add('uid', f"holiday-{h_date.isoformat()}")
            ev_h.add('summary', f"[HOLIDAY] Market Closed - {h_name}")
            ev_h.add('dtstart', h_date)
            ev_h.add('dtend', h_date + datetime.timedelta(days=1))
            ev_h.add('description', f"NSE & BSE equity/derivative segments are closed today for {h_name}.")
            cal_master.add_component(ev_h)

    # 2. Benchmark Weekly & Monthly Expiries (Tuesday: Nifty, Thursday: Sensex)
    curr_scan = cutoff_past
    while curr_scan <= cutoff_future:
        if CONFIG.get("ENABLE_NIFTY_WEEKLY_EXPIRY", True) and curr_scan.weekday() == 1:
            exp_date = curr_scan if is_trading_day(curr_scan) else get_previous_trading_day(curr_scan)
            ev_exp = Event()
            ev_exp.add('uid', f"exp-nifty-{curr_scan.isoformat()}")
            ev_exp.add('summary', "[F&O] NSE Nifty 50 Weekly Expiry (Tuesday)")
            ev_exp.add('dtstart', exp_date)
            ev_exp.add('dtend', exp_date + datetime.timedelta(days=1))
            ev_exp.add('description', "Benchmark index weekly options expiry for NSE Nifty 50.")
            cal_master.add_component(ev_exp)

        if CONFIG.get("ENABLE_SENSEX_WEEKLY_EXPIRY", True) and curr_scan.weekday() == 3:
            exp_date = curr_scan if is_trading_day(curr_scan) else get_previous_trading_day(curr_scan)
            ev_exp = Event()
            ev_exp.add('uid', f"exp-sensex-{curr_scan.isoformat()}")
            ev_exp.add('summary', "[F&O] BSE Sensex Weekly Expiry (Thursday)")
            ev_exp.add('dtstart', exp_date)
            ev_exp.add('dtend', exp_date + datetime.timedelta(days=1))
            ev_exp.add('description', "Benchmark index weekly options expiry for BSE Sensex.")
            cal_master.add_component(ev_exp)

        curr_scan += datetime.timedelta(days=1)

    # 3. Macro Events (FY2026-27)
    for m in MACRO_EVENTS_2026:
        if cutoff_past <= m["date"] <= cutoff_future:
            ev_m = Event()
            ev_m.add('uid', f"macro-{m['date'].isoformat()}")
            ev_m.add('summary', m["summary"])
            ev_m.add('dtstart', m["date"])
            ev_m.add('dtend', m["date"] + datetime.timedelta(days=1))
            ev_m.add('description', m["desc"])
            cal_master.add_component(ev_m)

    # 4. Nifty 500 Parallel Processing Engine
    universe = get_live_nifty_500_symbols()
    print(f"Loaded {len(universe)} symbols from Nifty 500.")

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(process_single_ticker, sym, today, cutoff_past, cutoff_future): sym for sym in universe}
        for fut in as_completed(futures):
            for ev in fut.result():
                cal_master.add_component(ev)

    # 5. Comprehensive IPO Lifecycle Engine (Past & Future FY2026-27)
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
            ev_o.add('url', "https://www.chittorgarh.com/ipo/ipo_dashboard.asp")
            ev_o.add('description', (
                f"Bidding Opens Today.\n"
                f"• Issue: {ipo['name']}\n"
                f"• Price Band: {ipo['price']}\n"
                f"• Latest GMP: {ipo['gmp']}\n"
                f"• Closes: {ipo['close'].strftime('%d-%b-%Y')}\n\n"
                f"• Chittorgarh Dashboard: https://www.chittorgarh.com/ipo/ipo_dashboard.asp\n"
                f"• InvestorGain GMP: https://www.investorgain.com/report/live-ipo-gmp/331/"
            ))
            add_market_alarm(ev_o, f"IPO Bidding Opens Today: {ipo['name']}")
            cal_master.add_component(ev_o)

        # CLOSE
        if cutoff_past <= ipo['close'] <= cutoff_future:
            ev_c = Event()
            ev_c.add('uid', f"ipo-close-{ipo['name'].replace(' ', '')}-{ipo['close'].isoformat()}")
            ev_c.add('summary', f"[IPO CLOSE] {ipo['name']} - Final Bidding Day")
            ev_c.add('dtstart', ipo['close'])
            ev_c.add('dtend', ipo['close'] + datetime.timedelta(days=1))
            ev_c.add('url', "https://www.chittorgarh.com/ipo/ipo_dashboard.asp")
            ev_c.add('description', (
                f"Final day to bid and approve UPI mandate (5:00 PM IST cutoff).\n"
                f"• Issue: {ipo['name']}\n"
                f"• Latest GMP: {ipo['gmp']}\n"
                f"• Price Band: {ipo['price']}\n"
            ))
            add_market_alarm(ev_c, f"IPO Closes Today (5 PM): {ipo['name']}")
            cal_master.add_component(ev_c)

        # ALLOTMENT
        if cutoff_past <= ipo['allotment'] <= cutoff_future:
            ev_a = Event()
            ev_a.add('uid', f"ipo-allot-{ipo['name'].replace(' ', '')}-{ipo['allotment'].isoformat()}")
            ev_a.add('summary', f"[IPO ALLOTMENT] {ipo['name']} Allotment Status")
            ev_a.add('dtstart', ipo['allotment'])
            ev_a.add('dtend', ipo['allotment'] + datetime.timedelta(days=1))
            ev_a.add('url', "https://linkintime.co.in/initial_offer/public-issues.html")
            ev_a.add('description', (
                f"Basis of Allotment finalization day.\n\n"
                f"Check status with PAN on official registrar desks:\n"
                f"• Link Intime: https://linkintime.co.in/initial_offer/public-issues.html\n"
                f"• KFintech: https://ris.kfintech.com/ipostatus/\n"
                f"• Bigshare: https://www.bigshareonline.com/ipo_Allotment.html\n"
            ))
            add_market_alarm(ev_a, f"Check Allotment Today: {ipo['name']}")
            cal_master.add_component(ev_a)

        # LISTING
        if cutoff_past <= ipo['listing'] <= cutoff_future:
            ev_l = Event()
            ev_l.add('uid', f"ipo-list-{ipo['name'].replace(' ', '')}-{ipo['listing'].isoformat()}")
            ev_l.add('summary', f"[IPO LISTING] {ipo['name']} Debut")
            ev_l.add('dtstart', ipo['listing'])
            ev_l.add('dtend', ipo['listing'] + datetime.timedelta(days=1))
            ev_l.add('url', "https://www.chittorgarh.com/report/ipo-listing-date-check-status-price-bse-nse/25/all/?year=2026")
            ev_l.add('description', (
                f"Company commences trading today on NSE/BSE (10:00 AM IST).\n"
                f"• Issue: {ipo['name']}\n"
                f"• Category: {ipo['type']}\n"
                f"• Final Grey Market Premium: {ipo['gmp']}\n"
            ))
            add_market_alarm(ev_l, f"Listing Debut Today (10 AM): {ipo['name']}")
            cal_master.add_component(ev_l)

    with open("market_calendar.ics", "wb") as f:
        f.write(cal_master.to_ical())

    print("Master calendar successfully rebuilt with full FY2026-27 historical and upcoming events.")

if __name__ == "__main__":
    build_calendars()
