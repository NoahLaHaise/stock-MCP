"""MCP server exposing stock market data tools."""

from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP

from market_data import TradingView, YahooFinance
from models import (
    AnalystRatings,
    EarningsReport,
    Fundamentals,
    Indicators,
    NewsArticle,
    OptionsChain,
    PriceBar,
    ScanResult,
    WatchlistChange,
    WatchlistUpdate,
)
from watchlist import Watchlist

mcp = FastMCP("finance", host="0.0.0.0", port=8080)
yahoo = YahooFinance()
tradingview = TradingView()
watchlist = Watchlist(Path(__file__).with_name("watchlist.json"))

Sector = Literal[
    "Commercial Services",
    "Communications",
    "Consumer Durables",
    "Consumer Non-Durables",
    "Consumer Services",
    "Distribution Services",
    "Electronic Technology",
    "Energy Minerals",
    "Finance",
    "Government",
    "Health Services",
    "Health Technology",
    "Industrial Services",
    "Miscellaneous",
    "Non-Energy Minerals",
    "Process Industries",
    "Producer Manufacturing",
    "Retail Trade",
    "Technology Services",
    "Transportation",
    "Utilities",
]

GUIDELINES = """
Stock Tools Guidelines:
- All data is live market data. Do not use stock prices from your memory. The data returned here is your SINGLE source of truth, treat it as such.
- TradingView data (scanner and indicators) may be delayed. Check data_delay_minutes, as_of and session in scanner results before calling a price current.
- Stock prices, options, news, earnings, analyst ratings and fundamentals come from the yfinance library.
- Indicators and market scans come from the TradingView library.
- The watchlist is persistent: use get_watchlist, add_to_watchlist and remove_from_watchlist to manage it.
"""


@mcp.tool()
def get_tool_guidelines() -> str:
    """Guidelines for using the stock tools. You should pull this before using any other tool."""
    return GUIDELINES


@mcp.tool()
def stock_scanner(
    timeframe: Literal["1d", "1w", "1m", "3m", "ytd", "1y"] = "1d",
    sort_by: Literal[
        "change", "relative_volume", "dollar_volume", "volume", "gap", "premarket_change", "market_cap", "rsi"
    ] = "change",
    ascending: bool = False,
    min_change_percent: float | None = None,
    max_change_percent: float | None = None,
    min_price: float | None = 5,
    min_market_cap: float | None = None,
    max_market_cap: float | None = None,
    min_dollar_volume: float | Literal["auto"] | None = "auto",
    min_volume: int | None = None,
    min_relative_volume: float | None = None,
    sectors: list[Sector] | None = None,
    min_rsi: float | None = None,
    max_rsi: float | None = None,
    above_sma50: bool | None = None,
    above_sma200: bool | None = None,
    max_pct_below_52w_high: float | None = None,
    include_adrs: bool = True,
    limit: int = 25,
) -> ScanResult:
    """Screen NASDAQ and NYSE common stocks and ADRs (preferreds, units, warrants, ETFs and pre-IPO listings excluded).

    timeframe picks the performance window used by sort_by="change", the min/max_change_percent filters, and each
    result's timeframe_change_percent (change_percent is always the 1-day move). Sort ascending=True with
    sort_by="change" for the worst losers. min_relative_volume compares today's volume to the 10-day average
    (2 = twice normal). max_pct_below_52w_high keeps names within that percent of their 52-week high.
    above_sma50/above_sma200: True keeps closes above the moving average, False below. Market caps and dollar volume
    are USD. Set a filter to null to disable it.

    min_dollar_volume (USD traded today) defaults to "auto": $20M, except with sort_by="premarket_change", where
    today's volume is unreliable and a $300M min_market_cap is applied instead (unless you set one). Pass a number
    or null to override. applied_filters in the response shows the filters that were actually used.

    The response includes session (pre_market/market/post_market/out_of_session), trading_day (the session the daily
    change refers to; on weekends this is the last trading day), as_of (US Eastern) and data_delay_minutes.
    total_matches counts every stock that passed the filters, not just the returned page."""
    return tradingview.scan(
        timeframe=timeframe,
        sort_by=sort_by,
        ascending=ascending,
        min_change_percent=min_change_percent,
        max_change_percent=max_change_percent,
        min_price=min_price,
        min_market_cap=min_market_cap,
        max_market_cap=max_market_cap,
        min_dollar_volume=min_dollar_volume,
        min_volume=min_volume,
        min_relative_volume=min_relative_volume,
        sectors=sectors,
        min_rsi=min_rsi,
        max_rsi=max_rsi,
        above_sma50=above_sma50,
        above_sma200=above_sma200,
        max_pct_below_52w_high=max_pct_below_52w_high,
        include_adrs=include_adrs,
        limit=limit,
    )


@mcp.tool()
def stock_indicators(ticker: str, interval: str = "1d", addtl_indicators: list[str] | None = None) -> Indicators:
    """Return RSI, MACD, and Bollinger Bands for a ticker on the given timeframe. interval: 1m/5m/15m/30m/1h/2h/4h/1d/1wk/1mo. Pass addtl_indicators to include extra TradingView columns on the same timeframe."""
    return tradingview.indicators(ticker.upper(), interval, addtl_indicators or ())


@mcp.tool()
def get_ticker_price_history(ticker: str, period: str = "6mo", interval: str = "1d") -> list[PriceBar]:
    """Get timestamped Open, High, Low, Close, and Volume bars. period: 1d/5d/1mo/3mo/6mo/1y/2y. interval: 1h/1d/1wk/1mo."""
    return yahoo.price_history(ticker.upper(), period, interval)


@mcp.tool()
def get_options_chain(
    ticker: str, expiration_date: str | None = None, strike_range_pct: float | None = 15
) -> OptionsChain:
    """Get the options chain for a ticker with strikes, bid/ask, implied volatility (percent), and open interest. expiration_date format: 'YYYY-MM-DD'; if None, uses nearest expiration. Only strikes within strike_range_pct of the underlying price are returned; pass None for the full chain. If quotes_stale is true (no bids or asks, typically outside market hours), bid/ask/open interest are unreliable and implied volatility is null."""
    return yahoo.options_chain(ticker.upper(), expiration_date, strike_range_pct)


@mcp.tool()
def get_news(ticker: str, limit: int = 10) -> list[NewsArticle]:
    """Get recent news articles for a ticker with publisher, publish time (UTC), summary, link, and related tickers. Articles that mention the ticker or company in the title or summary (mentions_ticker) are listed first; others may only reference it in passing."""
    return yahoo.news(ticker.upper(), limit)


@mcp.tool()
def get_earnings(ticker: str, limit: int = 8) -> EarningsReport:
    """Get the next earnings date with EPS and revenue estimates, plus the last `limit` reported quarters' estimated vs reported EPS and surprise percent."""
    return yahoo.earnings(ticker.upper(), limit)


@mcp.tool()
def get_analyst_ratings(ticker: str, limit: int = 10) -> AnalystRatings:
    """Get the analyst consensus, price targets, monthly buy/hold/sell counts, and the most recent rating and price target changes."""
    return yahoo.analyst_ratings(ticker.upper(), limit)


@mcp.tool()
def get_fundamentals(ticker: str) -> Fundamentals:
    """Get valuation, profitability, financial health, and ownership data. Margins, growth, returns, ownership and payout_ratio are fractions (0.25 = 25%); fields ending in _pct are percents. Cash flows are trailing twelve months, with free_cash_flow = operating_cash_flow + capital_expenditure (capex is negative). Trailing dividend fields reflect dividends paid over the past year; forward fields reflect the current declared rate."""
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
