"""
InventoryBalancer: 余额聚合与 IOC 重平衡
职责：获取总余额（含抵押品）、执行 IOC 重平衡
"""
from typing import Dict, Any, Optional, Tuple
from strategies.components.state import MMContext
from logger import setup_logger
import traceback

logger = setup_logger("inventory_balancer")


def format_balance(value, decimals=8, threshold=1e-8) -> str:
    """格式化余额显示，避免科学记号"""
    if abs(value) < threshold:
        return "0.00000000"
    return f"{value:.{decimals}f}"


class InventoryBalancer:
    """库存平衡器，负责资产余额管理与重平衡"""

    def __init__(self, context: MMContext):
        self.context = context

    def get_balances(self) -> Optional[Dict[str, Any]]:
        """
        获取总余额，包含普通余额和抵押品余额（迁移自 MarketMaker.get_total_balance）

        Returns:
            总余额字典，失败返回 None
        """
        try:
            # 获取普通余额
            balances = self.context.client.get_balance()
            if isinstance(balances, dict) and "error" in balances:
                logger.error(f"获取普通余额失败: {balances['error']}")
                return None

            # 获取抵押品余额
            collateral = self.context.client.get_collateral()
            if isinstance(collateral, dict) and "error" in collateral:
                logger.warning(f"获取抵押品余额失败: {collateral['error']}")
                collateral_assets = []
            else:
                collateral_assets = collateral.get('assets') or collateral.get('collateral', [])

            # 初始化总余额字典
            total_balances = {}

            # 处理普通余额
            if isinstance(balances, dict):
                for asset, details in balances.items():
                    available = float(details.get('available', 0))
                    locked = float(details.get('locked', 0))
                    total_balances[asset] = {
                        'available': available,
                        'locked': locked,
                        'total': available + locked,
                        'collateral_available': 0,
                        'collateral_total': 0
                    }

            # 添加抵押品余额
            for item in collateral_assets:
                symbol = item.get('symbol', '')
                if symbol:
                    total_quantity = float(item.get('totalQuantity', 0))
                    available_quantity = float(item.get('availableQuantity', 0))

                    if symbol not in total_balances:
                        total_balances[symbol] = {
                            'available': 0,
                            'locked': 0,
                            'total': 0,
                            'collateral_available': available_quantity,
                            'collateral_total': total_quantity
                        }
                    else:
                        total_balances[symbol]['collateral_available'] = available_quantity
                        total_balances[symbol]['collateral_total'] = total_quantity

                    # 更新总可用量和总量
                    total_balances[symbol]['total_available'] = (
                        total_balances[symbol]['available'] +
                        total_balances[symbol]['collateral_available']
                    )
                    total_balances[symbol]['total_all'] = (
                        total_balances[symbol]['total'] +
                        total_balances[symbol]['collateral_total']
                    )

            # 确保所有资产都有total_available和total_all字段
            for asset in total_balances:
                if 'total_available' not in total_balances[asset]:
                    total_balances[asset]['total_available'] = total_balances[asset]['available']
                if 'total_all' not in total_balances[asset]:
                    total_balances[asset]['total_all'] = total_balances[asset]['total']

            return total_balances

        except Exception as e:
            logger.error(f"获取总余额时出错: {e}")
            traceback.print_exc()
            return None

    def get_asset_balance(self, asset: str) -> Tuple[float, float]:
        """
        获取指定资产的总可用余额（迁移自 MarketMaker.get_asset_balance）

        Args:
            asset: 资产名称

        Returns:
            (可用余额, 总余额)
        """
        total_balances = self.get_balances()
        if not total_balances or asset not in total_balances:
            return 0, 0  # 返回 (可用余额, 总余额)

        balance_info = total_balances[asset]
        available = balance_info.get('total_available', 0)
        total = balance_info.get('total_all', 0)

        # 格式化显示余额，避免科学记号
        normal_available = balance_info.get('available', 0)
        collateral_available = balance_info.get('collateral_available', 0)

        logger.debug(f"{asset} 余额详情: 普通可用={format_balance(normal_available)}, "
                    f"抵押品可用={format_balance(collateral_available)}, "
                    f"总可用={format_balance(available)}, 总量={format_balance(total)}")

        return available, total

    def rebalance(self) -> bool:
        """
        执行 IOC 重平衡（含 autoLendRedeem）
        迁移自 MarketMaker.rebalance_position

        Returns:
            是否成功重平衡
        """
        from strategies.components.order_ops import build_limit_order as _cmp_build_limit_order
        from utils.helpers import round_to_precision, round_to_tick_size

        # 检查重平功能是否开启
        if not self.context.enable_rebalance:
            logger.warning("重平功能已关闭，取消重平衡操作")
            return False

        logger.info("开始重新平衡仓位...")

        # 获取当前价格（通过 client 直接调用，避免循环依赖）
        # 注意：这里暂时直接使用 client，后续可优化
        ticker = self.context.client.get_ticker(self.context.symbol)
        if isinstance(ticker, dict) and "error" in ticker:
            logger.error(f"获取价格失败: {ticker['error']}")
            return False
        current_price = float(ticker.get('lastPrice', 0))
        if not current_price:
            logger.error("无法获取价格，无法重新平衡")
            return False

        # 获取市场深度
        order_book = self.context.client.get_order_book(self.context.symbol)
        if isinstance(order_book, dict) and "error" in order_book:
            bid_price = current_price * 0.998
            ask_price = current_price * 1.002
        else:
            bids = order_book.get('bids', [])
            asks = order_book.get('asks', [])
            bid_price = float(bids[-1][0]) if bids else current_price * 0.998
            ask_price = float(asks[0][0]) if asks else current_price * 1.002

        # 获取总可用余额（包含抵押品）
        base_available, base_total = self.get_asset_balance(self.context.base_asset)
        quote_available, quote_total = self.get_asset_balance(self.context.quote_asset)

        logger.info(f"基础资产: 可用 {format_balance(base_available)}, 总计 {format_balance(base_total)} {self.context.base_asset}")
        logger.info(f"报价资产: 可用 {format_balance(quote_available)}, 总计 {format_balance(quote_total)} {self.context.quote_asset}")

        # 计算总资产价值
        total_assets = quote_total + (base_total * current_price)
        ideal_base_value = total_assets * (self.context.base_asset_target_percentage / 100)
        actual_base_value = base_total * current_price

        logger.info(f"使用目标配置比例: {self.context.base_asset_target_percentage}% {self.context.base_asset} / {self.context.quote_asset_target_percentage}% {self.context.quote_asset}")

        # 判断需要买入还是卖出
        if actual_base_value > ideal_base_value:
            # 基础资产过多，需要卖出
            excess_value = actual_base_value - ideal_base_value
            quantity_to_sell = excess_value / current_price

            max_sellable = base_total * 0.95  # 保留5%作为缓冲，基于总余额
            quantity_to_sell = min(quantity_to_sell, max_sellable)
            quantity_to_sell = round_to_precision(quantity_to_sell, self.context.base_precision)

            if quantity_to_sell < self.context.min_order_size:
                logger.info(f"需要卖出的数量 {format_balance(quantity_to_sell)} 低于最小订单大小 {format_balance(self.context.min_order_size)}，不进行重新平衡")
                return False

            if quantity_to_sell > base_total:
                logger.warning(f"需要卖出 {format_balance(quantity_to_sell)} 但总余额只有 {format_balance(base_total)}，调整为总余额的90%")
                quantity_to_sell = round_to_precision(base_total * 0.9, self.context.base_precision)

            # 检查可用余额，如果为0则依靠自动赎回
            if base_available < quantity_to_sell:
                logger.info(f"可用余额 {format_balance(base_available)} 不足，需要卖出 {format_balance(quantity_to_sell)}，将依靠自动赎回功能")

            # 使用略低于当前买价的价格来快速成交
            sell_price = round_to_tick_size(bid_price * 0.999, self.context.tick_size)
            logger.info(f"执行重新平衡: 卖出 {format_balance(quantity_to_sell)} {self.context.base_asset} @ {format_balance(sell_price)}")

            # 构建订单
            order_details = _cmp_build_limit_order(
                self.context.symbol,
                "Ask",
                sell_price,
                quantity_to_sell,
                time_in_force="IOC",
                extra={
                    "autoLendRedeem": True,
                    "autoLend": True,
                },
            )

        elif actual_base_value < ideal_base_value:
            # 基础资产不足，需要买入
            deficit_value = ideal_base_value - actual_base_value
            quantity_to_buy = deficit_value / current_price

            # 计算需要的报价资产
            cost = quantity_to_buy * ask_price
            max_affordable_cost = quote_total * 0.95  # 基于总余额的95%
            max_affordable = max_affordable_cost / ask_price
            quantity_to_buy = min(quantity_to_buy, max_affordable)
            quantity_to_buy = round_to_precision(quantity_to_buy, self.context.base_precision)

            if quantity_to_buy < self.context.min_order_size:
                logger.info(f"需要买入的数量 {format_balance(quantity_to_buy)} 低于最小订单大小 {format_balance(self.context.min_order_size)}，不进行重新平衡")
                return False

            cost = quantity_to_buy * ask_price
            if cost > quote_total:
                logger.warning(f"需要 {format_balance(cost)} {self.context.quote_asset} 但总余额只有 {format_balance(quote_total)}，调整买入数量")
                quantity_to_buy = round_to_precision((quote_total * 0.9) / ask_price, self.context.base_precision)
                cost = quantity_to_buy * ask_price

            # 检查可用余额
            if quote_available < cost:
                logger.info(f"可用余额 {format_balance(quote_available)} {self.context.quote_asset} 不足，需要 {format_balance(cost)} {self.context.quote_asset}，将依靠自动赎回功能")

            # 使用略高于当前卖价的价格来快速成交
            buy_price = round_to_tick_size(ask_price * 1.001, self.context.tick_size)
            logger.info(f"执行重新平衡: 买入 {format_balance(quantity_to_buy)} {self.context.base_asset} @ {format_balance(buy_price)}")

            # 构建订单
            order_details = _cmp_build_limit_order(
                self.context.symbol,
                "Bid",
                buy_price,
                quantity_to_buy,
                time_in_force="IOC",
                extra={
                    "autoLendRedeem": True,
                    "autoLend": True,
                },
            )
        else:
            logger.info("仓位已经均衡，无需重新平衡")
            return False

        # 执行订单
        result = self.context.client.execute_order(order_details)

        if isinstance(result, dict) and "error" in result:
            logger.error(f"重新平衡订单执行失败: {result['error']}")
            return False
        else:
            logger.info(f"重新平衡订单执行成功")
            # 记录这是一个重平衡订单
            if 'id' in result:
                self.context.db.record_rebalance_order(result['id'], self.context.symbol)

        logger.info("仓位重新平衡完成")
        return True

    def need_rebalance(self) -> bool:
        """
        判断是否需要重平衡仓位（迁移自 MarketMaker.need_rebalance）

        Returns:
            是否需要重平衡
        """
        # 检查重平功能是否开启
        if not self.context.enable_rebalance:
            logger.debug("重平功能已关闭，跳过重平衡检查")
            return False

        logger.info("检查是否需要重平衡仓位...")

        # 获取当前价格 (需要从 PriceEngine 获取,这里通过 client)
        ticker = self.context.client.get_ticker(self.context.symbol)
        if isinstance(ticker, dict) and "error" in ticker:
            logger.warning("无法获取当前价格，跳过重平衡检查")
            return False
        current_price = float(ticker.get('lastPrice', 0))
        if not current_price:
            logger.warning("无法获取当前价格，跳过重平衡检查")
            return False

        # 获取基础资产和报价资产的总可用余额（包含抵押品）
        base_available, base_total = self.get_asset_balance(self.context.base_asset)
        quote_available, quote_total = self.get_asset_balance(self.context.quote_asset)

        logger.info(f"当前基础资产余额: 可用 {format_balance(base_available)} {self.context.base_asset}, 总计 {format_balance(base_total)} {self.context.base_asset}")
        logger.info(f"当前报价资产余额: 可用 {format_balance(quote_available)} {self.context.quote_asset}, 总计 {format_balance(quote_total)} {self.context.quote_asset}")

        # 计算总资产价值（以报价货币计算）
        total_assets = quote_total + (base_total * current_price)

        # 检查是否有足够资产进行重平衡
        min_asset_value = self.context.min_order_size * current_price * 10  # 最小资产要求
        if total_assets < min_asset_value:
            logger.info(f"总资产价值 {total_assets:.2f} {self.context.quote_asset} 过小，跳过重平衡检查")
            return False

        # 使用用户设定的目标比例
        ideal_base_value = total_assets * (self.context.base_asset_target_percentage / 100)
        actual_base_value = base_total * current_price

        # 计算偏差
        deviation_value = abs(actual_base_value - ideal_base_value)
        risk_exposure = (deviation_value / total_assets) * 100 if total_assets > 0 else 0

        logger.info(f"总资产价值: {total_assets:.2f} {self.context.quote_asset}")
        logger.info(f"目标配置比例: {self.context.base_asset_target_percentage}% {self.context.base_asset} / {self.context.quote_asset_target_percentage}% {self.context.quote_asset}")
        logger.info(f"理想基础资产价值: {ideal_base_value:.2f} {self.context.quote_asset}")
        logger.info(f"实际基础资产价值: {actual_base_value:.2f} {self.context.quote_asset}")
        logger.info(f"偏差: {deviation_value:.2f} {self.context.quote_asset}")
        logger.info(f"风险暴露比例: {risk_exposure:.2f}% (阈值: {self.context.rebalance_threshold}%)")

        need_rebalance = risk_exposure > self.context.rebalance_threshold
        logger.info(f"重平衡检查结果: {'需要重平衡' if need_rebalance else '不需要重平衡'}")

        return need_rebalance