import datetime
import uuid
import re
from curl_cffi import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event

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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
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

def classify_action(purpose):
    p_up = purpose.upper()
    if "DIVIDEND" in p_up:
        return "[DIVIDEND]"
    elif "BONUS" in p_up:
        return "[BONUS ISSUE]"
    elif "SPLIT" in p_up or "SUB-DIVISION" in p_up:
        return "[STOCK SPLIT]"
    elif "RIGHTS" in p_up:
        return "[RIGHTS ISSUE]"
    elif "AGM" in p_up or "ANNUAL GENERAL" in p_up:
        return "[AGM]"
    elif "BOARD MEETING" in p_up or "FINANCIAL RESULTS" in p_up:
        return "[RESULTS/BM]"
    return "[CORP ACTION]"

def fetch_bse_corporate_actions():
    """Fetches all corporate actions: Dividends, Splits, Bonus, Rights from BSE."""
    today = datetime.date.today()
    fdate = (today - datetime.timedelta(days=10)).strftime("%Y%m%d")
    tdate = (today + datetime.timedelta(days=75)).strftime("%Y%m%d")
    
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

                tag = classify_action(purpose)
                actions.append({
                    "symbol": sec_name,
                    "scrip_code": scrip_code,
                    "purpose": purpose,
                    "record_date": rec_date,
                    "tag": tag,
                    "source": "BSE"
                })
    except Exception as e:
        print(f"BSE Action fetch error: {e}")
    return actions

def fetch_bse_board_meetings():
    """Fetches upcoming company board meetings for Financial Results and Earnings."""
    today = datetime.date.today()
    fdate = today.strftime("%Y%m%d")
    tdate = (today + datetime.timedelta(days=30)).strftime("%Y%m%d")
    url = f"https://api.bseindia.com/BseIndiaAPI/api/BMData/w?Fdate={fdate}&TDate={tdate}&scripcode="
    
    meetings = []
    try:
        session = requests.Session(impersonate="chrome120")
        headers = dict(BROWSER_HEADERS)
        headers["Referer"] = "https://www.bseindia.com/"
        resp = session.get(url, headers=headers, timeout=12)
        if resp.status_code == 200 and resp.text.strip().startswith("["):
            for row in resp.json():
                m_date_str = row.get("Meeting_Date")
                if not m_date_str or "/" not in m_date_str:
                    continue
                try:
                    m_date = datetime.datetime.strptime(m_date_str.strip(), "%d/%m/%Y").date()
                    meetings.append({
                        "symbol": row.get("Security_Name", "").strip(),
                        "scrip_code": row.get("Security_Code", ""),
                        "purpose": row.get("Purpose", "Quarterly Results / Board Meeting"),
                        "meeting_date": m_date,
                        "tag": "[EARNINGS / RESULTS]"
                    })
                except Exception:
                    continue
    except Exception as e:
        print(f"BSE Board Meetings fetch error: {e}")
    return meetings

def fetch_chittorgarh_ipos():
    """Scrapes live & upcoming Mainboard and SME IPOs from Chittorgarh."""
    ipos = []
    url = "https://www.chittorgarh.com/report/mainboard-ipo-list-in-india-bse-nse/83/"
    try:
        session = requests.Session(impersonate="chrome120")
        resp = session.get(url, headers=BROWSER_HEADERS, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            table = soup.find("table")
            if table:
                rows = table.find_all("tr")
                for row in rows[1:]:
                    cols = [c.text.strip() for c in row.find_all(["td", "th"])]
                    if len(cols) >= 5:
                        company = cols[0].replace("IPO Detail", "").strip()
                        open_str = cols[1]
                        close_str = cols[2]
                        price = cols[3]
                        
                        # Parse date formats (e.g. Sep 01, 2026 or 01-Sep-2026)
                        parsed_open = None
                        parsed_close = None
                        for fmt in ("%b %d, %Y", "%d-%b-%Y", "%Y-%m-%d"):
                            try:
                                parsed_open = datetime.datetime.strptime(open_str, fmt).date()
                                parsed_close = datetime.datetime.strptime(close_str, fmt).date()
                                break
                            except Exception:
                                continue

                        if parsed_open and parsed_close:
                            ipos.append({
                                "name": company,
                                "open": parsed_open,
                                "close": parsed_close,
                                "price": price,
                                "type": "Mainboard"
                            })
    except Exception as e:
        print(f"Chittorgarh IPO scraper error: {e}")
    return ipos

def build_calendar():
    cal = Calendar()
    cal.add('prodid', '-//NSE-BSE Live Financial Action Hub//EN')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', 'NSE/BSE Corporate Actions, Results & IPOs')
    cal.add('x-wr-timezone', 'Asia/Kolkata')
    cal.add('x-published-ttl', 'PT1H')

    # 1. Process Corporate Actions (Dividends, Splits, Bonus, Rights)
    actions = fetch_bse_corporate_actions()
    print(f"Loaded {len(actions)} corporate actions (Dividends, Bonus, Splits, Rights).")

    for act in actions:
        rec_date = act["record_date"]
        must_buy_by = get_previous_trading_day(rec_date)
        sym = act["symbol"]
        scrip = act.get("scrip_code", "")
        tag = act["tag"]

        tv_link = build_tradingview_link(sym)
        scr_link = build_screener_link(sym)
        mc_corp_link = f"https://www.moneycontrol.com/india/stockpricequote/{sym[0].lower()}/{sym.lower()}"
        bse_filings = f"https://www.bseindia.com/stock-share-price/x/y/{scrip}/corp-announcements/" if scrip else "https://www.bseindia.com"

        event = Event()
        event.add('uid', str(uuid.uuid4()))
        event.add('summary', f"{tag} {sym} - Last Day to Buy (T+1 Cutoff)")
        event.add('dtstart', must_buy_by)
        event.add('dtend', must_buy_by + datetime.timedelta(days=1))

        desc = (
            f"ACTION: Purchase today before 3:30 PM IST for Demat credit by Record Date.\n\n"
            f"• Announcement: {act['purpose']}\n"
            f"• Record Date: {rec_date.strftime('%d-%b-%Y')}\n"
            f"• Settlement: T+1 Rolling Cycle\n"
            f"-----------------------------------------\n"
            f"• TradingView Daily Chart:\n  {tv_link}\n\n"
            f"• Screener (Fundamentals & Dividend Yield):\n  {scr_link}\n\n"
            f"• Moneycontrol Company Hub:\n  {mc_corp_link}\n\n"
            f"• BSE Meeting Disclosures & PDF Filings:\n  {bse_filings}\n"
        )
        event.add('description', desc)
        event.add('location', 'NSE / BSE India')
        cal.add_component(event)

    # 2. Process Board Meetings & Financial Results
    meetings = fetch_bse_board_meetings()
    print(f"Loaded {len(meetings)} Board Meetings & Earnings announcements.")
    for bm in meetings:
        sym = bm["symbol"]
        scrip = bm.get("scrip_code", "")
        m_date = bm["meeting_date"]
        tv_link = build_tradingview_link(sym)
        scr_link = build_screener_link(sym)
        bse_filings = f"https://www.bseindia.com/stock-share-price/x/y/{scrip}/corp-announcements/" if scrip else "https://www.bseindia.com"

        event = Event()
        event.add('uid', str(uuid.uuid4()))
        event.add('summary', f"{bm['tag']} {sym} - Earnings / Board Meeting")
        event.add('dtstart', m_date)
        event.add('dtend', m_date + datetime.timedelta(days=1))
        
        desc = (
            f"EVENT: Company Board of Directors meeting today.\n\n"
            f"• Purpose: {bm['purpose']}\n"
            f"• Meeting Date: {m_date.strftime('%d-%b-%Y')}\n"
            f"-----------------------------------------\n"
            f"• TradingView Daily Chart:\n  {tv_link}\n\n"
            f"• Screener Financial Statements:\n  {scr_link}\n\n"
            f"• BSE Disclosures & Outcome PDFs:\n  {bse_filings}\n"
        )
        event.add('description', desc)
        event.add('location', 'NSE / BSE')
        cal.add_component(event)

    # 3. Process IPO Timelines & Live GMP Links
    ipos = fetch_chittorgarh_ipos()
    print(f"Loaded {len(ipos)} IPOs from market tracker.")
    for ipo in ipos:
        # Bidding Open
        ev_open = Event()
        ev_open.add('uid', str(uuid.uuid4()))
        ev_open.add('summary', f"[IPO OPEN] {ipo['name']}")
        ev_open.add('dtstart', ipo['open'])
        ev_open.add('dtend', ipo['open'] + datetime.timedelta(days=1))
        ev_open.add('description', (
            f"Issue: {ipo['name']}\n"
            f"Price Band: ₹{ipo['price']}\n"
            f"Bidding Closes: {ipo['close'].strftime('%d-%b-%Y')}\n\n"
            f"• Live Grey Market Premium (GMP) & Analysis:\n"
            f"  https://www.investorgain.com/report/live-ipo-gmp/331/\n"
            f"  https://www.chittorgarh.com/ipo/ipo_dashboard.asp\n"
        ))
        cal.add_component(ev_open)

        # Bidding Close
        ev_close = Event()
        ev_close.add('uid', str(uuid.uuid4()))
        ev_close.add('summary', f"[IPO CLOSE] {ipo['name']} - Final Bidding Day")
        ev_close.add('dtstart', ipo['close'])
        ev_close.add('dtend', ipo['close'] + datetime.timedelta(days=1))
        ev_close.add('description', (
            f"Final day for application and UPI mandate approval (Cutoff: 5:00 PM IST).\n"
            f"Issue: {ipo['name']}\n\n"
            f"• Check Allotment Status:\n"
            f"  Link Intime: https://linkintime.co.in/initial_offer/public-issues.html\n"
            f"  KFintech: https://ris.kfintech.com/ipostatus/\n"
        ))
        cal.add_component(ev_close)

    with open("market_calendar.ics", "wb") as f:
        f.write(cal.to_ical())
    print("Calendar generation completed successfully.")

if __name__ == "__main__":
    build_calendar()
