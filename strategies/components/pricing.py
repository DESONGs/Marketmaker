from typing import List, Tuple
from utils.helpers import round_to_tick_size


def compute_price_levels(
    mid_price: float,
    spread_pct: float,
    max_orders: int,
    tick_size: float,
) -> Tuple[List[float], List[float]]:
    """
    根据中间价与目标价差计算多档买卖价格，匹配原 MarketMaker.calculate_prices
    中的定价与阶梯分布逻辑（不包含行情获取与日志）。

    返回的买单价格从高到低，卖单价格从低到高，并做最小步进的去重与单调性修正。
    """
    # 使用基础价差
    exact_spread = mid_price * (spread_pct / 100.0)

    # 基础买卖价位
    base_buy_price = mid_price - (exact_spread / 2)
    base_sell_price = mid_price + (exact_spread / 2)

    base_buy_price = round_to_tick_size(base_buy_price, tick_size)
    base_sell_price = round_to_tick_size(base_sell_price, tick_size)

    buy_prices: List[float] = []
    sell_prices: List[float] = []

    spacing_factor = 1.0  # 越大代表越分散
    steps = max(1, int(max_orders) - 1)

    for i in range(int(max_orders)):
        if i == 0:
            multiplier = 1.0
        else:
            level_ratio = i / steps
            multiplier = 1.0 + spacing_factor * level_ratio

        buy_target = mid_price - (exact_spread / 2) * multiplier
        sell_target = mid_price + (exact_spread / 2) * multiplier

        buy_price = round_to_tick_size(buy_target, tick_size)
        sell_price = round_to_tick_size(sell_target, tick_size)

        if i > 0 and buy_prices and buy_price >= buy_prices[-1]:
            buy_price = round_to_tick_size(buy_prices[-1] - tick_size, tick_size)

        if i > 0 and sell_prices and sell_price <= sell_prices[-1]:
            sell_price = round_to_tick_size(sell_prices[-1] + tick_size, tick_size)

        buy_prices.append(buy_price)
        sell_prices.append(sell_price)

    return buy_prices, sell_prices

