# strategies/__init__.py
"""Strategies 模块，包含各种交易策略。"""

__all__ = ["MarketMaker", "PerpetualMarketMaker"]


def __getattr__(name):
    if name == "MarketMaker":
        from .market_maker import MarketMaker

        return MarketMaker
    if name == "PerpetualMarketMaker":
        from .perp_market_maker import PerpetualMarketMaker

        return PerpetualMarketMaker
    raise AttributeError(f"module 'strategies' has no attribute {name!r}")
