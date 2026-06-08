# Stock MCP Server

A Model Context Protocol (MCP) server that exposes real-time stock market data and technical indicators to Claude via a remote HTTP connection.

## Tools

| Tool | Description |
|------|-------------|
| `get_tool_guidelines` | Returns usage guidelines — Claude calls this before any other tool |
| `stock_scanner` | Scans NASDAQ and NYSE for stocks with volume > 5M and daily gain > 5%, sorted by top movers |
| `stock_indicators` | Returns RSI, MACD, and Bollinger Bands for a ticker (supports additional TradingView columns) |
| `watchlist_updates` | Returns price change, current price, trailing P/E, and key indicators for all watchlist tickers |
| `get_ticker_price_history` | Returns OHLCV history for a ticker. Periods: `1mo/3mo/6mo/1y/2y`. Intervals: `1d/1wk/1mo` |
| `get_options_chain` | Returns full options chain (strikes, bid/ask, IV, open interest) for a ticker and expiration date |

## Data Sources

- **Price data / options**: [yfinance](https://github.com/ranaroussi/yfinance)
- **Technical indicators / scanner**: [TradingView Screener](https://github.com/shner-elmo/TradingView-Screener)

## Running
* Set your watchlist in Python/WATCHLIST.py

* Start the MCP server:
```bash
uv run mcp run Python/StockMCPServer.py --transport streamable-http
```

* *Optional* Start the Cloudflare tunnel:
```bash
cloudflared tunnel run tunnel-name
```

## Claude.ai Connector

Add a remote MCP connector in Claude.ai pointing to:
```
https://cloudflare-tunnel-domain.com
```

No authentication required.
