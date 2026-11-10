"""Adapters that fetch data from Yahoo Finance and TradingView and convert it into models."""

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

import pandas as pd
import yfinance as yf
from tradingview_screener import And, Or, Query, col

from models import (
    AnalystRatings,
    DailyMove,
    EarningsReport,
    EarningsResult,
    FinancialHealth,
    Fundamentals,
    Indicators,
    MarketProfile,
    Mover,
    NewsArticle,
    OptionContract,
    OptionsChain,
    PriceBar,
    PriceTargets,
    Profitability,
    RatingChange,
    RecommendationTrend,
    ScanResult,
    UpcomingEarnings,
    Valuation,
)

PRICE_DIGITS = 2
RATIO_DIGITS = 4
DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT = "%Y-%m-%d %H:%M %Z"

Section = TypeVar("Section", Valuation, Profitability, FinancialHealth, MarketProfile)


class MarketDataError(Exception):
    """Base class for errors raised while fetching market data."""


class NoDataError(MarketDataError):
    """Raised when a data source returns nothing for the requested ticker."""


def to_number(value: Any, digits: int = PRICE_DIGITS) -> int | float | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return round(number, digits)


def to_price(value: Any) -> float | None:
    number = to_number(value, RATIO_DIGITS)
    return number if number is None or abs(number) < 1 else to_number(number)


def to_percent(fraction: Any) -> float | None:
    number = to_number(fraction, RATIO_DIGITS + 2)
    return None if number is None else to_number(number * 100)


def to_int(value: Any) -> int | None:
    number = to_number(value, 0)
    return None if number is None else int(number)


def to_text(value: Any) -> str | None:
    return None if value is None or pd.isna(value) else str(value)


def to_date(value: Any, date_format: str = DATE_FORMAT) -> str | None:
    return None if value is None or pd.isna(value) else pd.Timestamp(value).strftime(date_format).strip()


def is_intraday(interval: str) -> bool:
    return interval.endswith(("m", "h")) and not interval.endswith("mo")


class YahooFinance:
    """Prices, options, news, earnings, analyst ratings and fundamentals from Yahoo Finance."""

    NEWS_CANDIDATES_PER_RESULT = 3

    _FUNDAMENTAL_KEYS: Mapping[type, Mapping[str, str]] = {
        Valuation: {
            "market_cap": "marketCap",
            "enterprise_value": "enterpriseValue",
            "trailing_pe": "trailingPE",
            "forward_pe": "forwardPE",
            "peg_ratio": "trailingPegRatio",
            "price_to_book": "priceToBook",
            "price_to_sales": "priceToSalesTrailing12Months",
            "ev_to_ebitda": "enterpriseToEbitda",
        },
        Profitability: {
            "trailing_eps": "trailingEps",
            "forward_eps": "forwardEps",
            "revenue": "totalRevenue",
            "revenue_growth": "revenueGrowth",
            "earnings_growth": "earningsGrowth",
            "gross_margin": "grossMargins",
            "operating_margin": "operatingMargins",
            "profit_margin": "profitMargins",
            "return_on_equity": "returnOnEquity",
            "return_on_assets": "returnOnAssets",
        },
        FinancialHealth: {
            "total_cash": "totalCash",
            "total_debt": "totalDebt",
            "debt_to_equity": "debtToEquity",
            "current_ratio": "currentRatio",
        },
        MarketProfile: {
            "beta": "beta",
            "fifty_two_week_high": "fiftyTwoWeekHigh",
            "fifty_two_week_low": "fiftyTwoWeekLow",
            "shares_outstanding": "sharesOutstanding",
            "insider_ownership": "heldPercentInsiders",
            "institutional_ownership": "heldPercentInstitutions",
            "short_percent_of_float": "shortPercentOfFloat",
            "trailing_dividend_rate": "trailingAnnualDividendRate",
            "forward_dividend_rate": "dividendRate",
            "forward_dividend_yield_pct": "dividendYield",
            "payout_ratio": "payoutRatio",
        },
    }

    def ticker_exists(self, ticker: str) -> bool:
        return not yf.Ticker(ticker).history(period="5d").empty

    def price_history(self, ticker: str, period: str, interval: str) -> list[PriceBar]:
        history = yf.Ticker(ticker).history(period=period, interval=interval)
        if history.empty:
            raise NoDataError(f"No price history for {ticker} (period={period}, interval={interval}).")
        timestamp_format = DATETIME_FORMAT if is_intraday(interval) else DATE_FORMAT
        return [
            PriceBar(
                timestamp=bar.Index.strftime(timestamp_format),
                open=to_number(bar.Open),
                high=to_number(bar.High),
                low=to_number(bar.Low),
                close=to_number(bar.Close),
                volume=to_int(bar.Volume),
            )
            for bar in history.itertuples()
        ]

    def daily_move(self, ticker: str) -> DailyMove:
        closes = yf.Ticker(ticker).history(period="5d", interval="1d", actions=False)["Close"].tail(2)
        if len(closes) < 2:
            raise NoDataError(f"Not enough recent closes for {ticker}.")
        return DailyMove(
            price=to_number(closes.iloc[-1]),
            change_percent=to_percent(closes.pct_change().iloc[-1]),
            as_of=to_date(closes.index[-1]),
        )

    def trailing_pe(self, ticker: str) -> float | None:
        return to_number(yf.Ticker(ticker).info.get("trailingPE"))

    def options_chain(self, ticker: str, expiration: str | None, strike_range_pct: float | None) -> OptionsChain:
        yahoo_ticker = yf.Ticker(ticker)
        expirations = list(yahoo_ticker.options)
        if not expirations:
            raise NoDataError(f"No options available for {ticker}.")
        expiration = expiration or expirations[0]
        if expiration not in expirations:
            raise MarketDataError(f"{expiration} is not an expiration for {ticker}. Available: {', '.join(expirations)}")
        underlying_price = to_number(yahoo_ticker.fast_info.last_price)
        chain = yahoo_ticker.option_chain(expiration)
        calls = self._contracts(self._near_price(chain.calls, underlying_price, strike_range_pct))
        puts = self._contracts(self._near_price(chain.puts, underlying_price, strike_range_pct))
        contracts = calls + puts
        return OptionsChain(
            ticker=ticker,
            expiration=expiration,
            underlying_price=underlying_price,
            strike_range_pct=strike_range_pct,
            quotes_stale=bool(contracts) and not any(contract.bid or contract.ask for contract in contracts),
            expirations=expirations,
            calls=calls,
            puts=puts,
        )

    def news(self, ticker: str, limit: int) -> list[NewsArticle]:
        yahoo_ticker = yf.Ticker(ticker)
        mention = self._mention_pattern(ticker, yahoo_ticker.info.get("shortName"))
        candidates = yahoo_ticker.get_news(count=limit * self.NEWS_CANDIDATES_PER_RESULT)
        articles = [self._article(item.get("content", {}), mention) for item in candidates]
        return sorted(articles, key=lambda article: not article.mentions_ticker)[:limit]

    def earnings(self, ticker: str, limit: int) -> EarningsReport:
        yahoo_ticker = yf.Ticker(ticker)
        upcoming = self._upcoming_earnings(yahoo_ticker.calendar or {})
        history = self._earnings_history(yahoo_ticker.get_earnings_dates(), limit)
        if upcoming is None and not history:
            raise NoDataError(f"No earnings data for {ticker}.")
        return EarningsReport(ticker=ticker, upcoming=upcoming, history=history)

    def analyst_ratings(self, ticker: str, limit: int) -> AnalystRatings:
        yahoo_ticker = yf.Ticker(ticker)
        info = yahoo_ticker.info
        targets = yahoo_ticker.analyst_price_targets
        trend = yahoo_ticker.recommendations_summary
        changes = yahoo_ticker.upgrades_downgrades
        ratings = AnalystRatings(
            ticker=ticker,
            consensus=info.get("averageAnalystRating"),
            analyst_count=to_int(info.get("numberOfAnalystOpinions")),
            price_targets=self._price_targets(targets) if targets else None,
            trend=self._recommendation_trend(trend),
            recent_changes=self._rating_changes(changes, limit),
        )
        if ratings.consensus is None and not ratings.trend and not ratings.recent_changes:
            raise NoDataError(f"No analyst coverage for {ticker}.")
        return ratings

    def fundamentals(self, ticker: str) -> Fundamentals:
        yahoo_ticker = yf.Ticker(ticker)
        info = yahoo_ticker.info
        if not info.get("quoteType"):
            raise NoDataError(f"No fundamentals for {ticker}.")
        return Fundamentals(
            ticker=ticker,
            name=info.get("longName"),
            sector=info.get("sector"),
            industry=info.get("industry"),
            currency=info.get("currency"),
            valuation=self._section(Valuation, info),
            profitability=self._section(Profitability, info),
            financial_health=self._section(FinancialHealth, info, **self._cash_flow(yahoo_ticker.ttm_cashflow)),
            market_profile=self._section(
                MarketProfile,
                info,
                trailing_dividend_yield_pct=to_percent(info.get("trailingAnnualDividendYield")),
            ),
        )

    @classmethod
    def _section(cls, section: type[Section], info: Mapping[str, Any], **computed: Any) -> Section:
        keys = cls._FUNDAMENTAL_KEYS[section]
        return section(**{name: to_number(info.get(key), RATIO_DIGITS) for name, key in keys.items()}, **computed)

    @staticmethod
    def _cash_flow(statement: pd.DataFrame) -> dict[str, float | None]:
        def latest(line_item: str) -> float | None:
            return to_number(statement.loc[line_item].iloc[0]) if line_item in statement.index else None

        operating = latest("Operating Cash Flow")
        capital_expenditure = latest("Capital Expenditure")
        free = None if operating is None or capital_expenditure is None else operating + capital_expenditure
        return {"operating_cash_flow": operating, "capital_expenditure": capital_expenditure, "free_cash_flow": free}

    @staticmethod
    def _near_price(contracts: pd.DataFrame, price: float | None, range_pct: float | None) -> pd.DataFrame:
        if price is None or range_pct is None:
            return contracts
        width = price * range_pct / 100
        return contracts[contracts["strike"].between(price - width, price + width)]

    @staticmethod
    def _mention_pattern(ticker: str, company_name: str | None) -> re.Pattern[str]:
        terms = [rf"\b{re.escape(ticker)}\b"]
        if company_name:
            brand = re.split(r"[\s,]+", company_name.strip())[0]
            terms.append(rf"(?i:\b{re.escape(brand)}\b)")
        return re.compile("|".join(terms))

    @staticmethod
    def _article(content: Mapping[str, Any], mention: re.Pattern[str]) -> NewsArticle:
        title = content.get("title")
        summary = content.get("summary")
        tickers = (content.get("finance") or {}).get("stockTickers") or []
        return NewsArticle(
            title=title,
            publisher=(content.get("provider") or {}).get("displayName"),
            published=content.get("pubDate"),
            summary=summary,
            url=(content.get("canonicalUrl") or {}).get("url"),
            related_tickers=[entry["symbol"] for entry in tickers if "symbol" in entry],
            mentions_ticker=bool(mention.search(f"{title or ''} {summary or ''}")),
        )

    @staticmethod
    def _contracts(contracts: pd.DataFrame) -> list[OptionContract]:
        return [
            OptionContract(
                contract_symbol=contract.contractSymbol,
                strike=to_number(contract.strike),
                last_price=to_number(contract.lastPrice),
                bid=to_number(contract.bid),
                ask=to_number(contract.ask),
                change=to_number(contract.change),
                percent_change=to_number(contract.percentChange),
                volume=to_int(contract.volume),
                open_interest=to_int(contract.openInterest),
                implied_volatility_pct=(
                    to_percent(contract.impliedVolatility) if to_number(contract.bid) or to_number(contract.ask) else None
                ),
                in_the_money=bool(contract.inTheMoney),
                last_trade_date=to_date(contract.lastTradeDate, DATETIME_FORMAT),
            )
            for contract in contracts.itertuples()
        ]

    @staticmethod
    def _upcoming_earnings(calendar: Mapping[str, Any]) -> UpcomingEarnings | None:
        dates = calendar.get("Earnings Date")
        if not dates:
            return None
        return UpcomingEarnings(
            dates=[to_date(day) for day in dates],
            eps_low=to_number(calendar.get("Earnings Low")),
            eps_average=to_number(calendar.get("Earnings Average")),
            eps_high=to_number(calendar.get("Earnings High")),
            revenue_low=to_int(calendar.get("Revenue Low")),
            revenue_average=to_int(calendar.get("Revenue Average")),
            revenue_high=to_int(calendar.get("Revenue High")),
        )

    @staticmethod
    def _earnings_history(dates: pd.DataFrame | None, limit: int) -> list[EarningsResult]:
        if dates is None or dates.empty:
            return []
        reported = dates[dates.index <= pd.Timestamp.now(tz=dates.index.tz)].head(limit)
        return [
            EarningsResult(
                date=to_date(day, DATETIME_FORMAT),
                eps_estimate=to_number(row["EPS Estimate"]),
                eps_reported=to_number(row["Reported EPS"]),
                surprise_percent=to_number(row["Surprise(%)"]),
            )
            for day, row in reported.iterrows()
        ]

    @staticmethod
    def _price_targets(targets: Mapping[str, Any]) -> PriceTargets:
        return PriceTargets(
            current=to_number(targets.get("current")),
            low=to_number(targets.get("low")),
            mean=to_number(targets.get("mean")),
            median=to_number(targets.get("median")),
            high=to_number(targets.get("high")),
        )

    @staticmethod
    def _recommendation_trend(trend: pd.DataFrame | None) -> list[RecommendationTrend]:
        if trend is None or trend.empty:
            return []
        return [
            RecommendationTrend(
                period=month.period,
                strong_buy=to_int(month.strongBuy),
                buy=to_int(month.buy),
                hold=to_int(month.hold),
                sell=to_int(month.sell),
                strong_sell=to_int(month.strongSell),
            )
            for month in trend.itertuples()
        ]

    @staticmethod
    def _rating_changes(changes: pd.DataFrame | None, limit: int) -> list[RatingChange]:
        if changes is None or changes.empty:
            return []
        return [
            RatingChange(
                date=to_date(change.Index, DATETIME_FORMAT),
                firm=to_text(change.Firm),
                to_grade=to_text(change.ToGrade),
                from_grade=to_text(change.FromGrade),
                action=to_text(change.Action),
                price_target_action=to_text(change.priceTargetAction),
                current_price_target=to_number(change.currentPriceTarget),
                prior_price_target=to_number(change.priorPriceTarget),
            )
            for change in changes.head(limit).itertuples()
        ]


class TradingView:
    """Market scans and technical indicators from the TradingView screener."""

    BASE_INDICATORS = ("RSI", "MACD.macd", "MACD.signal", "BB.lower", "BB.upper")
    EXCHANGES = ("NASDAQ", "NYSE")
    SECURITY_TYPES = ("stock", "fund", "dr")
    INTERVAL_SUFFIXES = {
        "1m": "|1",
        "5m": "|5",
        "15m": "|15",
        "30m": "|30",
        "1h": "|60",
        "2h": "|120",
        "4h": "|240",
        "1d": "",
        "1wk": "|1W",
        "1mo": "|1M",
    }

    TIMEFRAME_COLUMNS = {
        "1d": "change",
        "1w": "Perf.W",
        "1m": "Perf.1M",
        "3m": "Perf.3M",
        "ytd": "Perf.YTD",
        "1y": "Perf.Y",
    }
    SORT_COLUMNS = {
        "relative_volume": "relative_volume_10d_calc",
        "dollar_volume": "Value.Traded",
        "volume": "volume",
        "gap": "gap",
        "premarket_change": "premarket_change",
        "market_cap": "market_cap_basic",
        "rsi": "RSI",
    }
    SCAN_COLUMNS = (
        "name",
        "description",
        "sector",
        "industry",
        "close",
        "change",
        "change_abs",
        "gap",
        "premarket_change",
        *(column for column in TIMEFRAME_COLUMNS.values() if column != "change"),
        "volume",
        "Value.Traded",
        "average_volume_10d_calc",
        "relative_volume_10d_calc",
        "float_shares_outstanding",
        "market_cap_basic",
        "RSI",
        "SMA50",
        "SMA200",
        "price_52_week_high",
        "time",
        "update_time",
        "update_mode",
        "current_session",
    )
    MARKET_TIMEZONE = "America/New_York"

    def scan(
        self,
        timeframe: str = "1d",
        sort_by: str = "change",
        ascending: bool = False,
        min_change_percent: float | None = None,
        max_change_percent: float | None = None,
        min_price: float | None = None,
        min_market_cap: float | None = None,
        max_market_cap: float | None = None,
        min_dollar_volume: float | None = None,
        min_volume: int | None = None,
        min_relative_volume: float | None = None,
        sectors: Sequence[str] | None = None,
        min_rsi: float | None = None,
        max_rsi: float | None = None,
        above_sma50: bool | None = None,
        above_sma200: bool | None = None,
        max_pct_below_52w_high: float | None = None,
        include_adrs: bool = False,
        limit: int = 25,
    ) -> ScanResult:
        if timeframe not in self.TIMEFRAME_COLUMNS:
            raise MarketDataError(f"Unsupported timeframe {timeframe}. Use one of: {', '.join(self.TIMEFRAME_COLUMNS)}")
        change_column = self.TIMEFRAME_COLUMNS[timeframe]
        sort_column = change_column if sort_by == "change" else self.SORT_COLUMNS.get(sort_by)
        if sort_column is None:
            raise MarketDataError(f"Unsupported sort_by {sort_by}. Use one of: change, {', '.join(self.SORT_COLUMNS)}")

        filters = [
            col("exchange").isin(list(self.EXCHANGES)),
            *self._range("close", min_price, None),
            *self._range(change_column, min_change_percent, max_change_percent),
            *self._range("market_cap_basic", min_market_cap, max_market_cap),
            *self._range("Value.Traded", min_dollar_volume, None),
            *self._range("volume", min_volume, None),
            *self._range("relative_volume_10d_calc", min_relative_volume, None),
            *self._range("RSI", min_rsi, max_rsi),
            *self._side_of("SMA50", above_sma50),
            *self._side_of("SMA200", above_sma200),
        ]
        if sectors:
            filters.append(col("sector").isin(list(sectors)))
        if max_pct_below_52w_high is not None:
            filters.append(col("close").above_pct("price_52_week_high", 1 - max_pct_below_52w_high / 100))

        common_stock = (col("type") == "stock", col("typespecs").has(["common"]))
        query = Query().select(*self.SCAN_COLUMNS)
        if include_adrs:
            query = query.where(*filters).where2(Or(And(*common_stock), col("type") == "dr"))
        else:
            query = query.where(*filters, *common_stock)
        total, rows = query.order_by(sort_column, ascending=ascending).limit(limit).get_scanner_data()

        first = rows.iloc[0] if not rows.empty else None
        return ScanResult(
            as_of=self._market_time(rows["update_time"].max(), DATETIME_FORMAT) if first is not None else None,
            session=to_text(first["current_session"]) if first is not None else None,
            trading_day=self._market_time(first["time"], DATE_FORMAT) if first is not None else None,
            data_delay_minutes=self._delay_minutes(first["update_mode"]) if first is not None else None,
            total_matches=total,
            timeframe=timeframe,
            sort_by=sort_by,
            ascending=ascending,
            results=[self._mover(row) for _, row in rows.iterrows()],
        )

    @staticmethod
    def _range(column: str, low: float | None, high: float | None) -> list:
        bounds = []
        if low is not None:
            bounds.append(col(column) >= low)
        if high is not None:
            bounds.append(col(column) <= high)
        return bounds

    @staticmethod
    def _side_of(column: str, above: bool | None) -> list:
        if above is None:
            return []
        return [col("close") > col(column)] if above else [col("close") < col(column)]

    @classmethod
    def _market_time(cls, epoch_seconds: Any, date_format: str) -> str | None:
        if epoch_seconds is None or pd.isna(epoch_seconds):
            return None
        return pd.Timestamp(epoch_seconds, unit="s", tz="UTC").tz_convert(cls.MARKET_TIMEZONE).strftime(date_format)

    @staticmethod
    def _delay_minutes(update_mode: Any) -> int | None:
        mode = to_text(update_mode)
        if mode == "streaming":
            return 0
        match = re.fullmatch(r"delayed_streaming_(\d+)", mode or "")
        return int(match.group(1)) // 60 if match else None

    @staticmethod
    def _mover(row: pd.Series) -> Mover:
        price = to_number(row["close"], RATIO_DIGITS)
        high = to_number(row["price_52_week_high"], RATIO_DIGITS)
        sma50 = to_number(row["SMA50"], RATIO_DIGITS)
        sma200 = to_number(row["SMA200"], RATIO_DIGITS)
        return Mover(
            symbol=row["name"],
            name=to_text(row["description"]),
            sector=to_text(row["sector"]),
            industry=to_text(row["industry"]),
            price=to_price(row["close"]),
            change_percent=to_number(row["change"]),
            change_abs=to_price(row["change_abs"]),
            gap_percent=to_number(row["gap"]),
            premarket_change_percent=to_number(row["premarket_change"]),
            perf_week_percent=to_number(row["Perf.W"]),
            perf_month_percent=to_number(row["Perf.1M"]),
            perf_3m_percent=to_number(row["Perf.3M"]),
            perf_ytd_percent=to_number(row["Perf.YTD"]),
            perf_year_percent=to_number(row["Perf.Y"]),
            volume=to_int(row["volume"]),
            dollar_volume=to_int(row["Value.Traded"]),
            average_volume_10d=to_int(row["average_volume_10d_calc"]),
            relative_volume_10d=to_number(row["relative_volume_10d_calc"]),
            float_shares=to_int(row["float_shares_outstanding"]),
            market_cap=to_int(row["market_cap_basic"]),
            rsi=to_number(row["RSI"]),
            pct_from_52w_high=to_number((price / high - 1) * 100) if price is not None and high else None,
            above_sma50=price > sma50 if price is not None and sma50 is not None else None,
            above_sma200=price > sma200 if price is not None and sma200 is not None else None,
        )

    def indicators(self, ticker: str, interval: str = "1d", additional: Sequence[str] = ()) -> Indicators:
        if interval not in self.INTERVAL_SUFFIXES:
            raise MarketDataError(f"Unsupported interval {interval}. Use one of: {', '.join(self.INTERVAL_SUFFIXES)}")
        suffix = self.INTERVAL_SUFFIXES[interval]
        columns = {name: f"{name}{suffix}" for name in (*self.BASE_INDICATORS, *additional)}
        _, rows = (
            Query()
            .select("name", *columns.values())
            .where(col("name") == ticker)
            .where2(Or(*(col("type") == security_type for security_type in self.SECURITY_TYPES)))
            .get_scanner_data()
        )
        if rows.empty:
            raise NoDataError(f"No indicator data for {ticker}.")
        row = rows.iloc[0]
        return Indicators(
            ticker=ticker,
            interval=interval,
            rsi=to_number(row[columns["RSI"]]),
            macd=to_number(row[columns["MACD.macd"]]),
            macd_signal=to_number(row[columns["MACD.signal"]]),
            bollinger_lower=to_number(row[columns["BB.lower"]]),
            bollinger_upper=to_number(row[columns["BB.upper"]]),
            additional={name: self._indicator_value(row.get(columns[name])) for name in additional},
        )

    @staticmethod
    def _indicator_value(value: Any) -> float | str | None:
        return value if isinstance(value, str) else to_number(value)
