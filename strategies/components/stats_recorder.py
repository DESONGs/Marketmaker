"""
StatsRecorder: 成交事件统计、会话利润计算、DB 持久化、日报落盘
职责：处理成交事件、更新统计、持久化到数据库
"""
from datetime import datetime
from typing import List, Tuple, Dict, Any
import traceback
from strategies.components.state import MMContext
from strategies.components.stats import calculate_session_profit as _cmp_calculate_session_profit
from strategies.components.stats import calculate_average_buy_cost as _cmp_calculate_average_buy_cost
from utils.helpers import calculate_volatility
from logger import setup_logger

logger = setup_logger("stats_recorder")


class StatsRecorder:
    """统计记录器，负责交易统计与数据持久化"""

    def __init__(self, context: MMContext):
        self.context = context
        self.session_start_time = datetime.now()

    def load_today_stats(self) -> None:
        """从数据库加载今日交易统计（迁移自 MarketMaker._load_trading_stats）"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')

            # 查询今天的统计数据
            stats = self.context.db.get_trading_stats(self.context.symbol, today)

            if stats and len(stats) > 0:
                stat = stats[0]
                # 访问 mm_context 中的统计字段
                if hasattr(self.context, 'maker_buy_volume'):
                    self.context.maker_buy_volume = stat['maker_buy_volume']
                    self.context.maker_sell_volume = stat['maker_sell_volume']
                    self.context.taker_buy_volume = stat['taker_buy_volume']
                    self.context.taker_sell_volume = stat['taker_sell_volume']
                    self.context.total_profit = stat['realized_profit']
                    self.context.total_fees = stat['total_fees']

                logger.info(f"已从数据库加载今日交易统计")
                logger.info(f"Maker买入量: {stat['maker_buy_volume']}, Maker卖出量: {stat['maker_sell_volume']}")
                logger.info(f"Taker买入量: {stat['taker_buy_volume']}, Taker卖出量: {stat['taker_sell_volume']}")
                logger.info(f"已实现利润: {stat['realized_profit']}, 总手续费: {stat['total_fees']}")
            else:
                logger.info("今日无交易统计记录，将创建新记录")
        except Exception as e:
            logger.error(f"加载交易统计时出错: {e}")

    def load_recent_trades(self) -> None:
        """从数据库加载最近交易记录（迁移自 MarketMaker._load_recent_trades）"""
        try:
            # 获取订单历史
            trades = self.context.db.get_order_history(self.context.symbol, 1000)
            trades_count = len(trades) if trades else 0

            if trades_count > 0:
                for side, quantity, price, maker, fee in trades:
                    quantity = float(quantity)
                    price = float(price)
                    fee = float(fee)

                    # 访问 mm_context 中的字段
                    if side == 'Bid':  # 买入
                        if hasattr(self.context, 'buy_trades'):
                            self.context.buy_trades.append((price, quantity))
                            self.context.total_bought += quantity
                            if maker:
                                self.context.maker_buy_volume += quantity
                            else:
                                self.context.taker_buy_volume += quantity
                    elif side == 'Ask':  # 卖出
                        if hasattr(self.context, 'sell_trades'):
                            self.context.sell_trades.append((price, quantity))
                            self.context.total_sold += quantity
                            if maker:
                                self.context.maker_sell_volume += quantity
                            else:
                                self.context.taker_sell_volume += quantity

                    if hasattr(self.context, 'total_fees'):
                        self.context.total_fees += fee

                logger.info(f"已从数据库载入 {trades_count} 条历史成交记录")
                if hasattr(self.context, 'total_bought'):
                    logger.info(f"总买入: {self.context.total_bought} {self.context.base_asset}, 总卖出: {self.context.total_sold} {self.context.base_asset}")
                    logger.info(f"Maker买入: {self.context.maker_buy_volume} {self.context.base_asset}, Maker卖出: {self.context.maker_sell_volume} {self.context.base_asset}")
                    logger.info(f"Taker买入: {self.context.taker_buy_volume} {self.context.base_asset}, Taker卖出: {self.context.taker_sell_volume} {self.context.base_asset}")

                # 计算精确利润
                profit = self.calculate_db_profit()
                if hasattr(self.context, 'total_profit'):
                    self.context.total_profit = profit
                logger.info(f"计算得出已实现利润: {profit:.8f} {self.context.quote_asset}")
                if hasattr(self.context, 'total_fees'):
                    logger.info(f"总手续费: {self.context.total_fees:.8f} {self.context.quote_asset}")
            else:
                logger.info("数据库中没有历史成交记录，将开始记录新的交易")

        except Exception as e:
            logger.error(f"载入历史成交记录时出错: {e}")
            traceback.print_exc()

    def calculate_db_profit(self) -> float:
        """计算数据库中的已实现利润（迁移自 MarketMaker._calculate_db_profit）"""
        try:
            # 获取订单历史，注意这里将返回一个列表
            order_history = self.context.db.get_order_history(self.context.symbol)
            if not order_history:
                return 0

            buy_trades = []
            sell_trades = []
            for side, quantity, price, maker, fee in order_history:
                if side == 'Bid':
                    buy_trades.append((float(price), float(quantity), float(fee)))
                elif side == 'Ask':
                    sell_trades.append((float(price), float(quantity), float(fee)))

            if not buy_trades or not sell_trades:
                return 0

            buy_queue = buy_trades.copy()
            total_profit = 0
            total_fees = 0

            for sell_price, sell_quantity, sell_fee in sell_trades:
                remaining_sell = sell_quantity
                total_fees += sell_fee

                while remaining_sell > 0 and buy_queue:
                    buy_price, buy_quantity, buy_fee = buy_queue[0]
                    matched_quantity = min(remaining_sell, buy_quantity)

                    trade_profit = (sell_price - buy_price) * matched_quantity
                    allocated_buy_fee = buy_fee * (matched_quantity / buy_quantity)
                    total_fees += allocated_buy_fee

                    net_trade_profit = trade_profit
                    total_profit += net_trade_profit

                    remaining_sell -= matched_quantity
                    if matched_quantity >= buy_quantity:
                        buy_queue.pop(0)
                    else:
                        remaining_fee = buy_fee * (1 - matched_quantity / buy_quantity)
                        buy_queue[0] = (buy_price, buy_quantity - matched_quantity, remaining_fee)

            # 更新 context 中的 total_fees
            if hasattr(self.context, 'total_fees'):
                self.context.total_fees = total_fees
            return total_profit

        except Exception as e:
            logger.error(f"计算数据库利润时出错: {e}")
            traceback.print_exc()
            return 0

    def flush_daily_stats(self) -> None:
        """刷新并持久化每日统计到数据库（迁移自 MarketMaker._update_trading_stats）"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')

            # 计算额外指标
            volatility = 0
            if self.context.ws and hasattr(self.context.ws, 'historical_prices'):
                volatility = calculate_volatility(self.context.ws.historical_prices)

            # 计算平均价差
            avg_spread = 0
            if self.context.ws and self.context.ws.bid_price and self.context.ws.ask_price:
                avg_spread = (self.context.ws.ask_price - self.context.ws.bid_price) / ((self.context.ws.ask_price + self.context.ws.bid_price) / 2) * 100

            # 准备统计数据
            stats_data = {
                'date': today,
                'symbol': self.context.symbol,
                'maker_buy_volume': getattr(self.context, 'maker_buy_volume', 0),
                'maker_sell_volume': getattr(self.context, 'maker_sell_volume', 0),
                'taker_buy_volume': getattr(self.context, 'taker_buy_volume', 0),
                'taker_sell_volume': getattr(self.context, 'taker_sell_volume', 0),
                'realized_profit': getattr(self.context, 'total_profit', 0),
                'total_fees': getattr(self.context, 'total_fees', 0),
                'net_profit': getattr(self.context, 'total_profit', 0) - getattr(self.context, 'total_fees', 0),
                'avg_spread': avg_spread,
                'trade_count': getattr(self.context, 'trades_executed', 0),
                'volatility': volatility
            }

            # 使用专门的函数来处理数据库操作
            def safe_update_stats():
                try:
                    success = self.context.db.update_trading_stats(stats_data)
                    if not success:
                        logger.warning("更新交易统计失败，下次再试")
                except Exception as db_err:
                    logger.error(f"更新交易统计时出错: {db_err}")

            # 直接在当前线程执行，避免过多的并发操作
            safe_update_stats()

        except Exception as e:
            logger.error(f"更新交易统计数据时出错: {e}")
            traceback.print_exc()

    def on_trade(self, trade_event: Dict[str, Any]) -> None:
        """
        处理成交事件（来自 WS 或轮询）

        Args:
            trade_event: 标准化的成交事件字典
        """
        logger.debug("StatsRecorder.on_trade 骨架调用")

    def get_session_profit(self) -> float:
        """获取本次会话利润（迁移自 MarketMaker._calculate_session_profit）"""
        if hasattr(self.context, 'session_buy_trades') and hasattr(self.context, 'session_sell_trades'):
            return _cmp_calculate_session_profit(
                self.context.session_buy_trades,
                self.context.session_sell_trades
            )
        return 0.0