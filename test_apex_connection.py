#!/usr/bin/env python3
"""
测试Apex连接和API响应
"""

from api.apex_simple_client import ApexSimpleClient
from logger import setup_logger
import json

logger = setup_logger("test_apex")

def test_apex_apis():
    """测试各种Apex API"""
    try:
        # 创建客户端
        client = ApexSimpleClient()

        print("=== 测试服务器时间 ===")
        server_time = client.get_server_time()
        print(f"服务器时间响应: {json.dumps(server_time, indent=2)}")

        print("\n=== 测试账户信息 ===")
        account_info = client.get_account_info()
        print(f"账户信息响应: {json.dumps(account_info, indent=2)}")

        print("\n=== 测试市场信息 ===")
        markets = client.get_markets()
        print(f"市场信息响应: {json.dumps(markets, indent=2)}")

        print("\n=== 测试订单簿 (BTC-USDT) ===")
        order_book = client.get_order_book("BTC-USDT")
        print(f"BTC-USDT订单簿: {json.dumps(order_book, indent=2)}")

        print("\n=== 测试订单簿 (BTCUSDT) ===")
        order_book2 = client.get_order_book("BTCUSDT")
        print(f"BTCUSDT订单簿: {json.dumps(order_book2, indent=2)}")

        print("\n=== 测试ticker (BTC-USDT) ===")
        ticker = client.get_ticker_24hr("BTC-USDT")
        print(f"BTC-USDT ticker: {json.dumps(ticker, indent=2)}")

    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_apex_apis()