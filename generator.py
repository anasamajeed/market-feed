import datetime
import uuid
import re
from curl_cffi import requests
from icalendar import Calendar, Event

# 2026 NSE/BSE Trading Holidays for T+1 Demat Settlement
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

def is_trading_day(d):
    return d.weekday() < 5 and d not in NSE_HOLIDAYS_2026

def get_previous_trading_day(d):
    curr = d - datetime.timedelta(days=1)
    while not is_trading_day(curr):
        curr -= datetime.timedelta(days=1)
    return curr

def build_tradingview_link(symbol):
    clean = re.sub(r'[^A-Za-z0-9]', '', symbol)
    return f"https://in.tradingview.com/chart/?symbol=NSE:{clean}"

def build_screener_link(symbol):
    clean = symbol.split()[0]
    return f"https://www.screener.in/company/{clean}/consolidated/"

def fetch_bse_corporate_actions():
    """Fetches real-time live corporate actions directly from BSE India."""
    url = "https://api.bseindia.com/BseIndiaAPI/api/DefaultData/w?page=1"
    actions = []
    try:
        session = requests.Session(impersonate="chrome120")
        # Handshake headers to satisfy BSE server
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.bseindia.com/",
            "Origin": "https://www.bseindia.com"
        }
        resp = session.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            for row in data:
                purpose = row.get("Purpose", "")
                rec_date_str = row.get("Record_Date")
                sec_name = row.get("Security_Name", "").strip()
                scrip_code = row.get("Security_Code", "")

                if not rec_date_str or rec_date_str == "-" or "/" not in rec_date_str:
                    continue

                try:
                    rec_date = datetime.datetime.strptime(rec_date_str, "%d/%m/%Y").date()
                except ValueError:
                    continue

                actions.append({
                    "symbol": sec_name,
                    "scrip_code": scrip_code,
                    "purpose": purpose,
                    "record_date": rec_date,
                    "is_dividend": "DIVIDEND" in purpose.upper(),
                    "is_agm": "AGM" in purpose.upper() or "ANNUAL GENERAL MEETING" in purpose.upper()
                })
    except Exception as e:
        print(f"Error fetching BSE data: {e}")
    return actions

def fetch_bse_announcements():
    """Fetches company board meetings, dividend notices, and PDF links from BSE."""
    url = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryData/w?strCat=Corporate+Action&strPrevDate=&strScrip=&strSearch=P&strToDate=&strType=C"
    filings = []
    try:
        session = requests.Session(impersonate="chrome120")
        resp = session.get(url, headers={"Referer": "https://www.bseindia.com/"}, timeout=15)
        if resp.status_code == 200:
            items = resp.json().get("Table", [])
            for item in items:
                pdf_file = item.get("ATTACHMENTNAME", "")
                pdf_url = f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{pdf_file}" if pdf_file else "N/A"
                filings.append({
                    "symbol": item.get("SLONGNAME", ""),
                    "headline": item.get("NEWSSUB", ""),
                    "date": item.get("NEWS_DT", "")[:10],
                    "pdf_url": pdf_url
                })
    except Exception as e:
        print(f"Error fetching BSE announcements: {e}")
    return filings

def fetch_upcoming_ipos():
    """Fetches upcoming Mainboard and SME IPO timelines."""
    ipos = []
    url = "https://api.bseindia.com/BseIndiaAPI/api/GetIPOBidDetails/w?status=U"
    try:
        session = requests.Session(impersonate="chrome120")
        resp = session.get(url, headers={"Referer": "https://www.bseindia.com/"}, timeout=15)
        if resp.status_code == 200:
            for item in resp.json().get("Table", []):
                name = item.get("Issuer_Company", "").strip()
                open_str = item.get("Open_Date")
                close_str = item.get("Close_Date")
                price_band = item.get("Price_Band", "N/A")
                if open_str and close_str:
                    try:
                        open_d = datetime.datetime.strptime(open_str, "%d-%b-%Y").date()
                        close_d = datetime.datetime.strptime(close_str, "%d-%b-%Y").date()
                        ipos.append({
                            "name": name,
                            "open": open_d,
                            "close": close_d,
                            "price": price_band,
                            "type": item.get("Issue_Type", "Equity")
                        })
                    except Exception:
                        continue
    except Exception as e:
        print(f"Error fetching IPO feed: {e}")
    return ipos

def build_calendar():
    cal = Calendar()
    cal.add('prodid', '-//NSE-BSE Corporate & IPO Live Hub//EN')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', 'NSE/BSE Corporate Hub & Live IPOs')
    cal.add('x-wr-timezone', 'Asia/Kolkata')
    cal.add('x-published-ttl', 'PT1H')

    # 1. Process Live Corporate Actions (Dividends, Splits, AGM)
    actions = fetch_bse_corporate_actions()
    print(f"Found {len(actions)} live corporate actions from exchange.")

    for act in actions:
        rec_date = act["record_date"]
        must_buy_by = get_previous_trading_day(rec_date)
        sym = act["symbol"]
        scrip = act["scrip_code"]
        tv_link = build_tradingview_link(sym)
        scr_link = build_screener_link(sym)
        bse_link = f"https://www.bseindia.com/stock-share-price/x/y/{scrip}/corporate-actions/"
        nse_link = f"https://www.nseindia.com/companies-listing/corporate-filings-actions"
        bse_filings_desk = f"https://www.bseindia.com/stock-share-price/x/y/{scrip}/corp-announcements/"

        tag = "[DIVIDEND]" if act["is_dividend"] else ("[AGM]" if act["is_agm"] else "[CORP ACTION]")
        
        event = Event()
        event.add('uid', str(uuid.uuid4()))
        event.add('summary', f"{tag} {sym} - Buy Cut-off (T+1)")
        event.add('dtstart', must_buy_by)
        event.add('dtend', must_buy_by + datetime.timedelta(days=1))
        
        desc = (
            f"ACTION REQUIRED: Purchase today before 3:30 PM IST to obtain Demat ownership by Record Date.\n\n"
            f"• Purpose: {act['purpose']}\n"
            f"• Record Date: {rec_date.strftime('%d-%b-%Y')}\n"
            f"• Settlement: T+1 Rolling Settlement (NSE/BSE)\n"
            f"-----------------------------------------\n"
            f"• TradingView Daily Chart:\n  {tv_link}\n\n"
            f"• Financial Statements & Balance Sheet:\n  {scr_link}\n\n"
            f"• BSE Official Filings & Meeting PDFs:\n  {bse_filings_desk}\n\n"
            f"• BSE Corporate Action Detail:\n  {bse_link}\n\n"
            f"• NSE Corporate Filings Portal:\n  {nse_link}\n"
        )
        event.add('description', desc)
        event.add('location', 'NSE / BSE')
        cal.add_component(event)

    # 2. Process IPO Schedules & GMP trackers
    ipos = fetch_upcoming_ipos()
    print(f"Found {len(ipos)} upcoming/live IPOs.")
    for ipo in ipos:
        # Bidding Open Date
        ev_open = Event()
        ev_open.add('uid', str(uuid.uuid4()))
        ev_open.add('summary', f"[IPO OPEN] {ipo['name']} ({ipo['type']})")
        ev_open.add('dtstart', ipo['open'])
        ev_open.add('dtend', ipo['open'] + datetime.timedelta(days=1))
        ev_open.add('description', (
            f"Issue: {ipo['name']}\n"
            f"Price Band: ₹{ipo['price']}\n"
            f"Bidding Closes: {ipo['close'].strftime('%d-%b-%Y')}\n\n"
            f"• Live GMP Tracking & Analysis (InvestorGain/Chittorgarh):\n"
            f"  https://www.investorgain.com/report/live-ipo-gmp/331/\n"
            f"  https://www.chittorgarh.com/ipo/ipo_dashboard.asp\n"
        ))
        cal.add_component(ev_open)

        # Bidding Close Date
        ev_close = Event()
        ev_close.add('uid', str(uuid.uuid4()))
        ev_close.add('summary', f"[IPO CLOSE] {ipo['name']} - Final Day")
        ev_close.add('dtstart', ipo['close'])
        ev_close.add('dtend', ipo['close'] + datetime.timedelta(days=1))
        ev_close.add('description', (
            f"Final day for application and UPI mandate authorization (5:00 PM IST).\n"
            f"Issue: {ipo['name']}\n\n"
            f"• Registrar Allotment Status Links:\n"
            f"  Link Intime: https://linkintime.co.in/initial_offer/public-issues.html\n"
            f"  KFintech: https://ris.kfintech.com/ipostatus/\n"
        ))
        cal.add_component(ev_close)

    # 3. Monthly F&O Expiry Days
    today = datetime.date.today()
    for m in range(3):
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
        fo.add('description', "NSE Index & Stock Options/Futures Monthly Expiry Cutoff.")
        cal.add_component(fo)

    with open("market_calendar.ics", "wb") as f:
        f.write(cal.to_ical())
    print("Calendar generation completed.")

if __name__ == "__main__":
    build_calendar()
