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

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

def is_trading_day(d):
    return d.weekday() < 5 and d not in NSE_HOLIDAYS_2026

def get_previous_trading_day(d):
    curr = d - datetime.timedelta(days=1)
    while not is_trading_day(curr):
        curr -= datetime.timedelta(days=1)
    return curr

def build_tradingview_link(symbol):
    clean = re.sub(r'[^A-Za-z0-9]', '', str(symbol))
    return f"https://in.tradingview.com/chart/?symbol=NSE:{clean}"

def build_screener_link(symbol):
    clean = str(symbol).split()[0].replace("&", "")
    return f"https://www.screener.in/company/{clean}/consolidated/"

def fetch_bse_corporate_actions():
    """Fetches real-time live corporate actions using official BSE date window parameters."""
    today = datetime.date.today()
    fdate = (today - datetime.timedelta(days=7)).strftime("%Y%m%d")
    tdate = (today + datetime.timedelta(days=60)).strftime("%Y%m%d")
    
    url = (
        f"https://api.bseindia.com/BseIndiaAPI/api/DefaultData/w?"
        f"Fdate={fdate}&Purposecode=&TDate={tdate}&ddlcategorys=E&ddlindustrys=&scripcode=&segment=0&strSearch=S"
    )
    
    actions = []
    try:
        session = requests.Session(impersonate="chrome120")
        headers = dict(BROWSER_HEADERS)
        headers["Referer"] = "https://www.bseindia.com/"
        headers["Origin"] = "https://www.bseindia.com"
        
        # Initialize cookies on main page
        session.get("https://www.bseindia.com", headers=headers, timeout=10)
        resp = session.get(url, headers=headers, timeout=15)
        
        if resp.status_code == 200 and resp.text.strip().startswith("["):
            data = resp.json()
            for row in data:
                purpose = row.get("Purpose", "")
                rec_date_str = row.get("Record_Date")
                sec_name = row.get("Security_Name", "").strip()
                scrip_code = row.get("Security_Code", "")

                if not rec_date_str or rec_date_str == "-" or "/" not in rec_date_str:
                    continue

                try:
                    rec_date = datetime.datetime.strptime(rec_date_str.strip(), "%d/%m/%Y").date()
                except ValueError:
                    continue

                actions.append({
                    "symbol": sec_name,
                    "scrip_code": scrip_code,
                    "purpose": purpose,
                    "record_date": rec_date,
                    "is_dividend": "DIVIDEND" in purpose.upper(),
                    "is_agm": "AGM" in purpose.upper() or "ANNUAL GENERAL" in purpose.upper(),
                    "source": "BSE"
                })
    except Exception as e:
        print(f"BSE fetch error: {e}")
    return actions

def fetch_nse_corporate_actions():
    """Fetches corporate actions directly from NSE India."""
    url = "https://www.nseindia.com/api/corporates-corporateActions?index=equities"
    actions = []
    try:
        session = requests.Session(impersonate="chrome120")
        headers = dict(BROWSER_HEADERS)
        headers["Referer"] = "https://www.nseindia.com/"
        
        # Bootstrap NSE session cookies
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
        resp = session.get(url, headers=headers, timeout=15)
        
        if resp.status_code == 200 and resp.text.strip().startswith("["):
            data = resp.json()
            for row in data:
                symbol = row.get("symbol", "").strip()
                purpose = row.get("subject", "")
                rec_date_str = row.get("recDate")

                if not rec_date_str or rec_date_str == "-":
                    continue

                try:
                    # NSE date format: DD-Mon-YYYY
                    rec_date = datetime.datetime.strptime(rec_date_str.strip(), "%d-%b-%Y").date()
                except ValueError:
                    continue

                actions.append({
                    "symbol": symbol,
                    "scrip_code": "",
                    "purpose": purpose,
                    "record_date": rec_date,
                    "is_dividend": "DIVIDEND" in purpose.upper(),
                    "is_agm": "AGM" in purpose.upper() or "ANNUAL GENERAL" in purpose.upper(),
                    "source": "NSE"
                })
    except Exception as e:
        print(f"NSE corporate actions fetch error: {e}")
    return actions

def fetch_nse_ipos():
    """Fetches active, upcoming, and recent IPO schedules directly from NSE."""
    url = "https://www.nseindia.com/api/all-upcoming-issues-ipo"
    ipos = []
    try:
        session = requests.Session(impersonate="chrome120")
        headers = dict(BROWSER_HEADERS)
        headers["Referer"] = "https://www.nseindia.com/market-data/all-upcoming-issues-ipo"
        
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
        resp = session.get(url, headers=headers, timeout=15)
        
        if resp.status_code == 200 and resp.text.strip().startswith("["):
            data = resp.json()
            for item in data:
                company = item.get("companyName", "").strip()
                series = item.get("series", "EQ")
                open_str = item.get("issueStartDate")
                close_str = item.get("issueEndDate")
                price_band = item.get("priceBand", "Check Prospectus")

                if open_str and close_str:
                    try:
                        open_dt = datetime.datetime.strptime(open_str.strip(), "%d-%b-%Y").date()
                        close_dt = datetime.datetime.strptime(close_str.strip(), "%d-%b-%Y").date()
                        ipos.append({
                            "name": company,
                            "open": open_dt,
                            "close": close_dt,
                            "price": price_band,
                            "type": "SME" if series == "SME" else "Mainboard"
                        })
                    except Exception:
                        continue
    except Exception as e:
        print(f"NSE IPO fetch error: {e}")
    return ipos

def build_calendar():
    cal = Calendar()
    cal.add('prodid', '-//NSE-BSE Corporate & IPO Live Hub//EN')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', 'NSE/BSE Corporate Hub & Live IPOs')
    cal.add('x-wr-timezone', 'Asia/Kolkata')
    cal.add('x-published-ttl', 'PT1H')

    # 1. Deduplicate actions across BSE and NSE
    bse_actions = fetch_bse_corporate_actions()
    nse_actions = fetch_nse_corporate_actions()
    all_actions = bse_actions + nse_actions
    
    seen_events = set()
    unique_actions = []
    for a in all_actions:
        key = (a["symbol"][:6].upper(), a["record_date"])
        if key not in seen_events:
            seen_events.add(key)
            unique_actions.append(a)

    print(f"Found {len(unique_actions)} unique corporate actions from NSE/BSE.")

    for act in unique_actions:
        rec_date = act["record_date"]
        must_buy_by = get_previous_trading_day(rec_date)
        sym = act["symbol"]
        scrip = act.get("scrip_code", "")

        tv_link = build_tradingview_link(sym)
        scr_link = build_screener_link(sym)
        nse_portal = "https://www.nseindia.com/companies-listing/corporate-filings-actions"
        bse_portal = f"https://www.bseindia.com/stock-share-price/x/y/{scrip}/corporate-actions/" if scrip else "https://www.bseindia.com/corporates/corporate_act.aspx"
        meeting_pdf_portal = f"https://www.bseindia.com/stock-share-price/x/y/{scrip}/corp-announcements/" if scrip else "https://www.nseindia.com/companies-listing/corporate-filings-announcements"

        tag = "[DIVIDEND]" if act["is_dividend"] else ("[AGM]" if act["is_agm"] else "[CORP ACTION]")

        event = Event()
        event.add('uid', str(uuid.uuid4()))
        event.add('summary', f"{tag} {sym} - Last Day to Buy (T+1 Cutoff)")
        event.add('dtstart', must_buy_by)
        event.add('dtend', must_buy_by + datetime.timedelta(days=1))

        desc = (
            f"ACTION: Purchase on or before today (prior to 3:30 PM IST) for Demat credit by Record Date.\n\n"
            f"• Purpose: {act['purpose']}\n"
            f"• Record Date: {rec_date.strftime('%d-%b-%Y')}\n"
            f"• Settlement: T+1 Rolling Settlement (NSE/BSE)\n"
            f"-----------------------------------------\n"
            f"• TradingView Daily Chart:\n  {tv_link}\n\n"
            f"• Financial Statements & Balance Sheet:\n  {scr_link}\n\n"
            f"• Official Meeting Disclosures & PDF Filings:\n  {meeting_pdf_portal}\n\n"
            f"• BSE Corporate Actions Desk:\n  {bse_portal}\n\n"
            f"• NSE Corporate Filings Desk:\n  {nse_portal}\n"
        )
        event.add('description', desc)
        event.add('location', 'NSE / BSE India')
        cal.add_component(event)

    # 2. Process IPOs
    ipos = fetch_nse_ipos()
    print(f"Found {len(ipos)} upcoming/live IPOs.")
    for ipo in ipos:
        # IPO Open
        ev_open = Event()
        ev_open.add('uid', str(uuid.uuid4()))
        ev_open.add('summary', f"[IPO OPEN] {ipo['name']} ({ipo['type']})")
        ev_open.add('dtstart', ipo['open'])
        ev_open.add('dtend', ipo['open'] + datetime.timedelta(days=1))
        ev_open.add('description', (
            f"Issue: {ipo['name']}\n"
            f"Price Band / Cutoff: {ipo['price']}\n"
            f"Category: {ipo['type']}\n"
            f"Bidding Closes: {ipo['close'].strftime('%d-%b-%Y')}\n\n"
            f"• Live GMP Tracking & Reviews (InvestorGain/Chittorgarh):\n"
            f"  https://www.investorgain.com/report/live-ipo-gmp/331/\n"
            f"  https://www.chittorgarh.com/ipo/ipo_dashboard.asp"
        ))
        cal.add_component(ev_open)

        # IPO Close
        ev_close = Event()
        ev_close.add('uid', str(uuid.uuid4()))
        ev_close.add('summary', f"[IPO CLOSE] {ipo['name']} - Final Day")
        ev_close.add('dtstart', ipo['close'])
        ev_close.add('dtend', ipo['close'] + datetime.timedelta(days=1))
        ev_close.add('description', (
            f"Final day for bidding & UPI mandate authorization (Cutoff: 5:00 PM IST).\n"
            f"Issue: {ipo['name']}\n\n"
            f"• Registrar Allotment Status:\n"
            f"  Link Intime: https://linkintime.co.in/initial_offer/public-issues.html\n"
            f"  KFintech: https://ris.kfintech.com/ipostatus/\n"
        ))
        cal.add_component(ev_close)

    # 3. Monthly F&O Expiry Triggers
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
        fo.add('description', "Monthly NSE Nifty/BankNifty derivative contracts expiry.")
        cal.add_component(fo)

    with open("market_calendar.ics", "wb") as f:
        f.write(cal.to_ical())
    print("Calendar generation completed successfully.")

if __name__ == "__main__":
    build_calendar()
