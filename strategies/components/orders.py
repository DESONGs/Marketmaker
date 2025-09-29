"""
OrderManager: 下单/撤单管理
职责：并发下单、错误码处理、差分撤单
"""
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
import time
from strategies.components.state import MMContext
from logger import setup_logger

logger = setup_logger("order_manager")


class OrderManager:
    """订单管理器，负责下单与撤单操作"""

    def __init__(self, context: MMContext):
        self.context = context

    def place_grid(
        self,
        buy_prices: List[float],
        sell_prices: List[float],
        buy_quantity: float,
        sell_quantity: float,
    ) -> Dict[str, Any]:
        """
        放置网格订单（并发、POST_ONLY 重试、资金不足处理）
        迁移自 MarketMaker.place_limit_orders

        Args:
            buy_prices: 买单价格列表
            sell_prices: 卖单价格列表
            buy_quantity: 单笔买单数量
            sell_quantity: 单笔卖单数量

        Returns:
            下单结果统计 {"buy_count": int, "sell_count": int}
        """
        from strategies.components.order_ops import build_limit_order as _cmp_build_limit_order
        from utils.helpers import round_to_tick_size

        # 下买单 (并发处理)
        buy_futures = []

        def place_buy(price, qty):
            order = _cmp_build_limit_order(
                self.context.symbol,
                "Bid",
                price,
                qty,
                post_only=True,
                extra={
                    "autoLendRedeem": True,
                    "autoLend": True,
                },
            )
            res = self.context.client.execute_order(order)
            if isinstance(res, dict) and "error" in res and "POST_ONLY_TAKER" in str(res["error"]):
                logger.info("调整买单价格并重试...")
                order["price"] = str(round_to_tick_size(float(order["price"]) - self.context.tick_size, self.context.tick_size))
                res = self.context.client.execute_order(order)

            # 特殊处理资金不足错误
            if isinstance(res, dict) and "error" in res and "INSUFFICIENT_FUNDS" in str(res["error"]):
                logger.warning(f"买单资金不足，可能需要手动赎回抵押品或等待自动赎回生效")

            return qty, order["price"], res

        with ThreadPoolExecutor(max_workers=self.context.max_orders) as executor:
            for p in buy_prices:
                if len(buy_futures) >= self.context.max_orders:
                    break
                buy_futures.append(executor.submit(place_buy, p, buy_quantity))

        buy_order_count = 0
        for future in buy_futures:
            qty, p_used, res = future.result()
            if isinstance(res, dict) and "error" in res:
                logger.error(f"买单失败: {res['error']}")
            else:
                logger.info(f"买单成功: 价格 {p_used}, 数量 {qty}")
                self.context.active_buy_orders.append(res)
                # 更新统计
                if hasattr(self.context, 'orders_placed'):
                    self.context.orders_placed += 1
                buy_order_count += 1

        # 下卖单
        sell_futures = []

        def place_sell(price, qty):
            order = _cmp_build_limit_order(
                self.context.symbol,
                "Ask",
                price,
                qty,
                post_only=True,
                extra={
                    "autoLendRedeem": True,
                    "autoLend": True,
                },
            )
            res = self.context.client.execute_order(order)
            if isinstance(res, dict) and "error" in res and "POST_ONLY_TAKER" in str(res["error"]):
                logger.info("调整卖单价格并重试...")
                order["price"] = str(round_to_tick_size(float(order["price"]) + self.context.tick_size, self.context.tick_size))
                res = self.context.client.execute_order(order)

            # 特殊处理资金不足错误
            if isinstance(res, dict) and "error" in res and "INSUFFICIENT_FUNDS" in str(res["error"]):
                logger.warning(f"卖单资金不足，可能需要手动赎回抵押品或等待自动赎回生效")

            return qty, order["price"], res

        with ThreadPoolExecutor(max_workers=self.context.max_orders) as executor:
            for p in sell_prices:
                if len(sell_futures) >= self.context.max_orders:
                    break
                sell_futures.append(executor.submit(place_sell, p, sell_quantity))

        sell_order_count = 0
        for future in sell_futures:
            qty, p_used, res = future.result()
            if isinstance(res, dict) and "error" in res:
                logger.error(f"卖单失败: {res['error']}")
            else:
                logger.info(f"卖单成功: 价格 {p_used}, 数量 {qty}")
                self.context.active_sell_orders.append(res)
                # 更新统计
                if hasattr(self.context, 'orders_placed'):
                    self.context.orders_placed += 1
                sell_order_count += 1

        logger.info(f"共下单: {buy_order_count} 个买单, {sell_order_count} 个卖单")
        return {"buy_count": buy_order_count, "sell_count": sell_order_count}

    def cancel_all(self) -> None:
        """
        取消所有现有订单（迁移自 MarketMaker.cancel_existing_orders）

        功能：
        - 获取所有未成交订单
        - 优先批量取消，失败则并发逐个取消
        - 更新 active_buy_orders 和 active_sell_orders
        - 更新 mm_context.orders_cancelled 统计
        """
        open_orders = self.context.client.get_open_orders(self.context.symbol)

        if isinstance(open_orders, dict) and "error" in open_orders:
            logger.error(f"获取订单失败: {open_orders['error']}")
            return

        if not open_orders:
            logger.info("没有需要取消的现有订单")
            self.context.active_buy_orders.clear()
            self.context.active_sell_orders.clear()
            return

        logger.info(f"正在取消 {len(open_orders)} 个现有订单")

        try:
            # 尝试批量取消
            result = self.context.client.cancel_all_orders(self.context.symbol)

            if isinstance(result, dict) and "error" in result:
                logger.error(f"批量取消订单失败: {result['error']}")
                logger.info("尝试逐个取消...")

                # 初始化线程池
                with ThreadPoolExecutor(max_workers=5) as executor:
                    cancel_futures = []

                    # 提交取消订单任务
                    for order in open_orders:
                        order_id = order.get('id')
                        if not order_id:
                            continue

                        future = executor.submit(
                            self.context.client.cancel_order,
                            order_id,
                            self.context.symbol
                        )
                        cancel_futures.append((order_id, future))

                    # 处理结果
                    for order_id, future in cancel_futures:
                        try:
                            res = future.result()
                            if isinstance(res, dict) and "error" in res:
                                logger.error(f"取消订单 {order_id} 失败: {res['error']}")
                            else:
                                logger.info(f"取消订单 {order_id} 成功")
                                # 访问 mm_context 中的 orders_cancelled
                                if hasattr(self.context, 'orders_cancelled'):
                                    self.context.orders_cancelled += 1
                        except Exception as e:
                            logger.error(f"取消订单 {order_id} 时出错: {e}")
            else:
                logger.info("批量取消订单成功")
                # 访问 mm_context 中的 orders_cancelled
                if hasattr(self.context, 'orders_cancelled'):
                    self.context.orders_cancelled += len(open_orders)
        except Exception as e:
            logger.error(f"取消订单过程中发生错误: {str(e)}")

        # 等待一下确保订单已取消
        time.sleep(1)

        # 检查是否还有未取消的订单
        remaining_orders = self.context.client.get_open_orders(self.context.symbol)
        if remaining_orders and len(remaining_orders) > 0:
            logger.warning(f"警告: 仍有 {len(remaining_orders)} 个未取消的订单")
        else:
            logger.info("所有订单已成功取消")

        # 重置活跃订单列表
        self.context.active_buy_orders.clear()
        self.context.active_sell_orders.clear()

    def cancel_diff(self, keep_ids: Optional[List[str]] = None) -> int:
        """
        差分撤单：仅撤掉不在 keep_ids 中且非 ReduceOnly 的订单
        （迁移自 order_ops.cancel_orders_diff）

        Args:
            keep_ids: 保留的订单ID列表；None/空 表示撤掉所有非 ReduceOnly 的订单

        Returns:
            实际取消成功的订单数量
        """
        try:
            open_orders = self.context.client.get_open_orders(self.context.symbol)
            if isinstance(open_orders, dict) and "error" in open_orders:
                logger.error(f"获取开放订单失败: {open_orders['error']}")
                return 0

            keep = set(map(str, keep_ids or []))
            to_cancel = []
            for od in open_orders or []:
                oid = str(od.get('id') or od.get('orderId') or od.get('clientOrderId') or '')
                if not oid or oid in keep:
                    continue
                if od.get('reduceOnly') is True:
                    # 保留用于安全对冲/减仓的订单
                    continue
                to_cancel.append(oid)

            if not to_cancel:
                logger.info("差分撤单：无可撤订单")
                return 0

            logger.info(f"差分撤单：准备取消 {len(to_cancel)} 个订单")
            success = 0
            for oid in to_cancel:
                try:
                    res = self.context.client.cancel_order(oid, self.context.symbol)
                    if isinstance(res, dict) and res.get('error'):
                        logger.warning(f"取消订单失败: id={oid}, err={res.get('error')}")
                        continue
                    success += 1
                except Exception as e:
                    logger.warning(f"取消订单异常: id={oid}, err={e}")
                    continue

            logger.info(f"差分撤单完成：已取消 {success} 个订单")
            return success

        except Exception as e:
            logger.error(f"差分撤单异常: {e}")
            return 0

    def check_order_fills(self) -> None:
        """
        检查订单成交情况（迁移自 MarketMaker.check_order_fills）

        功能：
        - 获取当前未成交订单
        - 对比活跃订单列表,识别已成交订单
        - 更新 active_buy_orders 和 active_sell_orders
        - 记录成交日志
        """
        open_orders = self.context.client.get_open_orders(self.context.symbol)

        if isinstance(open_orders, dict) and ("error" in open_orders or "code" in open_orders):
            error_msg = open_orders.get('error', open_orders.get('msg', '未知错误'))
            logger.error(f"获取订单失败: {error_msg}")
            return

        # 获取当前所有订单ID
        current_order_ids = set()
        orders_data = open_orders

        # 处理可能的数据结构：{data: [orders]} 或直接 [orders]
        if isinstance(open_orders, dict) and 'data' in open_orders:
            orders_data = open_orders['data']

        if orders_data and isinstance(orders_data, list):
            for order in orders_data:
                if isinstance(order, dict):
                    order_id = order.get('id') or order.get('orderId')
                    if order_id:
                        current_order_ids.add(order_id)

        # 记录更新前的订单数量
        prev_buy_orders = len(self.context.active_buy_orders)
        prev_sell_orders = len(self.context.active_sell_orders)

        # 更新活跃订单列表
        active_buy_orders = []
        active_sell_orders = []

        if orders_data and isinstance(orders_data, list):
            for order in orders_data:
                if isinstance(order, dict):
                    if order.get('side') == 'Bid' or order.get('side') == 'BUY':
                        active_buy_orders.append(order)
                    elif order.get('side') == 'Ask' or order.get('side') == 'SELL':
                        active_sell_orders.append(order)

        # 检查买单成交
        filled_buy_orders = []
        for order in self.context.active_buy_orders:
            order_id = order.get('id')
            if order_id and order_id not in current_order_ids:
                price = float(order.get('price', 0))
                quantity = float(order.get('quantity', 0))
                logger.info(f"买单已成交: {price} x {quantity}")
                filled_buy_orders.append(order)

        # 检查卖单成交
        filled_sell_orders = []
        for order in self.context.active_sell_orders:
            order_id = order.get('id')
            if order_id and order_id not in current_order_ids:
                price = float(order.get('price', 0))
                quantity = float(order.get('quantity', 0))
                logger.info(f"卖单已成交: {price} x {quantity}")
                filled_sell_orders.append(order)

        # 更新活跃订单列表
        self.context.active_buy_orders.clear()
        self.context.active_buy_orders.extend(active_buy_orders)
        self.context.active_sell_orders.clear()
        self.context.active_sell_orders.extend(active_sell_orders)

        # 输出订单数量变化，方便追踪
        if prev_buy_orders != len(active_buy_orders) or prev_sell_orders != len(active_sell_orders):
            logger.info(f"订单数量变更: 买单 {prev_buy_orders} -> {len(active_buy_orders)}, 卖单 {prev_sell_orders} -> {len(active_sell_orders)}")

        logger.info(f"当前活跃订单: 买单 {len(self.context.active_buy_orders)} 个, 卖单 {len(self.context.active_sell_orders)} 个")