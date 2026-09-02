import datetime
import uuid
import yfinance as yf
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

# Core liquid universe covering large & mid-cap dividend and action leaders
TRACKED_SYMBOLS = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "ITC", "SBIN",
    "BHARTIARTL", "KOTAKBANK", "LT", "HINDUNILVR", "AXISBANK", "BAJFINANCE",
    "MARUTI", "ASIANPAINT", "TITAN", "SUNPHARMA", "TATAMOTORS", "ULTRACEMCO",
    "NTPC", "POWERGRID", "ONGC", "COALINDIA", "BAJAJFINSV", "M&M", "ADANIENT",
    "ADANIPORTS", "TATASTEEL", "JSWSTEEL", "HCLTECH", "WIPRO", "TECHM",
    "VEDL", "IOC", "BPCL", "HINDZINC", "DIVISLAB", "DRREDDY", "CIPLA",
    "EICHERMOT", "HEROMOTOCO", "BRITANNIA", "NESTLEIND", "PIDILITIND",
    "SIEMENS", "ABB", "HAL", "BEL", "PFC", "RECLTD"
]

def is_trading_day(d):
    return d.weekday() < 5 and d not in NSE_HOLIDAYS_2026

def get_previous_trading_day(d):
    curr = d - datetime.timedelta(days=1)
    while not is_trading_day(curr):
        curr -= datetime.timedelta(days=1)
    return curr

def build_tradingview_link(symbol):
    return f"https://in.tradingview.com/chart/?symbol=NSE:{symbol}"

def build_screener_link(symbol):
    return f"https://www.screener.in/company/{symbol}/consolidated/"

def build_calendar():
    cal = Calendar()
    cal.add('prodid', '-//Live Indian Capital Markets Feed//EN')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', 'NSE/BSE Corporate Actions & Earnings Hub')
    cal.add('x-wr-timezone', 'Asia/Kolkata')
    cal.add('x-published-ttl', 'PT1H')

    today = datetime.date.today()
    cutoff_future = today + datetime.timedelta(days=90)
    cutoff_past = today - datetime.timedelta(days=14)

    events_count = 0

    for sym in TRACKED_SYMBOLS:
        ticker_str = f"{sym}.NS"
        try:
            t = yf.Ticker(ticker_str)
            
            # 1. Check Dividends & Ex-Dates
            divs = t.dividends
            if not divs.empty:
                for ts, amount in divs.items():
                    div_date = ts.date()
                    if cutoff_past <= div_date <= cutoff_future:
                        # Ex-date is the cutoff day under T+1
                        must_buy_by = div_date if is_trading_day(div_date) else get_previous_trading_day(div_date)
                        
                        event = Event()
                        event.add('uid', str(uuid.uuid4()))
                        event.add('summary', f"[DIVIDEND] {sym} (₹{amount:.2f}) - Must Buy Cutoff")
                        event.add('dtstart', must_buy_by)
                        event.add('dtend', must_buy_by + datetime.timedelta(days=1))
                        
                        desc = (
                            f"ACTION: Purchase today before 3:30 PM IST for Demat credit eligibility.\n\n"
                            f"• Dividend Amount: ₹{amount:.2f} per share\n"
                            f"• Ex-Date: {div_date.strftime('%d-%b-%Y')}\n"
                            f"• Settlement: T+1 Rolling Cycle\n"
                            f"-----------------------------------------\n"
                            f"• TradingView Daily Chart:\n  {build_tradingview_link(sym)}\n\n"
                            f"• Screener Fundamentals & Balance Sheet:\n  {build_screener_link(sym)}\n\n"
                            f"• BSE/NSE Regulatory Announcements:\n  https://www.nseindia.com/companies-listing/corporate-filings-actions\n"
                        )
                        event.add('description', desc)
                        event.add('location', 'NSE / BSE')
                        cal.add_component(event)
                        events_count += 1

            # 2. Check Upcoming Earnings / Results Dates
            try:
                cal_df = t.calendar
                if cal_df is not None and not cal_df.empty:
                    # Look for Earnings Date row/columns
                    if "Earnings Date" in cal_df.index:
                        earnings_dates = cal_df.loc["Earnings Date"]
                        for ed in earnings_dates:
                            if hasattr(ed, "date"):
                                e_date = ed.date()
                                if today <= e_date <= cutoff_future:
                                    event = Event()
                                    event.add('uid', str(uuid.uuid4()))
                                    event.add('summary', f"[EARNINGS / RESULTS] {sym} - Financial Results")
                                    event.add('dtstart', e_date)
                                    event.add('dtend', e_date + datetime.timedelta(days=1))
                                    event.add('description', (
                                        f"Company quarterly board meeting & results announcement.\n\n"
                                        f"• Symbol: {sym}\n"
                                        f"• TradingView Chart: {build_tradingview_link(sym)}\n"
                                        f"• Screener Financials: {build_screener_link(sym)}\n"
                                    ))
                                    event.add('location', 'NSE / BSE')
                                    cal.add_component(event)
                                    events_count += 1
            except Exception:
                pass

        except Exception as e:
            continue

    # 3. Monthly F&O Expiry Days
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
        fo.add('description', "NSE Index & Stock F&O Expiry Cutoff.")
        cal.add_component(fo)
        events_count += 1

    with open("market_calendar.ics", "wb") as f:
        f.write(cal.to_ical())
    print(f"Generated {events_count} total live events into market_calendar.ics successfully.")

if __name__ == "__main__":
    build_calendar()
