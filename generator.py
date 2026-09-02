import datetime
import uuid
import requests
from icalendar import Calendar, Event, vText

# Public holiday calendar for Indian markets to adjust T+1 settlement
NSE_HOLIDAYS_2026 = {
    datetime.date(2026, 1, 26),  # Republic Day
    datetime.date(2026, 3, 6),   # Holi
    datetime.date(2026, 4, 3),   # Good Friday
    datetime.date(2026, 4, 14),  # Dr. Ambedkar Jayanti
    datetime.date(2026, 5, 1),   # Maharashtra Day
    datetime.date(2026, 8, 15),  # Independence Day
    datetime.date(2026, 10, 2),  # Gandhi Jayanti
    datetime.date(2026, 10, 20), # Dussehra
    datetime.date(2026, 11, 10), # Diwali Laxmi Pujan
    datetime.date(2026, 12, 25), # Christmas
}

def is_trading_day(date_obj):
    # Weekends (5: Sat, 6: Sun) and NSE holidays
    return date_obj.weekday() < 5 and date_obj not in NSE_HOLIDAYS_2026

def get_previous_trading_day(date_obj):
    current = date_obj - datetime.timedelta(days=1)
    while not is_trading_day(current):
        current -= datetime.timedelta(days=1)
    return current

def build_tradingview_link(symbol, exchange="NSE"):
    return f"https://www.tradingview.com/chart/?symbol={exchange}:{symbol}"

def build_screener_link(symbol):
    return f"https://www.screener.in/company/{symbol}/consolidated/"

def create_market_calendar():
    cal = Calendar()
    cal.add('prodid', '-//Indian Markets & Dividends Live Feed//IN')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', 'NSE/BSE Corporate & IPO Hub')
    cal.add('x-wr-timezone', 'Asia/Kolkata')
    cal.add('x-published-ttl', 'PT1H')

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    # Fetch official BSE corporate actions API endpoint
    bse_api = "https://api.bseindia.com/BseIndiaAPI/api/DefaultData/w?page=1"
    
    # Pre-structured corporate events container
    events_data = []

    try:
        response = requests.get(bse_api, headers=headers, timeout=10)
        if response.status_code == 200:
            raw_data = response.json()
            for row in raw_data:
                purpose = row.get("Purpose", "")
                if "DIVIDEND" in purpose.upper():
                    try:
                        rec_date_str = row.get("Record_Date")
                        rec_date = datetime.datetime.strptime(rec_date_str, "%d/%m/%Y").date()
                        events_data.append({
                            "symbol": row.get("Security_Name", "").strip(),
                            "type": "DIVIDEND",
                            "record_date": rec_date,
                            "purpose": purpose,
                            "bse_code": row.get("Security_Code", "")
                        })
                    except Exception:
                        continue
    except Exception:
        # Gracefully handle network timeouts without breaking existing events
        pass

    # Sample baseline data for layout verification
    sample_records = [
        {
            "symbol": "TCS",
            "type": "DIVIDEND",
            "record_date": datetime.date(2026, 9, 18),
            "amount": "₹12.00 Interim",
            "bse_code": "532540"
        },
        {
            "symbol": "RELIANCE",
            "type": "DIVIDEND",
            "record_date": datetime.date(2026, 9, 25),
            "amount": "₹10.00 Final",
            "bse_code": "500325"
        }
    ]

    for item in sample_records:
        rec_date = item["record_date"]
        # Under India's T+1 rolling settlement, Ex-Date is the prior trading day.
        # Investor must execute purchase on or before this day to get Demat credit by Record Date.
        must_buy_by = get_previous_trading_day(rec_date)
        
        tv_link = build_tradingview_link(item["symbol"])
        screener_link = build_screener_link(item["symbol"])
        bse_link = f"https://www.bseindia.com/stock-share-price/x/y/{item['bse_code']}/corporate-actions/"

        event = Event()
        event.add('uid', str(uuid.uuid4()))
        event.add('summary', f"[DIV] {item['symbol']} ({item['amount']}) - Last Day to Buy")
        event.add('dtstart', must_buy_by)
        event.add('dtend', must_buy_by + datetime.timedelta(days=1))
        
        description = (
            f"ACTION: Must purchase on/before today for Demat credit.\n"
            f"-----------------------------------------\n"
            f"• Dividend: {item['amount']}\n"
            f"• Record Date: {rec_date.strftime('%d-%b-%Y')}\n"
            f"• Settlement: T+1 Rolling Cycle\n"
            f"-----------------------------------------\n"
            f"• TradingView Chart:\n  {tv_link}\n"
            f"• Balance Sheet & Financials:\n  {screener_link}\n"
            f"• BSE Corporate Filing:\n  {bse_link}\n"
        )
        event.add('description', description)
        event.add('location', 'NSE / BSE')
        cal.add_component(event)

    # Macro Trigger Demo Event
    macro_event = Event()
    macro_event.add('uid', str(uuid.uuid4()))
    macro_event.add('summary', '[MACRO] US Federal Reserve Rate Decision (FOMC)')
    macro_event.add('dtstart', datetime.date(2026, 9, 16))
    macro_event.add('dtend', datetime.date(2026, 9, 17))
    macro_event.add('description', "High market impact across global equity and forex indices.\n• Track US10Y & DXY.")
    macro_event.add('location', 'Washington, D.C.')
    cal.add_component(macro_event)

    with open("market_calendar.ics", "wb") as f:
        f.write(cal.to_ical())

if __name__ == "__main__":
    create_market_calendar()
