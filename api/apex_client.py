"""
Apex Omni交易所客户端
基于apex_config.py配置实现的统一交易接口
"""
from __future__ import annotations

import time
import json
import hmac
import hashlib
import requests
import websocket
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urlencode

from logger import setup_logger
from apex_config import load_apex_config, ApexConfig

logger = setup_logger("apex_client")


class ApexClient:
    """Apex Omni交易所API客户端"""

    def __init__(self, account_label: Optional[str] = None, account_index: Optional[int] = None):
        """
        初始化Apex客户端

        Args:
            account_label: 账户标签，从omni_config.json中选择
            account_index: 账户索引，如果不指定标签则使用索引
        """
        self.config = load_apex_config(
            account_label=account_label,
            account_index=account_index
        )
        self.session = requests.Session()
        self._setup_session()

        # 缓存市场信息
        self._markets_cache = {}
        self._markets_cache_time = 0
        self._cache_ttl = 60  # 缓存60秒

    def _setup_session(self):
        """设置HTTP会话"""
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'MarketMakerForCrypto/1.0'
        })

    def _sign_request(self, method: str, path: str, params: Dict = None, body: str = "") -> Dict[str, str]:
        """
        生成API请求签名

        Args:
            method: HTTP方法
            path: API路径
            params: 查询参数
            body: 请求体

        Returns:
            包含签名的headers
        """
        timestamp = str(int(time.time() * 1000))

        # 构建查询字符串
        query_string = ""
        if params:
            query_string = urlencode(sorted(params.items()))

        # 构建签名字符串
        sign_string = f"{method}{path}"
        if query_string:
            sign_string += f"?{query_string}"
        sign_string += f"{timestamp}{body}"

        # 生成签名
        api_secret = self.config.account.api_key.get('secret', '')
        signature = hmac.new(
            api_secret.encode('utf-8'),
            sign_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return {
            'APEX-SIGNATURE': signature,
            'APEX-API-KEY': self.config.account.api_key.get('key', ''),
            'APEX-TIMESTAMP': timestamp,
            'APEX-PASSPHRASE': self.config.account.api_key.get('passphrase', '')
        }

    def _request(self, method: str, path: str, params: Dict = None, body: Dict = None) -> Dict:
        """
        发送API请求

        Args:
            method: HTTP方法
            path: API路径
            params: 查询参数
            body: 请求体

        Returns:
            API响应
        """
        url = f"{self.config.http_base}{path}"
        body_str = json.dumps(body) if body else ""

        headers = self._sign_request(method, path, params, body_str)
        self.session.headers.update(headers)

        try:
            if method.upper() == 'GET':
                response = self.session.get(url, params=params, timeout=10)
            elif method.upper() == 'POST':
                response = self.session.post(url, params=params, data=body_str, timeout=10)
            elif method.upper() == 'DELETE':
                response = self.session.delete(url, params=params, data=body_str, timeout=10)
            else:
                raise ValueError(f"不支持的HTTP方法: {method}")

            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"API请求失败 {method} {path}: {e}")
            return {"error": str(e)}

    def get_markets(self) -> Dict:
        """获取市场信息（带缓存）"""
        current_time = time.time()
        if (current_time - self._markets_cache_time) < self._cache_ttl and self._markets_cache:
            return self._markets_cache

        # 尝试不同的API路径
        for path in ['/api/v3/symbols', '/api/v1/symbols', '/api/v3/instruments', '/api/v1/instruments']:
            markets = self._request('GET', path)
            if not markets.get('error'):
                self._markets_cache = markets
                self._markets_cache_time = current_time
                return markets

        # 如果都失败，返回最后一个错误
        return markets

    def get_market_info(self, symbol: str) -> Optional[Dict]:
        """获取特定交易对的市场信息"""
        markets = self.get_markets()
        instruments = markets.get('data', {}).get('instruments', [])

        for instrument in instruments:
            if instrument.get('symbol') == symbol:
                return instrument

        logger.warning(f"未找到交易对 {symbol} 的市场信息")
        return None

    def get_account_info(self) -> Dict:
        """获取账户信息"""
        return self._request('GET', '/api/v3/account')

    def get_positions(self) -> Dict:
        """获取持仓信息"""
        return self._request('GET', '/api/v3/positions')

    def get_order_book(self, symbol: str, depth: int = 20) -> Dict:
        """
        获取订单簿

        Args:
            symbol: 交易对
            depth: 深度

        Returns:
            订单簿数据
        """
        params = {
            'symbol': symbol,
            'depth': depth
        }
        return self._request('GET', '/api/v3/depth', params=params)

    def create_order(self, order_data: Dict) -> Dict:
        """
        创建订单

        Args:
            order_data: 订单数据

        Returns:
            订单创建结果
        """
        return self._request('POST', self.config.rest_paths['create_order'], body=order_data)

    def cancel_order(self, order_id: str, symbol: str) -> Dict:
        """
        取消订单

        Args:
            order_id: 订单ID
            symbol: 交易对

        Returns:
            取消结果
        """
        params = {
            'orderId': order_id,
            'symbol': symbol
        }
        return self._request('DELETE', self.config.rest_paths['cancel_order'], params=params)

    def get_open_orders(self, symbol: Optional[str] = None) -> Dict:
        """
        获取开放订单

        Args:
            symbol: 可选的交易对过滤

        Returns:
            开放订单列表
        """
        params = {}
        if symbol:
            params['symbol'] = symbol

        return self._request('GET', self.config.rest_paths['open_orders'], params=params)

    def cancel_all_orders(self, symbol: Optional[str] = None) -> Dict:
        """
        取消所有订单

        Args:
            symbol: 可选的交易对过滤

        Returns:
            取消结果
        """
        params = {}
        if symbol:
            params['symbol'] = symbol

        return self._request('DELETE', self.config.rest_paths['cancel_all'], params=params)

    def execute_order(self, order_data: Dict) -> Dict:
        """
        执行订单（统一接口）

        Args:
            order_data: 订单数据

        Returns:
            执行结果
        """
        # 添加必要的账户信息
        order_data.update({
            'accountId': self.config.account.account_id,
            'subAccountId': self.config.account.sub_account_id
        })

        logger.info(f"提交订单: {order_data}")
        result = self.create_order(order_data)

        if result.get('error'):
            logger.error(f"订单提交失败: {result.get('error')}")
        else:
            logger.info(f"订单提交成功: {result}")

        return result

    def get_ticker_24hr(self, symbol: str) -> Dict:
        """获取24小时ticker数据"""
        params = {'symbol': symbol}
        return self._request('GET', '/api/v3/ticker/24hr', params=params)

    def get_balances(self) -> Dict:
        """获取余额信息"""
        account_info = self.get_account_info()
        return account_info.get('data', {}).get('balances', [])

    def get_server_time(self) -> Dict:
        """获取服务器时间"""
        return self._request('GET', self.config.rest_paths['server_time'])


# 为兼容现有代码结构，提供统一的客户端工厂函数
def create_apex_client(account_label: Optional[str] = None, account_index: Optional[int] = None) -> ApexClient:
    """创建Apex客户端实例"""
    return ApexClient(account_label=account_label, account_index=account_index)