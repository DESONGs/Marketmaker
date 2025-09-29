"""
Apex交易所客户端适配器
实现与现有MarketMakerForCrypto策略兼容的交易所接口
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal

from logger import setup_logger
from api.apex_simple_client import ApexSimpleClient
from utils.helpers import round_to_precision, round_to_tick_size

logger = setup_logger("apex_exchange_client")


class ApexExchangeClient:
    """Apex交易所客户端，兼容现有策略接口"""

    def __init__(self, account_label: Optional[str] = None, account_index: Optional[int] = None, **kwargs):
        """
        初始化Apex交易所客户端

        Args:
            account_label: 账户标签
            account_index: 账户索引
            **kwargs: 其他配置参数（兼容性）
        """
        self.client = ApexSimpleClient(account_label=account_label, account_index=account_index)
        self.exchange_name = "apex"

        # 缓存交易对信息
        self._symbol_info_cache = {}
        self._cache_ttl = 300  # 5分钟缓存

        logger.info(f"Apex交易所客户端初始化完成")

    def _get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """获取交易对信息（带缓存）"""
        if symbol in self._symbol_info_cache:
            cache_time, info = self._symbol_info_cache[symbol]
            if time.time() - cache_time < self._cache_ttl:
                return info

        # 获取最新信息
        info = self.client.get_market_info(symbol)
        if info:
            self._symbol_info_cache[symbol] = (time.time(), info)

        return info

    def get_account_info(self) -> Dict:
        """获取账户信息"""
        return self.client.get_account_info()

    def get_balances(self) -> List[Dict]:
        """获取余额信息"""
        return self.client.get_balances()

    def get_positions(self) -> Dict:
        """获取持仓信息"""
        return self.client.get_positions()

    def get_order_book(self, symbol: str) -> Dict:
        """获取订单簿"""
        apex_symbol = symbol.replace('-', '')
        return self.client.get_order_book(apex_symbol)

    def get_ticker(self, symbol: str) -> Dict:
        """获取ticker信息"""
        apex_symbol = symbol.replace('-', '')
        return self.client.get_ticker_24hr(apex_symbol)

    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float = None,
        time_in_force: str = "GTC",
        **kwargs
    ) -> Dict:
        """
        下单

        Args:
            symbol: 交易对
            side: 买卖方向 (buy/sell)
            order_type: 订单类型 (limit/market)
            quantity: 数量
            price: 价格
            time_in_force: 时效性
            **kwargs: 其他参数

        Returns:
            下单结果
        """
        # 标准化参数
        side = side.upper() if side.lower() in ['buy', 'sell'] else side
        if side.lower() == 'buy':
            side = 'BUY'
        elif side.lower() == 'sell':
            side = 'SELL'

        order_type = order_type.upper()
        if order_type.lower() == 'limit':
            order_type = 'LIMIT'
        elif order_type.lower() == 'market':
            order_type = 'MARKET'

        # 获取交易对精度信息
        symbol_info = self._get_symbol_info(symbol)
        if symbol_info:
            # 根据交易对精度调整数量和价格
            qty_precision = int(symbol_info.get('quantityPrecision', 4))
            price_precision = int(symbol_info.get('pricePrecision', 2))
            tick_size = float(symbol_info.get('tickSize', '0.01'))

            quantity = round_to_precision(quantity, qty_precision)
            if price:
                price = round_to_tick_size(price, tick_size)

        logger.info(f"下单 {symbol}: {side} {quantity} @ {price} ({order_type})")

        # 转换交易对格式
        apex_symbol = symbol.replace('-', '')

        return self.client.create_order_simple(
            symbol=apex_symbol,
            side=side,
            order_type=order_type,
            quantity=str(quantity),
            price=str(price) if price else "0",
            time_in_force=time_in_force
        )

    def execute_order(self, order_data: Dict) -> Dict:
        """
        执行订单（兼容现有策略接口）

        Args:
            order_data: 订单数据字典

        Returns:
            执行结果
        """
        return self.client.execute_order(order_data)

    def cancel_order(self, order_id: str, symbol: str) -> Dict:
        """取消订单"""
        apex_symbol = symbol.replace('-', '')
        return self.client.cancel_order(order_id, apex_symbol)

    def cancel_all_orders(self, symbol: Optional[str] = None) -> Dict:
        """取消所有订单"""
        apex_symbol = symbol.replace('-', '') if symbol else None
        return self.client.cancel_all_orders(apex_symbol)

    def get_open_orders(self, symbol: Optional[str] = None) -> Dict:
        """获取开放订单"""
        apex_symbol = symbol.replace('-', '') if symbol else None
        return self.client.get_open_orders(apex_symbol)

    def get_order_status(self, order_id: str, symbol: str) -> Dict:
        """获取订单状态"""
        # 这个方法可能需要额外实现
        logger.warning("get_order_status 方法需要根据Apex API进一步实现")
        return {"error": "方法未实现"}

    def get_trade_history(self, symbol: Optional[str] = None, limit: int = 100) -> Dict:
        """获取交易历史"""
        # 这个方法可能需要额外实现
        logger.warning("get_trade_history 方法需要根据Apex API进一步实现")
        return {"error": "方法未实现"}

    # 兼容性方法
    def get_server_time(self) -> Dict:
        """获取服务器时间"""
        return self.client.get_server_time()

    def test_connectivity(self) -> bool:
        """测试连接性"""
        try:
            server_time = self.get_server_time()
            if server_time.get('error'):
                logger.error(f"连接测试失败: {server_time.get('error')}")
                return False

            account_info = self.get_account_info()
            if account_info.get('error'):
                logger.error(f"账户信息获取失败: {account_info.get('error')}")
                return False

            logger.info("Apex连接测试成功")
            return True

        except Exception as e:
            logger.error(f"连接测试异常: {e}")
            return False

    def get_trading_rules(self, symbol: str) -> Dict:
        """获取交易规则"""
        symbol_info = self._get_symbol_info(symbol)
        if not symbol_info:
            return {"error": f"无法获取 {symbol} 的交易规则"}

        return {
            'symbol': symbol,
            'min_quantity': float(symbol_info.get('minOrderSize', '0.001')),
            'max_quantity': float(symbol_info.get('maxOrderSize', '1000000')),
            'quantity_precision': int(symbol_info.get('quantityPrecision', 4)),
            'price_precision': int(symbol_info.get('pricePrecision', 2)),
            'tick_size': float(symbol_info.get('tickSize', '0.01')),
            'min_price': float(symbol_info.get('minPrice', '0.01')),
            'max_price': float(symbol_info.get('maxPrice', '1000000'))
        }

    def get_market_limits(self, symbol: str) -> Optional[Dict]:
        """
        获取市场限制信息（兼容MarketMaker接口）

        Args:
            symbol: 交易对（支持BTC-USDT格式，自动转换为BTCUSDT）

        Returns:
            市场限制信息
        """
        # 转换交易对格式：BTC-USDT -> BTCUSDT
        apex_symbol = symbol.replace('-', '')

        symbol_info = self._get_symbol_info(apex_symbol)
        if not symbol_info:
            logger.error(f"无法获取 {symbol} (转换为 {apex_symbol}) 的市场信息")
            return None

        # 解析交易对名称
        if '-' in symbol:
            parts = symbol.split('-')
            base_asset, quote_asset = parts
        else:
            # 尝试从crossSymbolName解析
            cross_symbol = symbol_info.get('crossSymbolName', symbol)
            if cross_symbol.endswith('USDT'):
                base_asset = cross_symbol[:-4]
                quote_asset = 'USDT'
            elif cross_symbol.endswith('USDC'):
                base_asset = cross_symbol[:-4]
                quote_asset = 'USDC'
            else:
                base_asset = cross_symbol[:3]
                quote_asset = cross_symbol[3:]

        return {
            'symbol': symbol,
            'base_asset': base_asset,
            'quote_asset': quote_asset,
            'base_precision': int(symbol_info.get('quantityPrecision', 4)),
            'quote_precision': int(symbol_info.get('pricePrecision', 2)),
            'min_order_size': symbol_info.get('minOrderSize', '0.001'),
            'max_order_size': symbol_info.get('maxOrderSize', '1000000'),
            'tick_size': symbol_info.get('tickSize', '0.01'),
            'min_price': symbol_info.get('minPrice', '0.01'),
            'max_price': symbol_info.get('maxPrice', '1000000'),
            'status': symbol_info.get('status', 'TRADING')
        }


# 工厂函数，用于创建Apex客户端实例
def create_apex_exchange_client(
    account_label: Optional[str] = None,
    account_index: Optional[int] = None,
    **kwargs
) -> ApexExchangeClient:
    """
    创建Apex交易所客户端

    Args:
        account_label: 账户标签
        account_index: 账户索引
        **kwargs: 其他配置参数

    Returns:
        ApexExchangeClient实例
    """
    return ApexExchangeClient(
        account_label=account_label,
        account_index=account_index,
        **kwargs
    )