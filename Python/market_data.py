"""Adapters that fetch data from Yahoo Finance and TradingView and convert it into models."""

import math
from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

import pandas as pd
import yfinance as yf
from tradingview_screener import Query, col

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
            "free_cash_flow": "freeCashflow",
            "operating_cash_flow": "operatingCashflow",
        },
        MarketProfile: {
            "beta": "beta",
            "fifty_two_week_high": "fiftyTwoWeekHigh",
            "fifty_two_week_low": "fiftyTwoWeekLow",
            "shares_outstanding": "sharesOutstanding",
            "insider_ownership": "heldPercentInsiders",
            "institutional_ownership": "heldPercentInstitutions",
            "short_percent_of_float": "shortPercentOfFloat",
            "dividend_yield_pct": "dividendYield",
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
            change_percent=to_number(closes.pct_change().iloc[-1] * 100),
            as_of=to_date(closes.index[-1]),
        )

    def trailing_pe(self, ticker: str) -> float | None:
        return to_number(yf.Ticker(ticker).info.get("trailingPE"))

    def options_chain(self, ticker: str, expiration: str | None) -> OptionsChain:
        yahoo_ticker = yf.Ticker(ticker)
        expirations = list(yahoo_ticker.options)
        if not expirations:
            raise NoDataError(f"No options available for {ticker}.")
        expiration = expiration or expirations[0]
        if expiration not in expirations:
            raise MarketDataError(f"{expiration} is not an expiration for {ticker}. Available: {', '.join(expirations)}")
        chain = yahoo_ticker.option_chain(expiration)
        return OptionsChain(
            ticker=ticker,
            expiration=expiration,
            expirations=expirations,
            calls=self._contracts(chain.calls),
            puts=self._contracts(chain.puts),
        )

    def news(self, ticker: str, limit: int) -> list[NewsArticle]:
        articles = []
        for item in yf.Ticker(ticker).get_news(count=limit):
            content = item.get("content", {})
            articles.append(
                NewsArticle(
                    title=content.get("title"),
                    publisher=(content.get("provider") or {}).get("displayName"),
                    published=content.get("pubDate"),
                    summary=content.get("summary"),
                    url=(content.get("canonicalUrl") or {}).get("url"),
                )
            )
        return articles

    def earnings(self, ticker: str, limit: int) -> EarningsReport:
        yahoo_ticker = yf.Ticker(ticker)
        upcoming = self._upcoming_earnings(yahoo_ticker.calendar or {})
        history = self._earnings_history(yahoo_ticker.get_earnings_dates(limit=limit))
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
        info = yf.Ticker(ticker).info
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
            financial_health=self._section(FinancialHealth, info),
            market_profile=self._section(MarketProfile, info),
        )

    @classmethod
    def _section(cls, section: type[Section], info: Mapping[str, Any]) -> Section:
        keys = cls._FUNDAMENTAL_KEYS[section]
        return section(**{name: to_number(info.get(key), RATIO_DIGITS) for name, key in keys.items()})

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
                implied_volatility_pct=to_number(contract.impliedVolatility * 100),
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
    def _earnings_history(dates: pd.DataFrame | None) -> list[EarningsResult]:
        if dates is None or dates.empty:
            return []
        return [
            EarningsResult(
                date=to_date(day, DATETIME_FORMAT),
                eps_estimate=to_number(row["EPS Estimate"]),
                eps_reported=to_number(row["Reported EPS"]),
                surprise_percent=to_number(row["Surprise(%)"]),
            )
            for day, row in dates.iterrows()
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

    def top_movers(self, min_volume: int, min_change_percent: float, limit: int) -> list[Mover]:
        _, movers = (
            Query()
            .select("name", "volume", "change_abs", "change")
            .where(
                col("volume") > min_volume,
                col("change") > min_change_percent,
                col("exchange").isin(list(self.EXCHANGES)),
            )
            .limit(limit)
            .order_by("change", ascending=False)
            .get_scanner_data()
        )
        return [
            Mover(
                symbol=mover["name"],
                change_percent=to_number(mover["change"]),
                change_abs=to_number(mover["change_abs"]),
                volume=to_int(mover["volume"]),
            )
            for _, mover in movers.iterrows()
        ]

    def indicators(self, ticker: str, additional: Sequence[str] = ()) -> Indicators:
        _, rows = (
            Query()
            .select("name", *self.BASE_INDICATORS, *additional)
            .where(col("name") == ticker)
            .get_scanner_data()
        )
        if rows.empty:
            raise NoDataError(f"No indicator data for {ticker}.")
        row = rows.iloc[0]
        return Indicators(
            ticker=ticker,
            rsi=to_number(row["RSI"]),
            macd=to_number(row["MACD.macd"]),
            macd_signal=to_number(row["MACD.signal"]),
            bollinger_lower=to_number(row["BB.lower"]),
            bollinger_upper=to_number(row["BB.upper"]),
            additional={name: self._indicator_value(row.get(name)) for name in additional},
        )

    @staticmethod
    def _indicator_value(value: Any) -> float | str | None:
        return value if isinstance(value, str) else to_number(value)
