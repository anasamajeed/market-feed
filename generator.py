import datetime
import uuid
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

# Broad universe of liquid dividend-paying stocks and blue chips
UNIVERSE = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "ITC", "SBIN",
    "BHARTIARTL", "KOTAKBANK", "LT", "HINDUNILVR", "AXISBANK", "BAJFINANCE",
    "MARUTI", "ASIANPAINT", "TITAN", "SUNPHARMA", "ULTRACEMCO", "NTPC",
    "POWERGRID", "ONGC", "COALINDIA", "BAJAJFINSV", "M&M", "ADANIENT",
    "ADANIPORTS", "TATASTEEL", "JSWSTEEL", "HCLTECH", "WIPRO", "TECHM",
    "VEDL", "IOC", "BPCL", "HINDZINC", "DIVISLAB", "DRREDDY", "CIPLA",
    "EICHERMOT", "HEROMOTOCO", "BRITANNIA", "NESTLEIND", "PIDILITIND",
    "SIEMENS", "ABB", "HAL", "BEL", "PFC", "RECLTD", "GAIL", "NMDC",
    "NATIONALUM", "CANBK", "BANKBARODA", "PNB", "INDUSINDBK", "DLF",
    "GODREJCP", "DABUR", "COLPAL", "SHREECEM", "AMBUJACEM", "CHOLAFIN",
    "MUTHOOTFIN", "BAJAJ-AUTO", "TVSMOTOR", "APOLLOHOSP", "MAXHEALTH",
    "LTIM", "PERSISTENT", "COFORGE", "IRCTC", "RVNL", "IRFC", "CONCOR"
]

# High-impact global & domestic macroeconomic dates for 2026
MACRO_EVENTS_2026 = [
    # RBI MPC Rate Decisions
    {"date": datetime.date(2026, 10, 8), "summary": "[MACRO] RBI Monetary Policy Committee (MPC) Outcome", "desc": "RBI repo rate decision & policy statement. High impact on banking indices and bond yields."},
    {"date": datetime.date(2026, 12, 10), "summary": "[MACRO] RBI Monetary Policy Committee (MPC) Outcome", "desc": "RBI repo rate decision & policy statement."},
    # US Federal Reserve (FOMC)
    {"date": datetime.date(2026, 9, 16), "summary": "[MACRO] US Federal Reserve FOMC Rate Decision", "desc": "Fed funds rate policy announcement & Jerome Powell press conference. High global impact."},
    {"date": datetime.date(2026, 11, 4), "summary": "[MACRO] US Federal Reserve FOMC Rate Decision", "desc": "FOMC interest rate decision."},
    {"date": datetime.date(2026, 12, 16), "summary": "[MACRO] US Federal Reserve FOMC Rate Decision", "desc": "FOMC rate decision & economic projections."},
    # US Inflation (CPI)
    {"date": datetime.date(2026, 9, 11), "summary": "[MACRO] US Consumer Price Index (CPI) Inflation Data", "desc": "Key inflation print influencing Fed interest rate trajectories."},
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
    return f"https://in.tradingview.com/chart/?symbol=NSE:{symbol}"

def build_screener_link(symbol):
    return f"https://www.screener.in/company/{symbol}/consolidated/"

def build_calendar():
    cal = Calendar()
    cal.add('prodid', '-//Indian Capital Markets Live Action Hub//EN')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', 'Indian Equities, Corporate Actions & Macro Hub')
    cal.add('x-wr-timezone', 'Asia/Kolkata')
    cal.add('x-published-ttl', 'PT1H')

    today = datetime.date.today()
    cutoff_future = today + datetime.timedelta(days=90)
    cutoff_past = today - datetime.timedelta(days=14)

    total_events = 0

    # 1. Fetch Dividends & Actions across the liquid universe
    for sym in UNIVERSE:
        ticker_str = f"{sym}.NS"
        try:
            t = yf.Ticker(ticker_str)
            divs = t.dividends
            if not divs.empty:
                for ts, amount in divs.items():
                    div_date = ts.date()
                    if cutoff_past <= div_date <= cutoff_future:
                        # Ex-date cutoff calculation under T+1
                        must_buy_by = div_date if is_trading_day(div_date) else get_previous_trading_day(div_date)

                        event = Event()
                        event.add('uid', str(uuid.uuid4()))
                        event.add('summary', f"[DIVIDEND] {sym} (₹{amount:.2f}) - Buy Cutoff")
                        event.add('dtstart', must_buy_by)
                        event.add('dtend', must_buy_by + datetime.timedelta(days=1))

                        desc = (
                            f"ACTION: Purchase before 3:30 PM IST today for Demat ownership by Record Date.\n\n"
                            f"• Dividend: ₹{amount:.2f} per share\n"
                            f"• Ex-Date: {div_date.strftime('%d-%b-%Y')}\n"
                            f"• Settlement: T+1 Rolling Cycle\n"
                            f"-----------------------------------------\n"
                            f"• TradingView Daily Chart:\n  {build_tradingview_link(sym)}\n\n"
                            f"• Screener Fundamentals & Dividend History:\n  {build_screener_link(sym)}\n\n"
                            f"• NSE Regulatory Filings:\n  https://www.nseindia.com/companies-listing/corporate-filings-actions\n"
                        )
                        event.add('description', desc)
                        event.add('location', 'NSE / BSE India')
                        cal.add_component(event)
                        total_events += 1

            # 2. Upcoming Financial Results / Earnings Dates
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
                                    ev_bm.add('summary', f"[RESULTS] {sym} - Financial Results Declaration")
                                    ev_bm.add('dtstart', e_date)
                                    ev_bm.add('dtend', e_date + datetime.timedelta(days=1))
                                    ev_bm.add('description', (
                                        f"Quarterly earnings announcement & Board of Directors outcome.\n\n"
                                        f"• Symbol: {sym}\n"
                                        f"• TradingView Daily Chart:\n  {build_tradingview_link(sym)}\n\n"
                                        f"• Screener Balance Sheet:\n  {build_screener_link(sym)}\n"
                                    ))
                                    ev_bm.add('location', 'NSE / BSE')
                                    cal.add_component(ev_bm)
                                    total_events += 1
            except Exception:
                pass

        except Exception:
            continue

    # 3. Macro Triggers (RBI MPC, US Fed FOMC, CPI)
    for m in MACRO_EVENTS_2026:
        ev_m = Event()
        ev_m.add('uid', str(uuid.uuid4()))
        ev_m.add('summary', m["summary"])
        ev_m.add('dtstart', m["date"])
        ev_m.add('dtend', m["date"] + datetime.timedelta(days=1))
        ev_m.add('description', m["desc"])
        ev_m.add('location', 'Economic Calendar')
        cal.add_component(ev_m)
        total_events += 1

    # 4. Monthly F&O Expiry Triggers
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
        fo.add('description', "NSE Index & Stock Options/Futures monthly contract expiry.")
        cal.add_component(fo)
        total_events += 1

    with open("market_calendar.ics", "wb") as f:
        f.write(cal.to_ical())
    print(f"Generated {total_events} total live events into market_calendar.ics successfully.")

if __name__ == "__main__":
    build_calendar()
