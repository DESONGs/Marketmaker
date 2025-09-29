from typing import List, Tuple, Optional


def calculate_session_profit(
    session_buy_trades: List[Tuple[float, float]],
    session_sell_trades: List[Tuple[float, float]],
) -> float:
    """
    计算本次执行的已实现利润（撮合买队列与卖队列），复制自 MarketMaker._calculate_session_profit。
    """
    if not session_buy_trades or not session_sell_trades:
        return 0.0

    buy_queue = session_buy_trades.copy()
    total_profit = 0.0

    for sell_price, sell_quantity in session_sell_trades:
        remaining_sell = sell_quantity

        while remaining_sell > 0 and buy_queue:
            buy_price, buy_quantity = buy_queue[0]
            matched_quantity = min(remaining_sell, buy_quantity)

            # 计算这笔交易的利润
            trade_profit = (sell_price - buy_price) * matched_quantity
            total_profit += trade_profit

            remaining_sell -= matched_quantity
            if matched_quantity >= buy_quantity:
                buy_queue.pop(0)
            else:
                buy_queue[0] = (buy_price, buy_quantity - matched_quantity)

    return total_profit


def calculate_average_buy_cost(
    buy_trades: List[Tuple[float, float]],
    sell_trades: List[Tuple[float, float]],
    fallback_bid: Optional[float] = None,
) -> float:
    """
    计算当前多头未对冲部分（剩余买入）平均成本价；若无未匹配买入且提供了 `fallback_bid`，则返回该价格；否则返回0。
    逻辑与 MarketMaker._calculate_average_buy_cost 一致。
    """
    if not buy_trades:
        return fallback_bid or 0.0

    buy_queue = buy_trades.copy()
    total_buy_quantity = sum(q for _, q in buy_queue)
    total_buy_cost = sum(p * q for p, q in buy_queue)

    consumed_quantity = 0.0
    consumed_cost = 0.0

    for sell_price, sell_quantity in sell_trades:
        remaining_sell = sell_quantity

        while remaining_sell > 0 and buy_queue:
            buy_price, buy_quantity = buy_queue[0]
            matched_quantity = min(remaining_sell, buy_quantity)
            consumed_quantity += matched_quantity
            consumed_cost += buy_price * matched_quantity
            remaining_sell -= matched_quantity

            if matched_quantity >= buy_quantity:
                buy_queue.pop(0)
            else:
                buy_queue[0] = (buy_price, buy_quantity - matched_quantity)

    remaining_buy_quantity = total_buy_quantity - consumed_quantity
    remaining_buy_cost = total_buy_cost - consumed_cost

    if remaining_buy_quantity <= 0:
        return fallback_bid or 0.0

    return remaining_buy_cost / remaining_buy_quantity

