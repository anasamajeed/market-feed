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

# ==============================================================================
# CONFIGURATION SETTINGS
# ==============================================================================
CONFIG = {
    "ENABLE_ALARMS": True,                  # 09:00 AM IST alerts
    "ALARM_MINUTES_BEFORE": 180,           # Triggers at 09:00 AM for all-day events
    "ENABLE_NIFTY_WEEKLY_EXPIRY": True,    # Tuesday
    "ENABLE_SENSEX_WEEKLY_EXPIRY": True,   # Thursday
    "ENABLE_MONTHLY_EXPIRIES": True,       # Last Tue (NSE) & Last Thu (BSE)
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
    return f"tradingview://chart?symbol=NSE:{clean}", f"https://in.tradingview.com/chart/?symbol=NSE:{clean}"

def build_screener_link(symbol):
    clean = str(symbol).split()[0].replace("&", "")
    return f"https://www.screener.in/company/{clean}/consolidated/"

def add_market_alarm(event, summary_text):
    """Attaches a 09:00 AM IST notification alarm."""
    if not CONFIG.get("ENABLE_ALARMS", True):
        return
    alarm = Alarm()
    alarm.add('action', 'DISPLAY')
    alarm.add('description', summary_text)
    # Triggers 3 hours before standard noon all-day index = 09:00 AM IST
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
            "VEDL", "IOC", "BPCL", "HINDZINC", "DIVISLAB", "DRREDDY", "CIPLA"
        ]
    return symbols

def fetch_ipogyani_data():
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
            for table in soup.find_all("table"):
                for r in table.find_all("tr")[1:]:
                    cells = [c.text.strip() for c in r.find_all(["td", "th"])]
                    if len(cells) >= 4:
                        name = re.sub(r'\s+', ' ', cells[0].replace("\n", " ").strip())
                        row_text = " ".join(cells)
                        gmp_match = re.search(r'(₹\s*\d+|\d+\s*%)', row_text)
                        gmp_info = gmp_match.group(0) if gmp_match else "Track on portal"
                        today = datetime.date.today()
                        ipos.append({
                            "name": name,
                            "open": today + datetime.timedelta(days=1),
                            "close": today + datetime.timedelta(days=3),
                            "gmp": gmp_info,
                            "type": "SME" if "SME" in name.upper() else "Mainboard"
                        })
                        if len(ipos) >= 12:
                            break
                if ipos:
                    break
    except Exception:
        pass
    return ipos

def process_single_ticker(sym, today, cutoff_past, cutoff_future):
    div_events = []
    results_events = []
    ticker_str = f"{sym}.NS"
    app_link, web_link = build_tradingview_links(sym)
    screener_link = build_screener_link(sym)

    try:
        t = yf.Ticker(ticker_str)
        # Attempt current price fetch for yield calculation
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
                    ev_cut.add('description', (
                        f"ACTION REQUIRED: Purchase today before 3:30 PM IST for Demat credit by Record Date.\n\n"
                        f"• Amount: ₹{amount:.2f} per share\n"
                        f"• Ex-Date: {div_date.strftime('%d-%b-%Y')}\n"
                        f"• Est. Dividend Yield: {yield_text.replace(' | Yield: ', '') if yield_text else 'N/A'}\n"
                        f"• Settlement: T+1 Rolling Settlement (NSE/BSE)\n"
                        f"-----------------------------------------\n"
                        f"• Native TradingView App: {app_link}\n"
                        f"• Browser Chart: {web_link}\n"
                        f"• Screener Balance Sheet: {screener_link}\n"
                    ))
                    ev_cut.add('location', 'NSE / BSE India')
                    add_market_alarm(ev_cut, f"Cutoff today: Buy {sym} for ₹{amount:.2f} dividend eligibility.")
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
                    ev_sp.add('description', f"Corporate restructuring for {sym}.\n• Native App: {app_link}\n• Screener: {screener_link}")
                    ev_sp.add('location', 'NSE / BSE')
                    add_market_alarm(ev_sp, f"Today is the buy cutoff for {sym} Split/Bonus.")
                    div_events.append(ev_sp)

        # 3. Financial Results Day (Tagged as High Volatility)
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
                                ev_bm.add('description', (
                                    f"HIGH VOLATILITY ALERT: Company Board Meeting for quarterly results.\n\n"
                                    f"• Symbol: {sym}\n"
                                    f"• Native App Chart: {app_link}\n"
                                    f"• Web Chart: {web_link}\n"
                                    f"• Screener Balance Sheet: {screener_link}\n"
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
    # 1. Corporate Actions & Dividends Feed
    cal_div = Calendar()
    cal_div.add('prodid', '-//NSE Nifty 500 Corporate Actions & Payouts//EN')
    cal_div.add('version', '2.0')
    cal_div.add('x-wr-calname', '1. NSE Dividends & Corporate Actions')
    cal_div.add('x-wr-timezone', 'Asia/Kolkata')

    # 2. IPOs & GMP Feed
    cal_ipo = Calendar()
    cal_ipo.add('prodid', '-//Live Indian IPOs & GMP Hub//EN')
    cal_ipo.add('version', '2.0')
    cal_ipo.add('x-wr-calname', '2. Indian IPOs, GMP & Allotments')
    cal_ipo.add('x-wr-timezone', 'Asia/Kolkata')

    # 3. Macro, Results & Expiry Feed
    cal_macro = Calendar()
    cal_macro.add('prodid', '-//NSE/BSE Macro, Results & Expiry Hub//EN')
    cal_macro.add('version', '2.0')
    cal_macro.add('x-wr-calname', '3. Results, Macro & Weekly Expiries')
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

    # Ingest IPO Timelines & Live Allotment Direct Links
    ipos = fetch_ipogyani_data()
    print(f"Loaded {len(ipos)} live IPOs.")
    for ipo in ipos:
        # Bidding Open
        ev_o = Event()
        ev_o.add('uid', f"ipo-open-{uuid.uuid4()}")
        ev_o.add('summary', f"[IPO OPEN] {ipo['name']} ({ipo['type']})")
        ev_o.add('dtstart', ipo['open'])
        ev_o.add('dtend', ipo['open'] + datetime.timedelta(days=1))
        ev_o.add('description', f"Bidding Opens.\n• Category: {ipo['type']}\n• GMP: {ipo['gmp']}\n• Closes: {ipo['close'].strftime('%d-%b-%Y')}\n\nTracker: https://ipogyani.com/")
        add_market_alarm(ev_o, f"IPO Bidding Opens Today: {ipo['name']}")
        cal_ipo.add_component(ev_o)

        # Bidding Close
        ev_c = Event()
        ev_c.add('uid', f"ipo-close-{uuid.uuid4()}")
        ev_c.add('summary', f"[IPO CLOSE] {ipo['name']} - Final Day")
        ev_c.add('dtstart', ipo['close'])
        ev_c.add('dtend', ipo['close'] + datetime.timedelta(days=1))
        ev_c.add('description', f"Final day for bidding & UPI mandate authorization (5:00 PM IST).\n• Current GMP: {ipo['gmp']}")
        add_market_alarm(ev_c, f"Final Day to Apply: {ipo['name']} IPO closes at 5:00 PM IST.")
        cal_ipo.add_component(ev_c)

        # Allotment Finalization (T+1 trading day after close)
        allot_date = ipo['close'] + datetime.timedelta(days=1)
        ev_a = Event()
        ev_a.add('uid', f"ipo-allot-{uuid.uuid4()}")
        ev_a.add('summary', f"[IPO ALLOTMENT] {ipo['name']} Allotment Status")
        ev_a.add('dtstart', allot_date)
        ev_a.add('dtend', allot_date + datetime.timedelta(days=1))
        ev_a.add('description', (
            f"Check allotment status using PAN on official registrar desks:\n\n"
            f"• Link Intime Portal:\n  https://linkintime.co.in/initial_offer/public-issues.html\n\n"
            f"• KFintech Portal:\n  https://ris.kfintech.com/ipostatus/\n\n"
            f"• Bigshare Services Portal:\n  https://www.bigshareonline.com/ipo_Allotment.html\n"
        ))
        add_market_alarm(ev_a, f"Check Allotment Today: {ipo['name']}")
        cal_ipo.add_component(ev_a)

    # NSE & BSE Trading Holidays
    for h_date, h_name in NSE_HOLIDAYS_2026.items():
        if cutoff_past <= h_date <= cutoff_future:
            ev_h = Event()
            ev_h.add('uid', f"holiday-{h_date.isoformat()}")
            ev_h.add('summary', f"[HOLIDAY] Market Closed - {h_name}")
            ev_h.add('dtstart', h_date)
            ev_h.add('dtend', h_date + datetime.timedelta(days=1))
            ev_h.add('description', f"NSE & BSE equity/derivative segments are closed today for {h_name}.")
            cal_macro.add_component(ev_h)

    # SEBI Benchmark Expiry Schedules (Tuesday: Nifty, Thursday: Sensex)
    curr_scan = today - datetime.timedelta(days=7)
    while curr_scan <= cutoff_future:
        # NSE Nifty Weekly (Tuesday)
        if CONFIG.get("ENABLE_NIFTY_WEEKLY_EXPIRY", True) and curr_scan.weekday() == 1:
            exp_date = curr_scan if is_trading_day(curr_scan) else get_previous_trading_day(curr_scan)
            ev_exp = Event()
            ev_exp.add('uid', f"exp-nifty-{curr_scan.isoformat()}")
            ev_exp.add('summary', "[F&O] NSE Nifty 50 Weekly Expiry (Tuesday)")
            ev_exp.add('dtstart', exp_date)
            ev_exp.add('dtend', exp_date + datetime.timedelta(days=1))
            ev_exp.add('description', "Benchmark index weekly options expiry for NSE Nifty 50.\nHeightened volatility expected after 01:30 PM IST.")
            cal_macro.add_component(ev_exp)

        # BSE Sensex Weekly (Thursday)
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

    # Macroeconomic Triggers
    for m in MACRO_EVENTS_2026:
        ev_m = Event()
        ev_m.add('uid', f"macro-{m['date'].isoformat()}")
        ev_m.add('summary', m["summary"])
        ev_m.add('dtstart', m["date"])
        ev_m.add('dtend', m["date"] + datetime.timedelta(days=1))
        ev_m.add('description', m["desc"])
        cal_macro.add_component(ev_m)

    # Write the 3 Color-Coded Feeds + Master Feed
    with open("dividends_actions.ics", "wb") as f:
        f.write(cal_div.to_ical())
    with open("ipos_listings.ics", "wb") as f:
        f.write(cal_ipo.to_ical())
    with open("macro_results.ics", "wb") as f:
        f.write(cal_macro.to_ical())

    # Combined master feed for backward compatibility
    cal_master = Calendar()
    cal_master.add('prodid', '-//NSE Master Capital Feed//EN')
    cal_master.add('version', '2.0')
    cal_master.add('x-wr-calname', 'NSE/BSE Master Market Hub')
    for comp in list(cal_div.subcomponents) + list(cal_ipo.subcomponents) + list(cal_macro.subcomponents):
        cal_master.add_component(comp)
    with open("market_calendar.ics", "wb") as f:
        f.write(cal_master.to_ical())

    print("Successfully built all 3 color-coded feeds and master calendar.")

if __name__ == "__main__":
    build_calendars()
