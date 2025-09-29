"""
PriceEngine: 价格层生成与调整
职责：调用 pricing.py 中的纯函数，生成多档买卖价格
"""
from typing import Tuple, List, Optional
from strategies.components.state import MMContext
from strategies.components.pricing import compute_price_levels
from utils.helpers import round_to_tick_size
from logger import setup_logger

logger = setup_logger("price_engine")


class PriceEngine:
    """价格引擎，负责计算价格层"""

    def __init__(self, context: MMContext):
        self.context = context

    def get_current_price(self) -> Optional[float]:
        """
        获取当前价格（优先使用WebSocket数据）
        迁移自 MarketMaker.get_current_price
        """
        # 检查 WS 连接（如果有）
        if self.context.ws:
            # 注意：check_ws_connection 由 WSManager 负责，这里暂时保留原逻辑
            pass

        price = None
        if self.context.ws and hasattr(self.context.ws, 'connected') and self.context.ws.connected:
            if hasattr(self.context.ws, 'get_current_price'):
                price = self.context.ws.get_current_price()

        if price is None:
            ticker = self.context.client.get_ticker(self.context.symbol)
            if isinstance(ticker, dict) and "error" in ticker:
                logger.error(f"获取价格失败: {ticker['error']}")
                return None

            if "lastPrice" not in ticker:
                logger.error(f"获取到的价格数据不完整: {ticker}")
                return None
            return float(ticker['lastPrice'])
        return price

    def get_market_depth(self) -> Tuple[Optional[float], Optional[float]]:
        """
        获取市场深度（优先使用WebSocket数据）
        迁移自 MarketMaker.get_market_depth
        """
        bid_price, ask_price = None, None
        if self.context.ws and hasattr(self.context.ws, 'connected') and self.context.ws.connected:
            if hasattr(self.context.ws, 'get_bid_ask'):
                bid_price, ask_price = self.context.ws.get_bid_ask()

        if bid_price is None or ask_price is None:
            order_book = self.context.client.get_order_book(self.context.symbol)
            if isinstance(order_book, dict) and "error" in order_book:
                logger.error(f"获取订单簿失败: {order_book['error']}")
                return None, None

            bids = order_book.get('bids', [])
            asks = order_book.get('asks', [])
            if not bids or not asks:
                return None, None

            highest_bid = float(bids[-1][0]) if bids else None
            lowest_ask = float(asks[0][0]) if asks else None

            return highest_bid, lowest_ask

        return bid_price, ask_price

    def calculate_prices(self) -> Tuple[Optional[List[float]], Optional[List[float]]]:
        """
        计算买卖订单价格（完整迁移自 MarketMaker.calculate_prices）

        Returns:
            (buy_prices, sell_prices) 或 (None, None) 失败时
        """
        try:
            bid_price, ask_price = self.get_market_depth()
            if bid_price is None or ask_price is None:
                current_price = self.get_current_price()
                if current_price is None:
                    logger.error("无法获取价格信息，无法设置订单")
                    return None, None
                mid_price = current_price
            else:
                mid_price = (bid_price + ask_price) / 2

            logger.info(f"市场中间价: {mid_price}")

            # 使用基础价差，先计算基础买卖价以保持原始日志语义
            spread_percentage = self.context.base_spread_percentage
            exact_spread = mid_price * (spread_percentage / 100)
            base_buy_price = round_to_tick_size(mid_price - (exact_spread / 2), self.context.tick_size)
            base_sell_price = round_to_tick_size(mid_price + (exact_spread / 2), self.context.tick_size)
            actual_spread = base_sell_price - base_buy_price
            actual_spread_pct = (actual_spread / mid_price) * 100
            logger.info(f"使用的价差: {actual_spread_pct:.4f}% (目标: {spread_percentage}%), 绝对价差: {actual_spread}")

            # 委托组件计算阶梯价格
            buy_prices, sell_prices = compute_price_levels(
                mid_price,
                spread_percentage,
                self.context.max_orders,
                self.context.tick_size,
            )

            if not buy_prices or not sell_prices:
                logger.error("无法计算订单价格，返回空结果")
                return None, None

            final_spread = sell_prices[0] - buy_prices[0]
            final_spread_pct = (final_spread / mid_price) * 100
            logger.info(
                f"最终价差: {final_spread_pct:.4f}% (最低卖价 {sell_prices[0]} - 最高买价 {buy_prices[0]} = {final_spread})"
            )

            logger.debug("买单价位梯度: %s", buy_prices)
            logger.debug("卖单价位梯度: %s", sell_prices)
            return buy_prices, sell_prices

        except Exception as e:
            logger.error(f"计算价格时出错: {str(e)}")
            return None, None

    def get_price_levels(self, mid_price: float) -> Tuple[List[float], List[float]]:
        """
        获取价格层（买单价格从高到低，卖单价格从低到高）
        简化版本，直接调用 compute_price_levels

        Args:
            mid_price: 中间价

        Returns:
            (buy_prices, sell_prices)
        """
        return compute_price_levels(
            mid_price=mid_price,
            spread_pct=self.context.base_spread_percentage,
            max_orders=self.context.max_orders,
            tick_size=self.context.tick_size,
        )