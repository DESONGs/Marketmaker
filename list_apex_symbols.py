#!/usr/bin/env python3
"""
列出Apex可用的交易对
"""

from api.apex_simple_client import ApexSimpleClient
from logger import setup_logger
import json

logger = setup_logger("list_symbols")

def list_apex_symbols():
    """列出Apex可用的交易对"""
    try:
        # 创建客户端
        client = ApexSimpleClient()

        print("=== 获取市场信息 ===")
        markets = client.get_markets()

        if markets.get('error'):
            print(f"错误: {markets.get('error')}")
            return

        print(f"原始响应结构: {list(markets.keys())}")
        data = markets.get('data', markets)
        print(f"数据结构: {list(data.keys()) if isinstance(data, dict) else type(data)}")

        print("\n=== 永续合约交易对 ===")
        if 'contractConfig' in data:
            contract_config = data['contractConfig']
            print(f"合约配置结构: {list(contract_config.keys()) if isinstance(contract_config, dict) else type(contract_config)}")

            if 'perpetualContract' in contract_config:
                perp_contracts = contract_config['perpetualContract']
                print(f"发现 {len(perp_contracts)} 个永续合约:")

                for i, contract in enumerate(perp_contracts[:10], 1):  # 只显示前10个
                    cross_symbol = contract.get('crossSymbolName', 'N/A')
                    enable_trade = contract.get('enableTrade', False)
                    min_order = contract.get('minOrderSize', 'N/A')
                    max_order = contract.get('maxOrderSize', 'N/A')

                    print(f"{i:2d}. {cross_symbol} (交易: {'是' if enable_trade else '否'})")
                    print(f"    最小订单: {min_order}, 最大订单: {max_order}")

                    if cross_symbol in ['BTCUSDT', 'ETHUSDT']:
                        print(f"    *** 详细信息: {json.dumps(contract, indent=2)}")

        print("\n=== 现货交易对 ===")
        spot_config = data.get('spotConfig', {})
        if 'spot' in spot_config:
            spot_contracts = spot_config['spot']
            print(f"发现 {len(spot_contracts)} 个现货交易对")

            for i, contract in enumerate(spot_contracts[:5], 1):  # 只显示前5个
                symbol = contract.get('symbol', 'N/A')
                print(f"{i:2d}. {symbol}")

    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    list_apex_symbols()