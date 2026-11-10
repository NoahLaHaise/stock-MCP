# Stock MCP Server

A Model Context Protocol (MCP) server that gives Claude live stock market data — prices, options, news, earnings, analyst ratings, fundamentals, technical indicators, a configurable stock screener and a persistent watchlist — over a remote streamable HTTP connection.

## Tools

### Guidelines

| Tool | Description |
|------|-------------|
| `get_tool_guidelines` | Usage guidelines Claude reads before calling any other tool |

### Market data

| Tool | Description |
|------|-------------|
| `get_ticker_price_history` | Timestamped OHLCV bars. Periods: `1d/5d/1mo/3mo/6mo/1y/2y`. Intervals: `1h/1d/1wk/1mo` |
| `get_options_chain` | Strikes, bid/ask, implied volatility and open interest for an expiration (nearest by default). Strikes are limited to ±15% of spot unless `strike_range_pct` is changed or set to null; flags stale quotes outside market hours |
| `get_news` | Recent articles with publisher, UTC publish time, summary, link and related tickers; articles that mention the ticker or company are listed first |
| `get_earnings` | Next earnings date with EPS and revenue estimates, plus estimated vs reported EPS and surprise percent for past quarters |
| `get_analyst_ratings` | Consensus, price targets, monthly buy/hold/sell counts and recent rating and price target changes |
| `get_fundamentals` | Valuation, profitability, financial health, ownership, TTM cash flows (free cash flow = operating cash flow + capex) and trailing/forward dividends |

### Technicals and screening

| Tool | Description |
|------|-------------|
| `stock_indicators` | RSI, MACD and Bollinger Bands on intervals from `1m` to `1mo`, plus any extra TradingView columns |
| `stock_scanner` | Screens NASDAQ and NYSE common stocks and ADRs. Sort by change, relative/dollar volume, volume, gap, pre-market change, market cap or RSI over `1d/1w/1m/3m/ytd/1y`, ascending or descending. Filters for price, market cap, change, dollar volume, relative volume, sector, RSI, 50/200-day SMA and distance from the 52-week high. Results include session, trading day, timestamp, data delay and the filters actually applied |

### Watchlist

| Tool | Description |
|------|-------------|
| `get_watchlist` | List watchlist tickers |
| `add_to_watchlist` | Add tickers (invalid symbols are rejected) |
| `remove_from_watchlist` | Remove tickers |
| `watchlist_updates` | Latest close, daily change, trailing P/E and key indicators for every watchlist ticker |

The watchlist is saved to `Python/watchlist.json` (git-ignored). Until it is first edited, the defaults in `Python/watchlist.py` are used.

## Data Sources

- **Prices, options, news, earnings, analyst ratings, fundamentals**: [yfinance](https://github.com/ranaroussi/yfinance)
- **Technical indicators and scanner**: [TradingView Screener](https://github.com/shner-elmo/TradingView-Screener) (may be delayed; the scanner reports the delay)

## Running

Requires Python 3.11+ and [uv](https://github.com/astral-sh/uv).

* Start the MCP server (listens on port 8080):
```bash
uv run mcp run Python/StockMCPServer.py --transport streamable-http
```

* *Optional* Expose it through a Cloudflare tunnel:
```bash
cloudflared tunnel run tunnel-name
```

## Claude.ai Connector

Add a remote MCP connector in Claude.ai pointing to:
```
https://cloudflare-tunnel-domain.com
```

No authentication required.
