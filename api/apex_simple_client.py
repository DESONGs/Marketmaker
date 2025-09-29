"""
Apex Omni交易所简化客户端
使用基础HTTP请求实现，避免复杂依赖，专注于策略执行
"""
from __future__ import annotations

import time
import json
import hmac
import hashlib
import requests
from typing import Dict, List, Optional, Any, Tuple

from logger import setup_logger
from apex_config import load_apex_config, ApexConfig
from api.apex_zk_signer import create_apex_zk_signer, OrderSigningContext

logger = setup_logger("apex_simple_client")


class ApexSimpleClient:
    """Apex Omni交易所简化API客户端"""

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

        self.zk_signer = create_apex_zk_signer(
            self.config.account.zk,
            self.config.account.ethereum_address,
        )
        self._account_cache: Optional[Dict[str, Any]] = None
        self._account_cache_time = 0
        self._account_cache_ttl = 10

        logger.info(f"初始化Apex简化客户端完成")
        logger.info(f"账户标签: {self.config.account.label}")
        logger.info(f"账户ID: {self.config.account.account_id}")
        logger.info(f"网络ID: {self.config.network_id}")

        if not self.zk_signer:
            logger.warning("未创建ZK签名器，后续私有请求将无法通过zkKeys验证")

    def _setup_session(self):
        """设置HTTP会话"""
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'MarketMakerForCrypto-Apex/1.0'
        })

    def _sign_request(self, method: str, path: str, params: Dict = None, body: str = "") -> Dict[str, str]:
        """
        生成API请求签名（按照Apex官方算法）

        Args:
            method: HTTP方法
            path: API路径
            params: 查询参数
            body: 请求体

        Returns:
            包含签名的headers
        """
        import base64
        timestamp = str(int(time.time() * 1000))

        # 构建数据字符串（按照官方格式）
        data = params if params else {}
        sorted_items = sorted(data.items(), key=lambda x: x[0], reverse=False)
        data_string = '&'.join(f'{key}={value}' for key, value in sorted_items if value is not None)

        # 构建签名字符串：timestamp + method + path + dataString
        message_string = timestamp + method.upper() + path + data_string

        # 生成签名（按照官方算法）
        api_secret = self.config.account.api_key.get('secret', '')
        hashed = hmac.new(
            base64.standard_b64encode(api_secret.encode('utf-8')),
            msg=message_string.encode('utf-8'),
            digestmod=hashlib.sha256,
        )
        signature = base64.standard_b64encode(hashed.digest()).decode()

        return {
            'APEX-SIGNATURE': signature,
            'APEX-API-KEY': self.config.account.api_key.get('key', ''),
            'APEX-TIMESTAMP': timestamp,
            'APEX-PASSPHRASE': self.config.account.api_key.get('passphrase', '')
        }

    def _request(self, method: str, path: str, params: Dict = None, body: Dict = None, signed: bool = True) -> Dict:
        """
        发送API请求

        Args:
            method: HTTP方法
            path: API路径
            params: 查询参数
            body: 请求体
            signed: 是否需要签名

        Returns:
            API响应
        """
        # 对于GET请求，将参数附加到路径中（按照官方实现）
        request_path = path
        if method.upper() == 'GET' and params:
            param_string = '&'.join(f'{key}={value}' for key, value in params.items() if value is not None)
            if param_string:
                request_path = f"{path}?{param_string}"
            # GET请求不使用params作为data参数进行签名
            sign_params = {}
        else:
            sign_params = params if params else {}

        url = f"{self.config.http_base}{request_path}"
        body_str = json.dumps(body) if body else ""

        headers = {}
        if signed:
            headers.update(self._sign_request(method, request_path, sign_params, body_str))

        self.session.headers.update(headers)

        try:
            if method.upper() == 'GET':
                # GET请求的参数已经包含在URL中，不需要再传递params
                response = self.session.get(url, timeout=10)
            elif method.upper() == 'POST':
                response = self.session.post(url, params=params, data=body_str, timeout=10)
            elif method.upper() == 'DELETE':
                response = self.session.delete(url, params=params, data=body_str, timeout=10)
            else:
                raise ValueError(f"不支持的HTTP方法: {method}")

            response.raise_for_status()

            # 调试：检查响应内容
            logger.debug(f"API响应状态: {response.status_code}")
            logger.debug(f"API响应头: {dict(response.headers)}")
            logger.debug(f"API响应内容: {response.text[:200]}...")

            if not response.text.strip():
                return {"error": "空响应"}

            result = response.json()

            # 清理headers以避免下次请求受影响
            for key in list(self.session.headers.keys()):
                if key.startswith('APEX-'):
                    del self.session.headers[key]

            return result

        except Exception as e:
            logger.error(f"API请求失败 {method} {path}: {e}")
            return {"error": str(e)}

    def get_server_time(self) -> Dict:
        """获取服务器时间"""
        return self._request('GET', '/api/v1/time', signed=False)

    def get_account_info(self) -> Dict:
        """获取账户信息"""
        return self._request('GET', '/api/v3/account', signed=True)

    def get_positions(self) -> Dict:
        """获取持仓信息"""
        return self._request('GET', '/api/v3/positions', signed=True)

    def get_markets(self) -> Dict:
        """获取市场信息（带缓存）"""
        current_time = time.time()
        if (current_time - self._markets_cache_time) < self._cache_ttl and self._markets_cache:
            return self._markets_cache

        # 尝试多个可能的API路径
        for path in ['/api/v3/symbols', '/api/v1/symbols', '/api/v3/instruments']:
            markets = self._request('GET', path, signed=False)
            if not markets.get('error'):
                self._markets_cache = markets
                self._markets_cache_time = current_time
                return markets

        # 如果都失败，返回最后一个错误
        return markets

    def _get_account_data(self, refresh: bool = False) -> Dict[str, Any]:
        """获取并缓存账户详情的data部分。"""

        now = time.time()
        if not refresh and self._account_cache and (now - self._account_cache_time) < self._account_cache_ttl:
            return self._account_cache

        response = self._request('GET', '/api/v3/account', signed=True)
        if response.get('error'):
            raise ValueError(f"获取账户信息失败: {response['error']}")

        data = response.get('data', response)
        if not isinstance(data, dict):
            raise ValueError("账户信息响应格式异常")

        self._account_cache = data
        self._account_cache_time = now
        return data

    def _resolve_symbol_context(self, symbol: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Based on market configs return symbol and asset definitions."""

        markets = self.get_markets()
        if markets.get('error'):
            raise ValueError(f"获取市场配置失败: {markets['error']}")

        data = markets.get('data', markets) or {}
        symbol_config = self.get_market_info(symbol)
        if not symbol_config:
            raise ValueError(f"未找到交易对 {symbol} 的市场配置")

        contract_cfg = data.get('contractConfig', {})
        assets = contract_cfg.get('assets', [])
        settle_asset_id = symbol_config.get('settleAssetId')
        asset_config = None
        for asset in assets:
            if asset.get('token') == settle_asset_id:
                asset_config = asset
                break

        if asset_config is None:
            raise ValueError(f"未找到交易对 {symbol} 对应的资产配置")

        return symbol_config, asset_config

    def get_market_info(self, symbol: str) -> Optional[Dict]:
        """获取特定交易对的市场信息"""
        markets = self.get_markets()
        if markets.get('error'):
            logger.warning(f"获取市场信息失败: {markets.get('error')}")
            return None

        # 根据实际返回格式查找symbol信息
        data = markets.get('data', markets)

        # 专门查找永续合约（在contractConfig中）
        if 'contractConfig' in data:
            contract_config = data['contractConfig']
            if 'perpetualContract' in contract_config:
                perp_contracts = contract_config['perpetualContract']
                for contract in perp_contracts:
                    # 检查crossSymbolName字段
                    cross_symbol = contract.get('crossSymbolName', '')
                    if cross_symbol == symbol:
                        logger.info(f"找到交易对 {symbol}: 最小订单={contract.get('minOrderSize')}, 最大订单={contract.get('maxOrderSize')}")
                        return contract

        # 尝试现货合约（在spotConfig中）
        if 'spotConfig' in data:
            spot_config = data['spotConfig']
            if 'spot' in spot_config:
                spot_contracts = spot_config['spot']
                for contract in spot_contracts:
                    if contract.get('symbol') == symbol or contract.get('crossSymbolName') == symbol:
                        logger.info(f"找到现货交易对 {symbol}")
                        return contract

        # 打印所有可用的交易对名称以便调试
        if 'contractConfig' in data and 'perpetualContract' in data['contractConfig']:
            available_symbols = [c.get('crossSymbolName', 'N/A') for c in data['contractConfig']['perpetualContract']]
            logger.warning(f"可用的永续合约交易对: {available_symbols[:10]}...")  # 只显示前10个

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
        params = {
            'symbol': symbol,
            'limit': depth
        }

        # 使用验证有效的API端点
        result = self._request('GET', '/api/v3/depth', params=params, signed=False)
        return result

    def get_ticker_24hr(self, symbol: str) -> Dict:
        """获取24小时ticker数据"""
        params = {'symbol': symbol}
        # 使用验证有效的API端点
        result = self._request('GET', '/api/v3/ticker', params=params, signed=False)
        return result

    def create_order_simple(self, symbol: str, side: str, order_type: str, quantity: str, price: str, time_in_force: str = "IOC") -> Dict:
        """
        创建订单（简化版本）

        Args:
            symbol: 交易对
            side: 买卖方向 (BUY/SELL)
            order_type: 订单类型 (LIMIT/MARKET)
            quantity: 数量
            price: 价格
            time_in_force: 时效性

        Returns:
            订单创建结果
        """
        if not self.zk_signer:
            error_msg = "ZK签名器未初始化，无法创建订单"
            logger.error(error_msg)
            return {"error": error_msg}

        try:
            symbol_cfg, asset_cfg = self._resolve_symbol_context(symbol)
            account_data = self._get_account_data()
        except ValueError as exc:
            logger.error(f"准备订单签名数据失败: {exc}")
            return {"error": str(exc)}

        contract_account = account_data.get('contractAccount', {})
        taker_fee_rate_value = contract_account.get('takerFeeRate')
        maker_fee_rate_value = contract_account.get('makerFeeRate')
        if taker_fee_rate_value is None or maker_fee_rate_value is None:
            error_msg = "账户信息缺少手续费率配置(takerFeeRate/makerFeeRate)"
            logger.error(error_msg)
            return {"error": error_msg}

        taker_fee_rate = str(taker_fee_rate_value)
        maker_fee_rate = str(maker_fee_rate_value)

        reduce_only = False

        order_payload = {
            'symbol': symbol,
            'side': side.upper(),
            'type': order_type.upper(),
            'size': str(quantity),
            'price': str(price),
            'timeInForce': time_in_force.upper(),
            'accountId': self.config.account.account_id,
            'subAccountId': self.config.account.sub_account_id,
            'reduceOnly': reduce_only,
        }
        order_payload['quantity'] = order_payload['size']

        signing_ctx = OrderSigningContext(
            symbol_config=symbol_cfg,
            asset_config=asset_cfg,
            account_id=self.config.account.account_id,
            sub_account_id=self.config.account.sub_account_id,
            taker_fee_rate=taker_fee_rate,
            maker_fee_rate=maker_fee_rate,
            reduce_only=reduce_only,
        )

        try:
            signature_fields = self.zk_signer.sign_order_payload(
                ctx=signing_ctx,
                side=order_payload['side'],
                size=order_payload['size'],
                price=order_payload['price'],
            )
        except Exception as exc:
            logger.error(f"生成ZK签名失败: {exc}")
            return {"error": f"生成ZK签名失败: {exc}"}

        order_payload.update(signature_fields)

        logger.info(f"创建订单: {order_payload}")
        result = self._request('POST', '/api/v3/order', body=order_payload, signed=True)

        if result.get('error'):
            logger.error(f"订单创建失败: {result.get('error')}")
        else:
            logger.info(f"订单创建成功: {result}")

        return result

    def execute_order(self, order_data: Dict) -> Dict:
        """
        执行订单（统一接口，兼容现有策略）

        Args:
            order_data: 包含symbol, side, quantity, price等的订单数据

        Returns:
            执行结果
        """
        return self.create_order_simple(
            symbol=order_data['symbol'],
            side=order_data['side'],
            order_type=order_data.get('orderType', 'LIMIT'),
            quantity=order_data['quantity'],
            price=order_data['price'],
            time_in_force=order_data.get('timeInForce', 'IOC')
        )

    def cancel_order(self, order_id: str, symbol: str) -> Dict:
        """取消订单"""
        params = {
            'orderId': order_id,
            'symbol': symbol
        }
        return self._request('DELETE', '/api/v3/order', params=params, signed=True)

    def get_open_orders(self, symbol: Optional[str] = None) -> Dict:
        """获取开放订单"""
        params = {}
        if symbol:
            params['symbol'] = symbol
        return self._request('GET', '/api/v3/open-orders', params=params, signed=True)

    def cancel_all_orders(self, symbol: Optional[str] = None) -> Dict:
        """取消所有订单"""
        params = {}
        if symbol:
            params['symbol'] = symbol
        return self._request('DELETE', '/api/v3/open-orders', params=params, signed=True)

    def get_balances(self) -> List[Dict]:
        """获取余额信息"""
        account_info = self.get_account_info()
        if account_info.get('error'):
            return []

        data = account_info.get('data', account_info)
        return data.get('balances', [])


# 为兼容现有代码结构，提供统一的客户端工厂函数
def create_apex_simple_client(account_label: Optional[str] = None, account_index: Optional[int] = None) -> ApexSimpleClient:
    """创建Apex简化客户端实例"""
    return ApexSimpleClient(account_label=account_label, account_index=account_index)
