import datetime
import uuid
import io
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import yfinance as yf
from icalendar import Calendar, Event

# 2026 Indian Stock Market Holidays for T+1 Demat Settlement
NSE_HOLIDAYS_2026 = {
    datetime.date(2026, 1, 26),
    datetime.date(2026, 3, 6),
    datetime.date(2026, 4, 3),
    datetime.date(2026, 4, 14),
    datetime.date(2026, 5, 1),
    datetime.date(2026, 8, 15),
    datetime.date(2026, 10, 2),
    datetime.date(2026, 10, 20),
    datetime.date(2026, 11, 10),
    datetime.date(2026, 12, 25),
}

# High-impact global and domestic macroeconomic dates for 2026
MACRO_EVENTS_2026 = [
    {"date": datetime.date(2026, 10, 8), "summary": "[MACRO] RBI Monetary Policy Committee (MPC) Outcome", "desc": "RBI repo rate decision & policy statement. Crucial for bank and rate-sensitive sectors."},
    {"date": datetime.date(2026, 12, 10), "summary": "[MACRO] RBI Monetary Policy Committee (MPC) Outcome", "desc": "RBI repo rate decision & policy statement."},
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

def build_tradingview_link(symbol):
    clean = symbol.replace("&", "_").replace("-", "_")
    return f"https://in.tradingview.com/chart/?symbol=NSE:{clean}"

def build_screener_link(symbol):
    return f"https://www.screener.in/company/{symbol}/consolidated/"

def get_live_nifty_500_symbols():
    """Downloads the official, real-time Nifty 500 constituent universe from NSE Indices repository."""
    url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    }
    symbols = []
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            reader = csv.DictReader(io.StringIO(resp.text))
            for row in reader:
                sym = row.get("Symbol", "").strip()
                if sym:
                    symbols.append(sym)
    except Exception as e:
        print(f"Could not fetch dynamic Nifty 500 list: {e}")

    # Fallback to liquid high-volume baseline if NSE repository rate-limits
    if len(symbols) < 50:
        symbols = [
            "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "ITC", "SBIN",
            "BHARTIARTL", "KOTAKBANK", "LT", "HINDUNILVR", "AXISBANK", "BAJFINANCE",
            "MARUTI", "ASIANPAINT", "TITAN", "SUNPHARMA", "ULTRACEMCO", "NTPC",
            "POWERGRID", "ONGC", "COALINDIA", "BAJAJFINSV", "M&M", "ADANIENT",
            "ADANIPORTS", "TATASTEEL", "JSWSTEEL", "HCLTECH", "WIPRO", "TECHM",
            "VEDL", "IOC", "BPCL", "HINDZINC", "DIVISLAB", "DRREDDY", "CIPLA",
            "EICHERMOT", "HEROMOTOCO", "BRITANNIA", "NESTLEIND", "PIDILITIND",
            "SIEMENS", "ABB", "HAL", "BEL", "PFC", "RECLTD", "GAIL", "NMDC"
        ]
    return symbols

def process_single_ticker(sym, today, cutoff_past, cutoff_future):
    """Worker task that extracts all corporate actions and results for a single stock."""
    events = []
    ticker_str = f"{sym}.NS"
    try:
        t = yf.Ticker(ticker_str)
        
        # 1. Dividend parsing
        divs = t.dividends
        if not divs.empty:
            for ts, amount in divs.items():
                div_date = ts.date()
                if cutoff_past <= div_date <= cutoff_future:
                    must_buy_by = div_date if is_trading_day(div_date) else get_previous_trading_day(div_date)
                    
                    ev = Event()
                    ev.add('uid', str(uuid.uuid4()))
                    ev.add('summary', f"[DIVIDEND] {sym} (₹{amount:.2f}) - Buy Cutoff")
                    ev.add('dtstart', must_buy_by)
                    ev.add('dtend', must_buy_by + datetime.timedelta(days=1))
                    ev.add('description', (
                        f"ACTION: Purchase before 3:30 PM IST today for Demat credit by Record Date.\n\n"
                        f"• Amount: ₹{amount:.2f} per share\n"
                        f"• Ex-Date: {div_date.strftime('%d-%b-%Y')}\n"
                        f"• Settlement: T+1 Rolling Cycle (NSE/BSE)\n"
                        f"-----------------------------------------\n"
                        f"• TradingView Daily Chart:\n  {build_tradingview_link(sym)}\n\n"
                        f"• Screener Fundamentals & Dividend History:\n  {build_screener_link(sym)}\n\n"
                        f"• NSE Corporate Filings:\n  https://www.nseindia.com/companies-listing/corporate-filings-actions\n"
                    ))
                    ev.add('location', 'NSE / BSE India')
                    events.append(ev)

        # 2. Stock splits / Bonus distributions
        splits = t.splits
        if not splits.empty:
            for ts, ratio in splits.items():
                split_date = ts.date()
                if cutoff_past <= split_date <= cutoff_future:
                    must_buy_by = split_date if is_trading_day(split_date) else get_previous_trading_day(split_date)
                    ev = Event()
                    ev.add('uid', str(uuid.uuid4()))
                    ev.add('summary', f"[SPLIT/BONUS] {sym} (Ratio {ratio}) - Cutoff")
                    ev.add('dtstart', must_buy_by)
                    ev.add('dtend', must_buy_by + datetime.timedelta(days=1))
                    ev.add('description', (
                        f"Stock split or bonus share allotment.\n"
                        f"• Ratio: {ratio}\n"
                        f"• TradingView: {build_tradingview_link(sym)}\n"
                        f"• Screener: {build_screener_link(sym)}\n"
                    ))
                    ev.add('location', 'NSE / BSE India')
                    events.append(ev)

        # 3. Quarterly earnings & Board Meeting agendas
        try:
            cal_df = t.calendar
            if cal_df is not None and not cal_df.empty:
                if "Earnings Date" in cal_df.index:
                    for ed in cal_df.loc["Earnings Date"]:
                        if hasattr(ed, "date"):
                            e_date = ed.date()
                            if today <= e_date <= cutoff_future:
                                ev = Event()
                                ev.add('uid', str(uuid.uuid4()))
                                ev.add('summary', f"[RESULTS] {sym} - Board Meeting")
                                ev.add('dtstart', e_date)
                                ev.add('dtend', e_date + datetime.timedelta(days=1))
                                ev.add('description', (
                                    f"Board of Directors financial results declaration.\n\n"
                                    f"• Symbol: {sym}\n"
                                    f"• TradingView Daily Chart: {build_tradingview_link(sym)}\n"
                                    f"• Screener Profile: {build_screener_link(sym)}\n"
                                ))
                                ev.add('location', 'NSE / BSE')
                                events.append(ev)
        except Exception:
            pass

    except Exception:
        pass

    return events

def build_calendar():
    cal = Calendar()
    cal.add('prodid', '-//Nifty 500 Capital Markets Live Action Hub//EN')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', 'NSE Nifty 500 Actions, Results & Macro')
    cal.add('x-wr-timezone', 'Asia/Kolkata')
    cal.add('x-published-ttl', 'PT1H')

    today = datetime.date.today()
    cutoff_future = today + datetime.timedelta(days=120)
    cutoff_past = today - datetime.timedelta(days=30)

    # 1. Ingest all Nifty 500 tickers
    universe = get_live_nifty_500_symbols()
    print(f"Loaded {len(universe)} symbols from the Nifty 500 index universe.")

    # 2. Parallel processing using thread pools
    total_events = 0
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_sym = {
            executor.submit(process_single_ticker, sym, today, cutoff_past, cutoff_future): sym
            for sym in universe
        }
        for future in as_completed(future_to_sym):
            res_events = future.result()
            for ev in res_events:
                cal.add_component(ev)
                total_events += 1

    # 3. Macro Events
    for m in MACRO_EVENTS_2026:
        ev_m = Event()
        ev_m.add('uid', str(uuid.uuid4()))
        ev_m.add('summary', m["summary"])
        ev_m.add('dtstart', m["date"])
        ev_m.add('dtend', m["date"] + datetime.timedelta(days=1))
        ev_m.add('description', m["desc"])
        ev_m.add('location', 'Global / Domestic Macro')
        cal.add_component(ev_m)
        total_events += 1

    # 4. Monthly F&O Expiry
    for m in range(4):
        t_month = (today.month + m - 1) % 12 + 1
        t_year = today.year + ((today.month + m - 1) // 12)
        last_d = datetime.date(t_year, 12, 31) if t_month == 12 else datetime.date(t_year, t_month + 1, 1) - datetime.timedelta(days=1)
        while last_d.weekday() != 3 or last_d in NSE_HOLIDAYS_2026:
            last_d -= datetime.timedelta(days=1)

        fo = Event()
        fo.add('uid', str(uuid.uuid4()))
        fo.add('summary', f"[F&O] NSE Monthly Derivatives Expiry ({last_d.strftime('%b %Y')})")
        fo.add('dtstart', last_d)
        fo.add('dtend', last_d + datetime.timedelta(days=1))
        fo.add('description', "NSE Index & Stock F&O contract expiry cutoff.")
        cal.add_component(fo)
        total_events += 1

    with open("market_calendar.ics", "wb") as f:
        f.write(cal.to_ical())
    print(f"Generated {total_events} total events across Nifty 500 into market_calendar.ics successfully.")

if __name__ == "__main__":
    build_calendar()
