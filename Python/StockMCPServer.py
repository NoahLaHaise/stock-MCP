from finvizfinance.quote import finvizfinance
from tradingview_screener import Query, col
from datetime import datetime, timedelta
import pandas as pd
from .WATCHLIST import WATCHLIST
import yfinance as yf
from mcp.server.fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import os
from dotenv import load_dotenv
#from API.TelegramMessenger import TelegramMessenger

load_dotenv()

API_TOKEN = os.environ["MCP_API_TOKEN"]


class BearerTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path.startswith("/.well-known/"):
            return await call_next(request)
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != API_TOKEN:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)


mcp = FastMCP("finance", host="0.0.0.0", port=8080)

@mcp.tool()
def stock_scanner() -> str:
    """Scan NASDAQ and NYSE for stocks with volume > 5M and daily gain > 5%, sorted by top movers."""
    _, df = (Query()
          .select('name', 'volume', 'change_abs', 'change')
          .where(col('volume') > 5_000_000,
                 col('change') > 5,
                 col('exchange').isin(['NASDAQ', 'NYSE']))
          .limit(25)
          .order_by('change', ascending=False)
          .get_scanner_data())

    if df.empty:
        return "No movers found."

    lines = [f"{row['name']}: +{row['change']:.1f}% | Vol: {int(row['volume']):,} | Abs chg: {row['change_abs']:.2f}"
             for _, row in df.iterrows()]
    return "\n".join(lines)


@mcp.tool()
def stock_indicators(ticker: str, addtl_indicators: list[str] = []) -> str:
    """Return RSI, MACD, and Bollinger Bands for a ticker. Pass addtl_indicators to include extra TradingView columns."""
    base_cols = ['name', 'RSI', 'MACD.macd', 'MACD.signal', 'BB.upper', 'BB.lower']

    _, df = (Query()
        .select(*base_cols, *addtl_indicators)
        .where(col('name') == ticker)
        .get_scanner_data())

    if df.empty:
        return "No indicator data found"

    row = df.iloc[0]
    result = (f"RSI: {row['RSI']:.1f} | "
              f"MACD: {row['MACD.macd']:.2f} / Signal: {row['MACD.signal']:.2f} | "
              f"BB: {row['BB.lower']:.2f} - {row['BB.upper']:.2f}")

    for indicator in addtl_indicators:
        if indicator in row:
            result += f" | {indicator}: {row[indicator]}"

    return result


@mcp.tool()
def watchlist_updates() -> str:
    """Return price change, current price, trailing P/E, and key technical indicators for all watchlist tickers."""
    updates = ""
    for ticker in WATCHLIST:
        stock = yf.Ticker(ticker)
        price_history = stock.history(period='2d', interval='1d', actions=False)

        price_movement = price_history.tail(2)['Close']
        percent_change = price_movement.pct_change().iloc[-1]
        pe_ratio = stock.info.get('trailingPE', 'N/A')

        updates += f"Ticker: {ticker} has moved {percent_change:.2%}. Current price {round(price_movement.iloc[1], 2)}. Trailing P/E: {pe_ratio}\n"
        updates += f"Key indicators: {stock_indicators(ticker)}\n\n"

    return updates

@mcp.tool()
def get_history(ticker: str, period: str = "6mo", interval: str = "1d") -> list:
    """Get Open, High, Low, Close, and Volume price history. period: 1mo/3mo/6mo/1y/2y. interval: 1d/1wk/1mo."""
    t = yf.Ticker(ticker)
    df = t.history(period=period, interval=interval)
    df.index = df.index.strftime("%Y-%m-%d")
    return df[["Open", "High", "Low", "Close", "Volume"]].to_dict("records")


@mcp.tool()
def get_options_chain(ticker: str, expiration_date: str | None = None) -> dict:
    """Get full options chain with strikes, bid/ask, IV, and open interest. expiration_date format: 'YYYY-MM-DD'. If None, uses nearest expiration."""
    t = yf.Ticker(ticker)
    if not t.options:
        return {"error": f"No options available for {ticker}"}
    if expiration_date is None:
        expiration_date = t.options[0]

    def _chain_records(df):
        df = df.copy()
        df["lastTradeDate"] = df["lastTradeDate"].astype(str)
        return df.to_dict("records")

    chain = t.option_chain(expiration_date)
    return {
        "expiration": expiration_date,
        "expirations": list(t.options),
        "calls": _chain_records(chain.calls),
        "puts": _chain_records(chain.puts),
    }

if __name__ == "__main__":
    import uvicorn
    app = mcp.streamable_http_app()
    app.add_middleware(BearerTokenMiddleware)
    uvicorn.run(app, host="0.0.0.0", port=8080)