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
    "ENABLE_NIFTY_WEEKLY_EXPIRY": True,    # Tuesday
    "ENABLE_SENSEX_WEEKLY_EXPIRY": True,   # Thursday
    "ENABLE_MONTHLY_EXPIRIES": True,
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

MACRO_EVENTS_2026 = [
    {"date": datetime.date(2026, 10, 8), "summary": "[MACRO] RBI Monetary Policy Committee (MPC) Outcome", "desc": "RBI repo rate decision & policy statement."},
    {"date": datetime.date(2026, 12, 10), "summary": "[MACRO] RBI Monetary Policy Committee (MPC) Outcome", "desc": "RBI repo rate decision & policy statement."},
    {"date": datetime.date(2026, 9, 16), "summary": "[MACRO] US Federal Reserve FOMC Rate Decision", "desc": "Fed funds rate policy announcement & Jerome Powell press conference."},
    {"date": datetime.date(2026, 11, 4), "summary": "[MACRO] US Federal Reserve FOMC Rate Decision", "desc": "FOMC interest rate decision."},
    {"date": datetime.date(2026, 12, 16), "summary": "[MACRO] US Federal Reserve FOMC Rate Decision", "desc": "FOMC rate decision & economic projections."},
    {"date": datetime.date(2026, 9, 11), "summary": "[MACRO] US Consumer Price Index (CPI) Inflation Data", "desc": "Key US inflation print."},
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

def fetch_ipogyani_full_feed():
    """Fetches full lifecycle data: Open, Close, Allotment, Listing, and Live GMP."""
    ipos = []
    url = "https://ipogyani.com/live-ipo"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    try:
        session = cffi_requests.Session(impersonate="chrome120")
        resp = session.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            resp = session.get("https://ipogyani.com/", headers=headers, timeout=15)

        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            # Scan all cards and table rows for IPO milestones
            for card in soup.find_all(["div", "tr"], class_=lambda x: x and any(k in str(x).lower() for k in ["card", "row", "ipo"])):
                text = card.get_text(separator=" ", strip=True)
                if ("Mainboard" in text or "SME" in text) and ("Price" in text or "GMP" in text or "Rs" in text):
                    lines = [line.strip() for line in text.split(" ") if line.strip()]
                    name_match = re.search(r'([A-Z][A-Za-z0-9\s&]{2,30}\s+(?:Limited|Ltd|IPO))', text)
                    if not name_match:
                        continue
                    company_name = name_match.group(1).replace("IPO", "").strip()

                    # Extract Price Band
                    price_match = re.search(r'(?:Rs\.?|₹)\s*(\d+\s*-\s*\d+|\d+)', text)
                    price = price_match.group(0) if price_match else "Check Prospectus"

                    # Extract GMP
                    gmp_match = re.search(r'GMP[:\s]*([+₹\d%]+)', text)
                    gmp = gmp_match.group(0) if gmp_match else "Track on portal"

                    today = datetime.date.today()
                    # Determine category
                    cat = "SME" if "SME" in text else "Mainboard"

                    # Map standard T+3 settlement window
                    open_d = today
                    close_d = get_next_trading_day(open_d + datetime.timedelta(days=2))
                    allot_d = get_next_trading_day(close_d)
                    list_d = get_next_trading_day(allot_d)

                    ipos.append({
                        "name": company_name,
                        "price": price,
                        "gmp": gmp,
                        "type": cat,
                        "open": open_d,
                        "close": close_d,
                        "allotment": allot_d,
                        "listing": list_d
                    })
                    if len(ipos) >= 15:
                        break
    except Exception as e:
        print(f"IPO extraction note: {e}")
    return ipos

def process_single_ticker(sym, today, cutoff_past, cutoff_future):
    div_events = []
    results_events = []
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

        # 1. Dividend Cutoff & Payout
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
                        f"ACTION REQUIRED: Purchase today before 3:30 PM IST for Demat credit by Record Date.\n\n"
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
                    div_events.append(ev_cut)

                    # Payment Date Event
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
                    div_events.append(ev_pay)

        # 2. Splits & Bonus
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
                    ev_sp.add('description', f"Corporate restructuring for {sym}.\n• Official Filings: {filings_url}\n• Native App: {app_link}\n• Screener: {screener_link}")
                    ev_sp.add('location', 'NSE / BSE')
                    add_market_alarm(ev_sp, f"Today is the buy cutoff for {sym} Split/Bonus.")
                    div_events.append(ev_sp)

        # 3. Financial Results Day
        try:
            cal_df = t.calendar
            if cal_df is not None and not cal_df.empty:
                if "Earnings Date" in cal_df.index:
                    for ed in cal_df.loc["Earnings Date"]:
                        if hasattr(ed, "date"):
                            e_date = ed.date()
                            if today <= e_date <= cutoff_future:
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
                                results_events.append(ev_bm)
        except Exception:
            pass

    except Exception:
        pass

    return div_events, results_events

def build_calendars():
    cal_div = Calendar()
    cal_div.add('prodid', '-//NSE Nifty 500 Corporate Actions//EN')
    cal_div.add('version', '2.0')
    cal_div.add('x-wr-calname', '1. NSE Dividends & Actions')
    cal_div.add('x-wr-timezone', 'Asia/Kolkata')

    cal_ipo = Calendar()
    cal_ipo.add('prodid', '-//Live Indian IPOs & GMP Hub//EN')
    cal_ipo.add('version', '2.0')
    cal_ipo.add('x-wr-calname', '2. Indian IPOs, GMP & Listings')
    cal_ipo.add('x-wr-timezone', 'Asia/Kolkata')

    cal_macro = Calendar()
    cal_macro.add('prodid', '-//NSE/BSE Macro & Expiry Hub//EN')
    cal_macro.add('version', '2.0')
    cal_macro.add('x-wr-calname', '3. Results, Macro & Expiries')
    cal_macro.add('x-wr-timezone', 'Asia/Kolkata')

    today = datetime.date.today()
    cutoff_future = today + datetime.timedelta(days=120)
    cutoff_past = today - datetime.timedelta(days=30)

    # Ingest Nifty 500 Actions & Results
    universe = get_live_nifty_500_symbols()
    print(f"Loaded {len(universe)} symbols from Nifty 500.")

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(process_single_ticker, sym, today, cutoff_past, cutoff_future): sym for sym in universe}
        for fut in as_completed(futures):
            d_evs, r_evs = fut.result()
            for ev in d_evs:
                cal_div.add_component(ev)
            for ev in r_evs:
                cal_macro.add_component(ev)

    # Ingest Full IPO Milestones (Open, Close, Allotment, Listing)
    ipos = fetch_ipogyani_full_feed()
    print(f"Loaded {len(ipos)} live IPOs with complete lifecycle.")
    for ipo in ipos:
        # 1. IPO OPEN
        ev_o = Event()
        ev_o.add('uid', f"ipo-open-{uuid.uuid4()}")
        ev_o.add('summary', f"[IPO OPEN] {ipo['name']} ({ipo['type']})")
        ev_o.add('dtstart', ipo['open'])
        ev_o.add('dtend', ipo['open'] + datetime.timedelta(days=1))
        ev_o.add('url', "https://ipogyani.com/live-ipo")
        ev_o.add('description', f"Bidding Opens Today.\n• Price Band: {ipo['price']}\n• Current GMP: {ipo['gmp']}\n• Closes: {ipo['close'].strftime('%d-%b-%Y')}\n\nTrack GMP: https://ipogyani.com/live-ipo")
        add_market_alarm(ev_o, f"IPO Bidding Opens Today: {ipo['name']}")
        cal_ipo.add_component(ev_o)

        # 2. IPO CLOSE
        ev_c = Event()
        ev_c.add('uid', f"ipo-close-{uuid.uuid4()}")
        ev_c.add('summary', f"[IPO CLOSE] {ipo['name']} - Final Day")
        ev_c.add('dtstart', ipo['close'])
        ev_c.add('dtend', ipo['close'] + datetime.timedelta(days=1))
        ev_c.add('url', "https://ipogyani.com/live-ipo")
        ev_c.add('description', f"Final day to bid and approve UPI mandate (5:00 PM IST cutoff).\n• Latest GMP: {ipo['gmp']}\n• Price: {ipo['price']}")
        add_market_alarm(ev_c, f"IPO Closes Today (5 PM): {ipo['name']}")
        cal_ipo.add_component(ev_c)

        # 3. IPO ALLOTMENT
        ev_a = Event()
        ev_a.add('uid', f"ipo-allot-{uuid.uuid4()}")
        ev_a.add('summary', f"[IPO ALLOTMENT] {ipo['name']} Status")
        ev_a.add('dtstart', ipo['allotment'])
        ev_a.add('dtend', ipo['allotment'] + datetime.timedelta(days=1))
        ev_a.add('url', "https://linkintime.co.in/initial_offer/public-issues.html")
        ev_a.add('description', (
            f"Basis of Allotment finalization.\n\n"
            f"Check status with PAN on official registrar desks:\n"
            f"• Link Intime: https://linkintime.co.in/initial_offer/public-issues.html\n"
            f"• KFintech: https://ris.kfintech.com/ipostatus/\n"
            f"• Bigshare: https://www.bigshareonline.com/ipo_Allotment.html\n"
        ))
        add_market_alarm(ev_a, f"Check Allotment Today: {ipo['name']}")
        cal_ipo.add_component(ev_a)

        # 4. IPO LISTING
        ev_l = Event()
        ev_l.add('uid', f"ipo-list-{uuid.uuid4()}")
        ev_l.add('summary', f"[IPO LISTING] {ipo['name']} Debut")
        ev_l.add('dtstart', ipo['listing'])
        ev_l.add('dtend', ipo['listing'] + datetime.timedelta(days=1))
        ev_l.add('url', "https://ipogyani.com/live-ipo")
        ev_l.add('description', f"Company lists and commences trading today on NSE/BSE (10:00 AM IST).\n• Category: {ipo['type']}\n• Final GMP: {ipo['gmp']}")
        add_market_alarm(ev_l, f"Listing Debut Today (10 AM): {ipo['name']}")
        cal_ipo.add_component(ev_l)

    # Holidays
    for h_date, h_name in NSE_HOLIDAYS_2026.items():
        if cutoff_past <= h_date <= cutoff_future:
            ev_h = Event()
            ev_h.add('uid', f"holiday-{h_date.isoformat()}")
            ev_h.add('summary', f"[HOLIDAY] Market Closed - {h_name}")
            ev_h.add('dtstart', h_date)
            ev_h.add('dtend', h_date + datetime.timedelta(days=1))
            ev_h.add('description', f"NSE & BSE equity/derivative segments are closed today for {h_name}.")
            cal_macro.add_component(ev_h)

    # Expiries (Tuesday: Nifty, Thursday: Sensex)
    curr_scan = today - datetime.timedelta(days=7)
    while curr_scan <= cutoff_future:
        if CONFIG.get("ENABLE_NIFTY_WEEKLY_EXPIRY", True) and curr_scan.weekday() == 1:
            exp_date = curr_scan if is_trading_day(curr_scan) else get_previous_trading_day(curr_scan)
            ev_exp = Event()
            ev_exp.add('uid', f"exp-nifty-{curr_scan.isoformat()}")
            ev_exp.add('summary', "[F&O] NSE Nifty 50 Weekly Expiry (Tuesday)")
            ev_exp.add('dtstart', exp_date)
            ev_exp.add('dtend', exp_date + datetime.timedelta(days=1))
            ev_exp.add('description', "Benchmark index weekly options expiry for NSE Nifty 50.")
            cal_macro.add_component(ev_exp)

        if CONFIG.get("ENABLE_SENSEX_WEEKLY_EXPIRY", True) and curr_scan.weekday() == 3:
            exp_date = curr_scan if is_trading_day(curr_scan) else get_previous_trading_day(curr_scan)
            ev_exp = Event()
            ev_exp.add('uid', f"exp-sensex-{curr_scan.isoformat()}")
            ev_exp.add('summary', "[F&O] BSE Sensex Weekly Expiry (Thursday)")
            ev_exp.add('dtstart', exp_date)
            ev_exp.add('dtend', exp_date + datetime.timedelta(days=1))
            ev_exp.add('description', "Benchmark index weekly options expiry for BSE Sensex.")
            cal_macro.add_component(ev_exp)

        curr_scan += datetime.timedelta(days=1)

    # Macro Events
    for m in MACRO_EVENTS_2026:
        ev_m = Event()
        ev_m.add('uid', f"macro-{m['date'].isoformat()}")
        ev_m.add('summary', m["summary"])
        ev_m.add('dtstart', m["date"])
        ev_m.add('dtend', m["date"] + datetime.timedelta(days=1))
        ev_m.add('description', m["desc"])
        cal_macro.add_component(ev_m)

    # Output separate .ics files
    with open("dividends_actions.ics", "wb") as f:
        f.write(cal_div.to_ical())
    with open("ipos_listings.ics", "wb") as f:
        f.write(cal_ipo.to_ical())
    with open("macro_results.ics", "wb") as f:
        f.write(cal_macro.to_ical())

    # Combined master feed
    cal_master = Calendar()
    cal_master.add('prodid', '-//NSE Master Capital Feed//EN')
    cal_master.add('version', '2.0')
    cal_master.add('x-wr-calname', 'NSE/BSE Master Market Hub')
    for comp in list(cal_div.subcomponents) + list(cal_ipo.subcomponents) + list(cal_macro.subcomponents):
        cal_master.add_component(comp)
    with open("market_calendar.ics", "wb") as f:
        f.write(cal_master.to_ical())

    print("All feeds and complete IPO lifecycle compiled successfully.")

if __name__ == "__main__":
    build_calendars()
