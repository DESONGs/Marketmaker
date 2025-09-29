"""
Apex Omni交易所客户端 - 基于apexpro库
使用官方apexpro库实现的统一交易接口
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional, Any
from decimal import Decimal

from logger import setup_logger
from apex_config import load_apex_config, ApexConfig

# 导入apexpro库
try:
    from apexomni.http_private_sign import HttpPrivateSign
    from apexomni.http_public import HttpPublic
    APEX_AVAILABLE = True
except ImportError as e:
    logger = setup_logger("apex_omni_client")
    logger.error(f"无法导入apexpro库: {e}")
    APEX_AVAILABLE = False

logger = setup_logger("apex_omni_client")


class ApexOmniClient:
    """Apex Omni交易所API客户端 - 基于官方apexpro库"""

    def __init__(self, account_label: Optional[str] = None, account_index: Optional[int] = None):
        """
        初始化Apex客户端

        Args:
            account_label: 账户标签，从omni_config.json中选择
            account_index: 账户索引，如果不指定标签则使用索引
        """
        if not APEX_AVAILABLE:
            raise ImportError("apexpro库未安装，请先安装: pip install apexpro")

        self.config = load_apex_config(
            account_label=account_label,
            account_index=account_index
        )

        # 初始化公共API客户端
        self.public_client = HttpPublic(host=self.config.http_base)

        # 初始化私有API客户端
        self.private_client = HttpPrivateSign(
            host=self.config.http_base,
            api_key_credentials={
                'key': self.config.account.api_key['key'],
                'secret': self.config.account.api_key['secret'],
                'passphrase': self.config.account.api_key['passphrase']
            }
        )

        logger.info(f"初始化Apex客户端完成")
        logger.info(f"账户标签: {self.config.account.label}")
        logger.info(f"账户ID: {self.config.account.account_id}")

    def get_server_time(self) -> Dict:
        """获取服务器时间"""
        try:
            response = self.public_client.server_time()
            return response.data if hasattr(response, 'data') else response
        except Exception as e:
            logger.error(f"获取服务器时间失败: {e}")
            return {"error": str(e)}

    def get_account_info(self) -> Dict:
        """获取账户信息"""
        try:
            response = self.private_client.get_account_v3()
            return response.data if hasattr(response, 'data') else response
        except Exception as e:
            logger.error(f"获取账户信息失败: {e}")
            return {"error": str(e)}

    def get_positions(self) -> Dict:
        """获取持仓信息"""
        try:
            response = self.private_client.get_positions()
            return response.data if hasattr(response, 'data') else response
        except Exception as e:
            logger.error(f"获取持仓信息失败: {e}")
            return {"error": str(e)}

    def get_markets(self) -> Dict:
        """获取市场信息"""
        try:
            response = self.public_client.configs_v3()
            return response.data if hasattr(response, 'data') else response
        except Exception as e:
            logger.error(f"获取市场信息失败: {e}")
            return {"error": str(e)}

    def get_market_info(self, symbol: str) -> Optional[Dict]:
        """获取特定交易对的市场信息"""
        markets = self.get_markets()
        if markets.get('error'):
            return None

        # Apex v3 configs返回的格式可能不同，先尝试找到symbol
        if isinstance(markets, dict):
            # 查找perpetualContract配置
            perp_contracts = markets.get('perpetualContract', [])
            for contract in perp_contracts:
                if contract.get('symbol') == symbol:
                    return contract

        logger.warning(f"未找到交易对 {symbol} 的市场信息")
        return None

    def get_order_book(self, symbol: str, depth: int = 20) -> Dict:
        """
        获取订单簿

        Args:
            symbol: 交易对
            depth: 深度

        Returns:
            订单簿数据
        """
        try:
            response = self.public_client.depth_v3(symbol=symbol, limit=depth)
            return response.data if hasattr(response, 'data') else response
        except Exception as e:
            logger.error(f"获取订单簿失败: {e}")
            return {"error": str(e)}

    def get_ticker_24hr(self, symbol: str) -> Dict:
        """获取24小时ticker数据"""
        try:
            response = self.public_client.get_ticker(symbol=symbol)
            return response.data if hasattr(response, 'data') else response
        except Exception as e:
            logger.error(f"获取ticker失败: {e}")
            return {"error": str(e)}

    def create_order(self, order_data: Dict) -> Dict:
        """
        创建订单

        Args:
            order_data: 订单数据

        Returns:
            订单创建结果
        """
        try:
            # 构建订单参数
            order_params = {
                'symbol': order_data['symbol'],
                'side': order_data['side'],
                'type': order_data.get('orderType', 'LIMIT'),
                'timeInForce': order_data.get('timeInForce', 'IOC'),
                'size': str(order_data['quantity']),
                'price': str(order_data['price']),
                'accountId': self.config.account.account_id,
                'subAccountId': self.config.account.sub_account_id
            }

            # 添加可选参数
            if 'reduceOnly' in order_data:
                order_params['reduceOnly'] = order_data['reduceOnly']

            logger.info(f"创建订单: {order_params}")
            response = self.private_client.create_order_v3(**order_params)
            return response.data if hasattr(response, 'data') else response

        except Exception as e:
            logger.error(f"创建订单失败: {e}")
            return {"error": str(e)}

    def execute_order(self, order_data: Dict) -> Dict:
        """
        执行订单（统一接口）

        Args:
            order_data: 订单数据

        Returns:
            执行结果
        """
        return self.create_order(order_data)

    def cancel_order(self, order_id: str, symbol: str) -> Dict:
        """
        取消订单

        Args:
            order_id: 订单ID
            symbol: 交易对

        Returns:
            取消结果
        """
        try:
            response = self.private_client.cancel_order(order_id=order_id)
            return response.data if hasattr(response, 'data') else response
        except Exception as e:
            logger.error(f"取消订单失败: {e}")
            return {"error": str(e)}

    def get_open_orders(self, symbol: Optional[str] = None) -> Dict:
        """
        获取开放订单

        Args:
            symbol: 可选的交易对过滤

        Returns:
            开放订单列表
        """
        try:
            kwargs = {}
            if symbol:
                kwargs['symbol'] = symbol

            response = self.private_client.get_open_orders(**kwargs)
            return response.data if hasattr(response, 'data') else response
        except Exception as e:
            logger.error(f"获取开放订单失败: {e}")
            return {"error": str(e)}

    def cancel_all_orders(self, symbol: Optional[str] = None) -> Dict:
        """
        取消所有订单

        Args:
            symbol: 可选的交易对过滤

        Returns:
            取消结果
        """
        try:
            kwargs = {}
            if symbol:
                kwargs['symbol'] = symbol

            response = self.private_client.cancel_all_order(**kwargs)
            return response.data if hasattr(response, 'data') else response
        except Exception as e:
            logger.error(f"取消所有订单失败: {e}")
            return {"error": str(e)}

    def get_balances(self) -> List[Dict]:
        """获取余额信息"""
        account_info = self.get_account_info()
        if account_info.get('error'):
            return []

        return account_info.get('balances', [])

    def get_fills(self, symbol: Optional[str] = None, limit: int = 100) -> Dict:
        """获取成交历史"""
        try:
            kwargs = {'limit': limit}
            if symbol:
                kwargs['symbol'] = symbol

            response = self.private_client.get_fills(**kwargs)
            return response.data if hasattr(response, 'data') else response
        except Exception as e:
            logger.error(f"获取成交历史失败: {e}")
            return {"error": str(e)}


# 为兼容现有代码结构，提供统一的客户端工厂函数
def create_apex_omni_client(account_label: Optional[str] = None, account_index: Optional[int] = None) -> ApexOmniClient:
    """创建Apex Omni客户端实例"""
    return ApexOmniClient(account_label=account_label, account_index=account_index)