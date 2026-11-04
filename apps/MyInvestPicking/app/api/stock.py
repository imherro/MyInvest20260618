from fastapi import APIRouter, Query

from config.settings import DEFAULT_TOP_N
from data.trade_calendar import format_api_date
from engine.data_loader import TushareDataLoader
from engine.shadow_portfolio import build_shadow_portfolio
from strategy.core_strategy import build_stock_picks


router = APIRouter(prefix="/api", tags=["stock"])


@router.get("/picks")
def get_picks(
    date: str | None = Query(default=None, description="Trade date as YYYY-MM-DD or YYYYMMDD"),
    top_n: int = Query(default=DEFAULT_TOP_N, ge=1, le=100),
    shadow_days: int = Query(default=10, ge=0, le=30),
) -> dict[str, object]:
    return build_stock_picks(trade_date=date, top_n=top_n, shadow_days=shadow_days)


@router.get("/shadow-portfolio")
def get_shadow_portfolio(
    date: str | None = Query(default=None, description="Trade date as YYYY-MM-DD or YYYYMMDD"),
    top_n: int = Query(default=DEFAULT_TOP_N, ge=1, le=100),
    shadow_days: int = Query(default=5, ge=1, le=30),
) -> dict[str, object]:
    loader = TushareDataLoader()
    market_data = loader.load_market_data(date)
    shadow = build_shadow_portfolio(
        market_data,
        top_n=top_n,
        lookback_days=shadow_days,
    )
    return {
        "status": "ok",
        "date": format_api_date(market_data.trade_date),
        "trading_date": format_api_date(market_data.trade_date),
        "source": market_data.source,
        "mock_mode": market_data.mock_mode,
        "shadow_portfolio": shadow,
    }
