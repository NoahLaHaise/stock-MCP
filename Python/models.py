"""Structured results returned by the stock MCP tools."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PriceBar:
    timestamp: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: int | None


@dataclass(frozen=True)
class DailyMove:
    price: float | None
    change_percent: float | None
    as_of: str


@dataclass(frozen=True)
class Mover:
    symbol: str
    name: str | None
    price: float | None
    change_percent: float | None
    change_abs: float | None
    volume: int | None
    market_cap: float | None


@dataclass(frozen=True)
class Indicators:
    ticker: str
    interval: str
    rsi: float | None
    macd: float | None
    macd_signal: float | None
    bollinger_lower: float | None
    bollinger_upper: float | None
    additional: dict[str, float | str | None] = field(default_factory=dict)


@dataclass(frozen=True)
class WatchlistUpdate:
    ticker: str
    move: DailyMove | None = None
    trailing_pe: float | None = None
    indicators: Indicators | None = None
    error: str | None = None


@dataclass(frozen=True)
class WatchlistChange:
    applied: list[str]
    skipped: list[str]
    invalid: list[str]
    watchlist: list[str]


@dataclass(frozen=True)
class OptionContract:
    contract_symbol: str
    strike: float | None
    last_price: float | None
    bid: float | None
    ask: float | None
    change: float | None
    percent_change: float | None
    volume: int | None
    open_interest: int | None
    implied_volatility_pct: float | None
    in_the_money: bool
    last_trade_date: str | None


@dataclass(frozen=True)
class OptionsChain:
    ticker: str
    expiration: str
    underlying_price: float | None
    strike_range_pct: float | None
    quotes_stale: bool
    expirations: list[str]
    calls: list[OptionContract]
    puts: list[OptionContract]


@dataclass(frozen=True)
class NewsArticle:
    title: str | None
    publisher: str | None
    published: str | None
    summary: str | None
    url: str | None
    related_tickers: list[str]
    mentions_ticker: bool


@dataclass(frozen=True)
class UpcomingEarnings:
    dates: list[str]
    eps_low: float | None
    eps_average: float | None
    eps_high: float | None
    revenue_low: int | None
    revenue_average: int | None
    revenue_high: int | None


@dataclass(frozen=True)
class EarningsResult:
    date: str
    eps_estimate: float | None
    eps_reported: float | None
    surprise_percent: float | None


@dataclass(frozen=True)
class EarningsReport:
    ticker: str
    upcoming: UpcomingEarnings | None
    history: list[EarningsResult]


@dataclass(frozen=True)
class PriceTargets:
    current: float | None
    low: float | None
    mean: float | None
    median: float | None
    high: float | None


@dataclass(frozen=True)
class RecommendationTrend:
    period: str
    strong_buy: int | None
    buy: int | None
    hold: int | None
    sell: int | None
    strong_sell: int | None


@dataclass(frozen=True)
class RatingChange:
    date: str | None
    firm: str | None
    to_grade: str | None
    from_grade: str | None
    action: str | None
    price_target_action: str | None
    current_price_target: float | None
    prior_price_target: float | None


@dataclass(frozen=True)
class AnalystRatings:
    ticker: str
    consensus: str | None
    analyst_count: int | None
    price_targets: PriceTargets | None
    trend: list[RecommendationTrend]
    recent_changes: list[RatingChange]


@dataclass(frozen=True)
class Valuation:
    market_cap: float | None
    enterprise_value: float | None
    trailing_pe: float | None
    forward_pe: float | None
    peg_ratio: float | None
    price_to_book: float | None
    price_to_sales: float | None
    ev_to_ebitda: float | None


@dataclass(frozen=True)
class Profitability:
    trailing_eps: float | None
    forward_eps: float | None
    revenue: float | None
    revenue_growth: float | None
    earnings_growth: float | None
    gross_margin: float | None
    operating_margin: float | None
    profit_margin: float | None
    return_on_equity: float | None
    return_on_assets: float | None


@dataclass(frozen=True)
class FinancialHealth:
    total_cash: float | None
    total_debt: float | None
    debt_to_equity: float | None
    current_ratio: float | None
    operating_cash_flow: float | None
    capital_expenditure: float | None
    free_cash_flow: float | None


@dataclass(frozen=True)
class MarketProfile:
    beta: float | None
    fifty_two_week_high: float | None
    fifty_two_week_low: float | None
    shares_outstanding: float | None
    insider_ownership: float | None
    institutional_ownership: float | None
    short_percent_of_float: float | None
    trailing_dividend_rate: float | None
    trailing_dividend_yield_pct: float | None
    forward_dividend_rate: float | None
    forward_dividend_yield_pct: float | None
    payout_ratio: float | None


@dataclass(frozen=True)
class Fundamentals:
    ticker: str
    name: str | None
    sector: str | None
    industry: str | None
    currency: str | None
    valuation: Valuation
    profitability: Profitability
    financial_health: FinancialHealth
    market_profile: MarketProfile
