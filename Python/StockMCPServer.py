"""MCP server exposing stock market data tools."""

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from market_data import TradingView, YahooFinance
from models import (
    AnalystRatings,
    EarningsReport,
    Fundamentals,
    Indicators,
    Mover,
    NewsArticle,
    OptionsChain,
    PriceBar,
    WatchlistChange,
    WatchlistUpdate,
)
from watchlist import Watchlist

mcp = FastMCP("finance", host="0.0.0.0", port=8080)
yahoo = YahooFinance()
tradingview = TradingView()
watchlist = Watchlist(Path(__file__).with_name("watchlist.json"))

GUIDELINES = """
Stock Tools Guidelines:
- All data is real time market data. Do not use stock prices from your memory. The data returned here is your SINGLE source of truth, treat it as such.
- Stock prices, options, news, earnings, analyst ratings and fundamentals come from the yfinance library.
- Indicators and market scans come from the TradingView library.
- The watchlist is persistent: use get_watchlist, add_to_watchlist and remove_from_watchlist to manage it.
"""


@mcp.tool()
def get_tool_guidelines() -> str:
    """Guidelines for using the stock tools. You should pull this before using any other tool."""
    return GUIDELINES


@mcp.tool()
def stock_scanner(min_volume: int = 5_000_000, min_change_percent: float = 5, limit: int = 25) -> list[Mover]:
    """Scan NASDAQ and NYSE for today's top gainers above a volume and percent-gain threshold, sorted by gain."""
    return tradingview.top_movers(min_volume, min_change_percent, limit)


@mcp.tool()
def stock_indicators(ticker: str, addtl_indicators: list[str] | None = None) -> Indicators:
    """Return RSI, MACD, and Bollinger Bands for a ticker. Pass addtl_indicators to include extra TradingView columns."""
    return tradingview.indicators(ticker.upper(), addtl_indicators or ())


@mcp.tool()
def get_ticker_price_history(ticker: str, period: str = "6mo", interval: str = "1d") -> list[PriceBar]:
    """Get timestamped Open, High, Low, Close, and Volume bars. period: 1d/5d/1mo/3mo/6mo/1y/2y. interval: 1h/1d/1wk/1mo."""
    return yahoo.price_history(ticker.upper(), period, interval)


@mcp.tool()
def get_options_chain(ticker: str, expiration_date: str | None = None) -> OptionsChain:
    """Get the options chain for a ticker with strikes, bid/ask, implied volatility (percent), and open interest. expiration_date format: 'YYYY-MM-DD'. If None, uses nearest expiration."""
    return yahoo.options_chain(ticker.upper(), expiration_date)


@mcp.tool()
def get_news(ticker: str, limit: int = 10) -> list[NewsArticle]:
    """Get recent news articles for a ticker with publisher, publish time (UTC), summary, and link."""
    return yahoo.news(ticker.upper(), limit)


@mcp.tool()
def get_earnings(ticker: str, limit: int = 8) -> EarningsReport:
    """Get the next earnings date with EPS and revenue estimates, plus recent quarters' estimated vs reported EPS and surprise percent."""
    return yahoo.earnings(ticker.upper(), limit)


@mcp.tool()
def get_analyst_ratings(ticker: str, limit: int = 10) -> AnalystRatings:
    """Get the analyst consensus, price targets, monthly buy/hold/sell counts, and the most recent rating and price target changes."""
    return yahoo.analyst_ratings(ticker.upper(), limit)


@mcp.tool()
def get_fundamentals(ticker: str) -> Fundamentals:
    """Get valuation, profitability, financial health, and ownership data. Margins, growth, returns and ownership are fractions (0.25 = 25%); dividend_yield_pct is already a percent."""
    return yahoo.fundamentals(ticker.upper())


@mcp.tool()
def get_watchlist() -> list[str]:
    """List the tickers currently on the watchlist."""
    return watchlist.tickers


@mcp.tool()
def add_to_watchlist(tickers: list[str]) -> WatchlistChange:
    """Add tickers to the watchlist. Returns which were added (applied), already present (skipped), or not found (invalid)."""
    return watchlist.add(tickers, is_valid=yahoo.ticker_exists)


@mcp.tool()
def remove_from_watchlist(tickers: list[str]) -> WatchlistChange:
    """Remove tickers from the watchlist. Returns which were removed (applied) and which were not on it (skipped)."""
    return watchlist.remove(tickers)


@mcp.tool()
def watchlist_updates() -> list[WatchlistUpdate]:
    """Return the latest close, daily percent change, trailing P/E, and key technical indicators for every watchlist ticker."""
    return [_watchlist_update(ticker) for ticker in watchlist.tickers]


def _watchlist_update(ticker: str) -> WatchlistUpdate:
    try:
        return WatchlistUpdate(
            ticker=ticker,
            move=yahoo.daily_move(ticker),
            trailing_pe=yahoo.trailing_pe(ticker),
            indicators=tradingview.indicators(ticker),
        )
    except Exception as error:
        return WatchlistUpdate(ticker=ticker, error=str(error))


if __name__ == "__main__":
    import uvicorn

    app = mcp.streamable_http_app()
    # app.add_middleware(BearerTokenMiddleware)
    uvicorn.run(app, host="0.0.0.0", port=8080)
