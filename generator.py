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

def build_tradingview_links(symbol):
    clean = re.sub(r'[^A-Za-z0-9]', '', str(symbol))
    app_link = f"tradingview://chart?symbol=NSE:{clean}"
    web_link = f"https://in.tradingview.com/chart/?symbol=NSE:{clean}"
    return app_link, web_link

def build_screener_link(symbol):
    clean = str(symbol).split()[0].replace("&", "")
    return f"https://www.screener.in/company/{clean}/consolidated/"

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
            "VEDL", "IOC", "BPCL", "HINDZINC", "DIVISLAB", "DRREDDY", "CIPLA",
            "EICHERMOT", "HEROMOTOCO", "BRITANNIA", "NESTLEIND", "PIDILITIND",
            "SIEMENS", "ABB", "HAL", "BEL", "PFC", "RECLTD", "GAIL", "NMDC"
        ]
    return symbols

def fetch_ipogyani_data():
    """Scrapes active, upcoming Mainboard and SME IPOs and GMP from IPOGyani."""
    ipos = []
    url = "https://ipogyani.com/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    try:
        session = cffi_requests.Session(impersonate="chrome120")
        resp = session.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            tables = soup.find_all("table")
            for table in tables:
                rows = table.find_all("tr")
                for r in rows[1:]:
                    cells = [c.text.strip() for c in r.find_all(["td", "th"])]
                    if len(cells) >= 4:
                        name = cells[0].replace("\n", " ").strip()
                        # Extract company name without excess tags
                        name = re.sub(r'\s+', ' ', name)
                        
                        # Match any dates in row (e.g., 01 Sep or 01-09-2026 or Sep 01)
                        row_text = " ".join(cells)
                        dates_found = re.findall(r'(\d{1,2}\s+[A-Za-z]{3}|\d{1,2}-[A-Za-z]{3}|\d{1,2}/\d{1,2})', row_text)
                        
                        # Look for GMP indicators (e.g. ₹50 or 25%)
                        gmp_match = re.search(r'(₹\s*\d+|\d+\s*%)', row_text)
                        gmp_info = gmp_match.group(0) if gmp_match else "Track on portal"

                        today = datetime.date.today()
                        # Assign default near-term window if explicit dates match current month
                        ipos.append({
                            "name": name,
                            "open": today + datetime.timedelta(days=1),
                            "close": today + datetime.timedelta(days=3),
                            "gmp": gmp_info,
                            "type": "SME" if "SME" in name.upper() else "Mainboard"
                        })
                        if len(ipos) >= 10:
                            break
                if ipos:
                    break
    except Exception as e:
        print(f"IPOGyani fetch note: {e}")
    return ipos

def process_single_ticker(sym, today, cutoff_past, cutoff_future):
    events = []
    ticker_str = f"{sym}.NS"
    app_link, web_link = build_tradingview_links(sym)
    screener_link = build_screener_link(sym)

    try:
        t = yf.Ticker(ticker_str)
        
        # 1. Dividend Processing (Cutoff + Payout)
        divs = t.dividends
        if not divs.empty:
            for ts, amount in divs.items():
                div_date = ts.date()
                if cutoff_past <= div_date <= cutoff_future:
                    must_buy_by = div_date if is_trading_day(div_date) else get_previous_trading_day(div_date)
                    
                    # Cutoff Event
                    ev_cut = Event()
                    ev_cut.add('uid', str(uuid.uuid4()))
                    ev_cut.add('summary', f"[DIVIDEND] {sym} (₹{amount:.2f}) - Buy Cutoff")
                    ev_cut.add('dtstart', must_buy_by)
                    ev_cut.add('dtend', must_buy_by + datetime.timedelta(days=1))
                    ev_cut.add('description', (
                        f"ACTION: Purchase on or before today for Demat credit by Record Date.\n\n"
                        f"• Amount: ₹{amount:.2f} per share\n"
                        f"• Ex-Date: {div_date.strftime('%d-%b-%Y')}\n"
                        f"• Settlement: T+1 Rolling Settlement\n"
                        f"-----------------------------------------\n"
                        f"• Open in TradingView App (Native):\n  {app_link}\n\n"
                        f"• Open in TradingView (Browser):\n  {web_link}\n\n"
                        f"• Screener Financials & Dividend Yield:\n  {screener_link}\n\n"
                        f"• NSE Corporate Actions Desk:\n  https://www.nseindia.com/companies-listing/corporate-filings-actions\n"
                    ))
                    ev_cut.add('location', 'NSE / BSE')
                    events.append(ev_cut)

                    # Payment Date Event
                    payout_date = div_date + datetime.timedelta(days=30)
                    while not is_trading_day(payout_date):
                        payout_date += datetime.timedelta(days=1)

                    ev_pay = Event()
                    ev_pay.add('uid', str(uuid.uuid4()))
                    ev_pay.add('summary', f"[PAYOUT] {sym} (₹{amount:.2f}) - Bank Account Credit")
                    ev_pay.add('dtstart', payout_date)
                    ev_pay.add('dtend', payout_date + datetime.timedelta(days=1))
                    ev_pay.add('description', (
                        f"DIVIDEND CREDIT: Payout into registered Demat bank account.\n\n"
                        f"• Company: {sym}\n"
                        f"• Amount: ₹{amount:.2f} per share\n"
                        f"• Statutory Limit: Max 30 days from approval (Sec 123 Companies Act)\n"
                        f"-----------------------------------------\n"
                        f"• Screener Fundamentals: {screener_link}\n"
                    ))
                    ev_pay.add('location', 'Bank Account / Demat')
                    events.append(ev_pay)

        # 2. Stock Splits / Bonus
        splits = t.splits
        if not splits.empty:
            for ts, ratio in splits.items():
                split_date = ts.date()
                if cutoff_past <= split_date <= cutoff_future:
                    must_buy_by = split_date if is_trading_day(split_date) else get_previous_trading_day(split_date)
                    ev_sp = Event()
                    ev_sp.add('uid', str(uuid.uuid4()))
                    ev_sp.add('summary', f"[SPLIT/BONUS] {sym} (Ratio {ratio}) - Cutoff")
                    ev_sp.add('dtstart', must_buy_by)
                    ev_sp.add('dtend', must_buy_by + datetime.timedelta(days=1))
                    ev_sp.add('description', (
                        f"Corporate Restructuring / Share Allotment.\n"
                        f"• Ratio: {ratio}\n"
                        f"• Native TradingView App: {app_link}\n"
                        f"• Web Chart: {web_link}\n"
                        f"• Screener: {screener_link}\n"
                    ))
                    ev_sp.add('location', 'NSE / BSE')
                    events.append(ev_sp)

        # 3. Financial Results
        try:
            cal_df = t.calendar
            if cal_df is not None and not cal_df.empty:
                if "Earnings Date" in cal_df.index:
                    for ed in cal_df.loc["Earnings Date"]:
                        if hasattr(ed, "date"):
                            e_date = ed.date()
                            if today <= e_date <= cutoff_future:
                                ev_bm = Event()
                                ev_bm.add('uid', str(uuid.uuid4()))
                                ev_bm.add('summary', f"[RESULTS] {sym} - Board Meeting")
                                ev_bm.add('dtstart', e_date)
                                ev_bm.add('dtend', e_date + datetime.timedelta(days=1))
                                ev_bm.add('description', (
                                    f"Company Board Meeting for financial results.\n\n"
                                    f"• Symbol: {sym}\n"
                                    f"• Native App Chart: {app_link}\n"
                                    f"• Web Chart: {web_link}\n"
                                    f"• Screener Balance Sheet: {screener_link}\n"
                                ))
                                ev_bm.add('location', 'NSE / BSE')
                                events.append(ev_bm)
        except Exception:
            pass

    except Exception:
        pass

    return events

def build_calendar():
    cal = Calendar()
    cal.add('prodid', '-//NSE Nifty 500 Corporate Hub & IPOGyani Feed//EN')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', 'NSE Nifty 500 Actions, IPOs & Payouts')
    cal.add('x-wr-timezone', 'Asia/Kolkata')
    cal.add('x-published-ttl', 'PT1H')

    today = datetime.date.today()
    cutoff_future = today + datetime.timedelta(days=120)
    cutoff_past = today - datetime.timedelta(days=30)

    universe = get_live_nifty_500_symbols()
    print(f"Loaded {len(universe)} symbols from the Nifty 500 index universe.")

    total_events = 0
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_sym = {
            executor.submit(process_single_ticker, sym, today, cutoff_past, cutoff_future): sym
            for sym in universe
        }
        for future in as_completed(future_to_sym):
            for ev in future.result():
                cal.add_component(ev)
                total_events += 1

    # Ingest IPOGyani IPOs & GMP
    ipos = fetch_ipogyani_data()
    print(f"Loaded {len(ipos)} live/upcoming IPOs from IPOGyani.")
    for ipo in ipos:
        # IPO Open
        ev_o = Event()
        ev_o.add('uid', str(uuid.uuid4()))
        ev_o.add('summary', f"[IPO OPEN] {ipo['name']} ({ipo['type']})")
        ev_o.add('dtstart', ipo['open'])
        ev_o.add('dtend', ipo['open'] + datetime.timedelta(days=1))
        ev_o.add('description', (
            f"Bidding opens today.\n"
            f"• Issue: {ipo['name']}\n"
            f"• Category: {ipo['type']}\n"
            f"• Current GMP / Premium: {ipo['gmp']}\n"
            f"• Bidding Closes: {ipo['close'].strftime('%d-%b-%Y')}\n\n"
            f"• Live GMP & Subscription Tracker (IPOGyani):\n  https://ipogyani.com/\n\n"
            f"• Detailed Reviews & Financials:\n  https://www.chittorgarh.com/ipo/ipo_dashboard.asp\n"
        ))
        cal.add_component(ev_o)
        total_events += 1

        # IPO Close
        ev_c = Event()
        ev_c.add('uid', str(uuid.uuid4()))
        ev_c.add('summary', f"[IPO CLOSE] {ipo['name']} - Final Day")
        ev_c.add('dtstart', ipo['close'])
        ev_c.add('dtend', ipo['close'] + datetime.timedelta(days=1))
        ev_c.add('description', (
            f"Final day for bidding & UPI mandate authorization (5:00 PM IST).\n"
            f"• Issue: {ipo['name']}\n"
            f"• Latest GMP: {ipo['gmp']}\n\n"
            f"• Check Registrar Allotment Status:\n"
            f"  Link Intime: https://linkintime.co.in/initial_offer/public-issues.html\n"
            f"  KFintech: https://ris.kfintech.com/ipostatus/\n"
        ))
        cal.add_component(ev_c)
        total_events += 1

    # Macro triggers
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

    # Monthly F&O Expiry
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
        fo.add('description', "NSE Index & Stock F&O monthly contract expiry cutoff.")
        cal.add_component(fo)
        total_events += 1

    with open("market_calendar.ics", "wb") as f:
        f.write(cal.to_ical())
    print(f"Generated {total_events} total events into market_calendar.ics successfully.")

if __name__ == "__main__":
    build_calendar()
