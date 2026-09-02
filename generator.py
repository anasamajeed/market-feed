import datetime
import uuid
import requests
from icalendar import Calendar, Event

# Market Holiday List 2026 for T+1 Demat Settlement
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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.bseindia.com/",
    "Origin": "https://www.bseindia.com"
}

def is_trading_day(d):
    return d.weekday() < 5 and d not in NSE_HOLIDAYS_2026

def get_previous_trading_day(d):
    curr = d - datetime.timedelta(days=1)
    while not is_trading_day(curr):
        curr -= datetime.timedelta(days=1)
    return curr

def build_tradingview_link(symbol):
    clean_sym = symbol.replace("&", "_").replace("-", "_").split()[0]
    return f"https://in.tradingview.com/chart/?symbol=NSE:{clean_sym}"

def build_screener_link(symbol):
    clean_sym = symbol.split()[0]
    return f"https://www.screener.in/company/{clean_sym}/consolidated/"

def fetch_bse_corporate_actions():
    """Fetches upcoming dividends and corporate actions from BSE India."""
    url = "https://api.bseindia.com/BseIndiaAPI/api/DefaultData/w?page=1"
    actions = []
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        # Seed session cookies
        session.get("https://www.bseindia.com", timeout=8)
        resp = session.get(url, timeout=12)
        if resp.status_code == 200:
            data = resp.json()
            for row in data:
                purpose = row.get("Purpose", "")
                rec_date_str = row.get("Record_Date")
                sec_name = row.get("Security_Name", "").strip()
                scrip_code = row.get("Security_Code", "")

                if not rec_date_str or rec_date_str == "-":
                    continue

                try:
                    rec_date = datetime.datetime.strptime(rec_date_str, "%d/%m/%Y").date()
                except ValueError:
                    continue

                actions.append({
                    "symbol": sec_name,
                    "purpose": purpose,
                    "record_date": rec_date,
                    "scrip_code": scrip_code,
                    "is_dividend": "DIVIDEND" in purpose.upper()
                })
    except Exception as e:
        print(f"BSE Action fetch error: {e}")
    return actions

def fetch_ipo_feed():
    """Aggregates IPO timeline data from market feeds."""
    ipos = []
    # Primary API endpoint for live/upcoming IPOs
    url = "https://api.bseindia.com/BseIndiaAPI/api/GetIPOBidDetails/w?status=U"
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        resp = session.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("Table", []):
                company = item.get("Issuer_Company", "")
                open_str = item.get("Open_Date")
                close_str = item.get("Close_Date")
                price_band = item.get("Price_Band", "N/A")
                if open_str and close_str:
                    try:
                        open_dt = datetime.datetime.strptime(open_str, "%d-%b-%Y").date()
                        close_dt = datetime.datetime.strptime(close_str, "%d-%b-%Y").date()
                        ipos.append({
                            "company": company,
                            "open": open_dt,
                            "close": close_dt,
                            "price_band": price_band,
                            "issue_type": item.get("Issue_Type", "Mainboard/SME")
                        })
                    except Exception:
                        continue
    except Exception as e:
        print(f"IPO fetch error: {e}")
    return ipos

def build_calendar():
    cal = Calendar()
    cal.add('prodid', '-//Live Indian Capital Markets//EN')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', 'NSE/BSE Corporate Actions, IPOs & Macro')
    cal.add('x-wr-timezone', 'Asia/Kolkata')
    cal.add('x-published-ttl', 'PT1H')

    # 1. Add Corporate Actions & Dividends
    actions = fetch_bse_corporate_actions()
    for act in actions:
        rec_date = act["record_date"]
        must_buy_date = get_previous_trading_day(rec_date)
        sym = act["symbol"]
        tv_link = build_tradingview_link(sym)
        screener_link = build_screener_link(sym)
        filing_link = f"https://www.bseindia.com/stock-share-price/x/y/{act['scrip_code']}/corporate-actions/"

        tag = "[DIVIDEND]" if act["is_dividend"] else "[CORP ACTION]"
        
        event = Event()
        event.add('uid', str(uuid.uuid4()))
        event.add('summary', f"{tag} {sym} - Last Day to Buy (T+1 Cutoff)")
        event.add('dtstart', must_buy_date)
        event.add('dtend', must_buy_date + datetime.timedelta(days=1))
        
        desc = (
            f"ACTION REQUIRED: Purchase today before 3:30 PM IST to get Demat credit by Record Date.\n\n"
            f"• Announcement Details: {act['purpose']}\n"
            f"• Record Date: {rec_date.strftime('%d-%b-%Y')}\n"
            f"• Exchange: NSE / BSE\n"
            f"-----------------------------------------\n"
            f"• TradingView Daily Chart:\n  {tv_link}\n\n"
            f"• Financial Statements & Fundamentals:\n  {screener_link}\n\n"
            f"• Official BSE Regulatory Announcement:\n  {filing_link}\n"
        )
        event.add('description', desc)
        event.add('location', 'NSE/BSE India')
        cal.add_component(event)

    # 2. Add IPO Timelines
    ipos = fetch_ipo_feed()
    for ipo in ipos:
        # Event for IPO Open Day
        ev_open = Event()
        ev_open.add('uid', str(uuid.uuid4()))
        ev_open.add('summary', f"[IPO OPEN] {ipo['company']} ({ipo['issue_type']})")
        ev_open.add('dtstart', ipo['open'])
        ev_open.add('dtend', ipo['open'] + datetime.timedelta(days=1))
        ev_open.add('description', (
            f"Company: {ipo['company']}\n"
            f"Price Band: ₹{ipo['price_band']}\n"
            f"Status: Applications Open\n"
            f"Bidding Closes: {ipo['close'].strftime('%d-%b-%Y')}\n\n"
            f"• Chittorgarh / InvestorGain GMP Tracker:\n  https://www.chittorgarh.com/ipo/ipo_dashboard.asp"
        ))
        cal.add_component(ev_open)

        # Event for IPO Closing Day
        ev_close = Event()
        ev_close.add('uid', str(uuid.uuid4()))
        ev_close.add('summary', f"[IPO CLOSE] {ipo['company']} - Final Bidding Day")
        ev_close.add('dtstart', ipo['close'])
        ev_close.add('dtend', ipo['close'] + datetime.timedelta(days=1))
        ev_close.add('description', (
            f"Last day for UPI mandate authorization (cut-off: 5:00 PM IST).\n"
            f"Company: {ipo['company']}\n"
            f"Price Band: ₹{ipo['price_band']}\n\n"
            f"• Check Live Allotment (Link Intime / KFintech):\n"
            f"  https://linkintime.co.in/initial_offer/public-issues.html\n"
            f"  https://ris.kfintech.com/ipostatus/"
        ))
        cal.add_component(ev_close)

    # 3. Monthly F&O Expiry Triggers (Last Thursday of the month)
    today = datetime.date.today()
    for m_offset in range(3):
        # Scan upcoming 3 months for last Thursday
        target_month = (today.month + m_offset - 1) % 12 + 1
        target_year = today.year + ((today.month + m_offset - 1) // 12)
        # Start at end of month
        if target_month == 12:
            last_day = datetime.date(target_year, 12, 31)
        else:
            last_day = datetime.date(target_year, target_month + 1, 1) - datetime.timedelta(days=1)
        
        # Walk back to finding the last Thursday (weekday 3)
        while last_day.weekday() != 3 or last_day in NSE_HOLIDAYS_2026:
            last_day -= datetime.timedelta(days=1)

        fo_event = Event()
        fo_event.add('uid', str(uuid.uuid4()))
        fo_event.add('summary', f"[MARKET] Monthly NSE F&O Expiry ({last_day.strftime('%B %Y')})")
        fo_event.add('dtstart', last_day)
        fo_event.add('dtend', last_day + datetime.timedelta(days=1))
        fo_event.add('description', "NSE Nifty/BankNifty Monthly Derivative Contracts Expiry.\nExpect heightened volatility.")
        cal.add_component(fo_event)

    # Save to disk
    with open("market_calendar.ics", "wb") as f:
        f.write(cal.to_ical())
    print("market_calendar.ics successfully built.")

if __name__ == "__main__":
    build_calendar()
