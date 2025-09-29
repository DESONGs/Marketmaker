#!/usr/bin/env python3
"""
Apex Omni Taker策略运行脚本
支持BTC-USDT和ETH-USDT的真实订单提交
"""

import argparse
import sys
import time
from decimal import Decimal
from typing import Dict, List

from logger import setup_logger
from api.apex_omni_client import ApexOmniClient
from strategies.taker_executor import TakerExecutor, TakerConfig, OrderAttempt

logger = setup_logger("apex_taker")


def test_apex_connection(client: ApexOmniClient) -> bool:
    """测试Apex连接"""
    try:
        logger.info("测试Apex连接...")

        # 测试服务器时间
        server_time = client.get_server_time()
        if server_time.get('error'):
            logger.error(f"获取服务器时间失败: {server_time.get('error')}")
            return False

        logger.info(f"服务器时间: {server_time.get('data', {}).get('serverTime')}")

        # 测试账户信息
        account_info = client.get_account_info()
        if account_info.get('error'):
            logger.error(f"获取账户信息失败: {account_info.get('error')}")
            return False

        account_data = account_info.get('data', {})
        logger.info(f"账户ID: {account_data.get('accountId')}")
        logger.info(f"子账户ID: {account_data.get('subAccountId')}")

        # 测试市场信息
        markets = client.get_markets()
        if markets.get('error'):
            logger.error(f"获取市场信息失败: {markets.get('error')}")
            return False

        instruments = markets.get('data', {}).get('instruments', [])
        logger.info(f"可用交易对数量: {len(instruments)}")

        return True

    except Exception as e:
        logger.error(f"连接测试失败: {e}")
        return False


def get_symbol_config(client: ApexOmniClient, symbol: str) -> Dict:
    """获取交易对配置信息"""
    market_info = client.get_market_info(symbol)
    if not market_info:
        raise ValueError(f"无法获取 {symbol} 的市场信息")

    # 解析精度信息
    price_precision = int(market_info.get('pricePrecision', 2))
    qty_precision = int(market_info.get('qtyPrecision', 4))
    tick_size = float(market_info.get('tickSize', '0.01'))
    min_qty = float(market_info.get('minOrderSize', '0.001'))

    logger.info(f"{symbol} 交易配置:")
    logger.info(f"  价格精度: {price_precision}")
    logger.info(f"  数量精度: {qty_precision}")
    logger.info(f"  最小变动: {tick_size}")
    logger.info(f"  最小订单: {min_qty}")

    return {
        'symbol': symbol,
        'base_precision': qty_precision,
        'tick_size': tick_size,
        'min_qty': min_qty,
        'price_precision': price_precision
    }


def run_taker_simulation(
    client: ApexOmniClient,
    symbol: str,
    quantity: float,
    slippage_bps: float = 5.0,
    side: str = "Buy",
    slice_count: int = 1
) -> List[OrderAttempt]:
    """
    运行taker吃单模拟

    Args:
        client: Apex客户端
        symbol: 交易对
        quantity: 交易数量
        slippage_bps: 滑点基点
        side: 买卖方向 (Buy/Sell)
        slice_count: 切片数量

    Returns:
        订单执行结果列表
    """
    logger.info(f"开始 {symbol} taker策略模拟")
    logger.info(f"参数: 方向={side}, 数量={quantity}, 滑点={slippage_bps}bps, 切片={slice_count}")

    # 获取交易对配置
    config_data = get_symbol_config(client, symbol)

    # 创建taker配置
    taker_config = TakerConfig(
        symbol=symbol,
        base_precision=config_data['base_precision'],
        tick_size=config_data['tick_size'],
        slippage_bps=slippage_bps,
        slice_count=slice_count
    )

    # 创建taker执行器
    taker_executor = TakerExecutor(client, taker_config)

    # 检查最小订单量
    if quantity < config_data['min_qty']:
        logger.warning(f"订单量 {quantity} 小于最小值 {config_data['min_qty']}")
        quantity = config_data['min_qty']
        logger.info(f"调整订单量为: {quantity}")

    # 获取当前盘口
    order_book = client.get_order_book(symbol)
    if order_book.get('error'):
        logger.error(f"获取盘口失败: {order_book.get('error')}")
        return []

    book_data = order_book.get('data', {})
    bids = book_data.get('bids', [])
    asks = book_data.get('asks', [])

    if not bids or not asks:
        logger.error("盘口数据不完整")
        return []

    best_bid = float(bids[-1][0]) if bids else 0  # bids可能是升序排列
    best_ask = float(asks[0][0]) if asks else 0

    logger.info(f"当前盘口: bid={best_bid}, ask={best_ask}, spread={best_ask-best_bid:.6f}")

    # 执行切片订单
    if slice_count > 1:
        logger.info(f"执行切片下单，总量={quantity}, 切片数={slice_count}")
        results = taker_executor.run_sliced(side, quantity)
    else:
        logger.info(f"执行单笔下单，数量={quantity}")
        result = taker_executor.submit_ioc(side, quantity)
        results = [result]

    # 汇总结果
    total_qty = 0
    successful_orders = 0
    total_latency = 0

    for i, result in enumerate(results, 1):
        logger.info(f"订单 {i}: {result.status}")
        logger.info(f"  方向: {result.side}")
        logger.info(f"  数量: {result.quantity}")
        logger.info(f"  价格: {result.price}")
        logger.info(f"  延迟: {result.latency_ms:.2f}ms")

        if result.status == "accepted":
            successful_orders += 1
            total_qty += result.quantity
            total_latency += result.latency_ms
        elif result.error:
            logger.error(f"  错误: {result.error}")

    if successful_orders > 0:
        avg_latency = total_latency / successful_orders
        logger.info(f"执行汇总: {successful_orders}/{len(results)} 成功")
        logger.info(f"总成交量: {total_qty}")
        logger.info(f"平均延迟: {avg_latency:.2f}ms")
    else:
        logger.warning("所有订单都失败了")

    return results


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='Apex Omni Taker策略模拟')

    # 基本参数
    parser.add_argument('--account-label', type=str, help='账户标签 (从omni_config.json)')
    parser.add_argument('--account-index', type=int, help='账户索引 (默认0)')
    parser.add_argument('--test-connection', action='store_true', help='仅测试连接')

    # 交易参数
    parser.add_argument('--symbol', type=str, default='BTC-USDT',
                       choices=['BTC-USDT', 'ETH-USDT'], help='交易对')
    parser.add_argument('--side', type=str, default='Buy',
                       choices=['Buy', 'Sell'], help='买卖方向')
    parser.add_argument('--quantity', type=float, default=0.001, help='交易数量')
    parser.add_argument('--slippage', type=float, default=5.0, help='滑点基点')
    parser.add_argument('--slices', type=int, default=1, help='切片数量')

    # 模拟参数
    parser.add_argument('--rounds', type=int, default=1, help='执行轮数')
    parser.add_argument('--interval', type=int, default=10, help='轮次间隔(秒)')
    parser.add_argument('--both-symbols', action='store_true', help='同时测试BTC和ETH')

    args = parser.parse_args()

    try:
        # 创建客户端
        logger.info("初始化Apex客户端...")
        client = ApexOmniClient(
            account_label=args.account_label,
            account_index=args.account_index
        )

        # 测试连接
        if not test_apex_connection(client):
            logger.error("Apex连接测试失败")
            sys.exit(1)

        if args.test_connection:
            logger.info("连接测试成功，退出")
            return

        # 确定要交易的符号
        symbols = ['BTC-USDT', 'ETH-USDT'] if args.both_symbols else [args.symbol]

        # 执行交易模拟
        for round_num in range(1, args.rounds + 1):
            logger.info(f"=== 第 {round_num}/{args.rounds} 轮 ===")

            for symbol in symbols:
                logger.info(f"--- 处理 {symbol} ---")

                # 调整不同币种的默认数量
                if symbol == 'BTC-USDT':
                    default_qty = args.quantity if args.quantity != 0.001 else 0.001
                else:  # ETH-USDT
                    default_qty = args.quantity if args.quantity != 0.001 else 0.01

                results = run_taker_simulation(
                    client=client,
                    symbol=symbol,
                    quantity=default_qty,
                    slippage_bps=args.slippage,
                    side=args.side,
                    slice_count=args.slices
                )

                if not results:
                    logger.error(f"{symbol} 执行失败")
                    continue

                # 等待一下再处理下一个符号
                if len(symbols) > 1:
                    time.sleep(2)

            # 轮次间隔
            if round_num < args.rounds:
                logger.info(f"等待 {args.interval} 秒后进行下一轮...")
                time.sleep(args.interval)

        logger.info("所有交易模拟完成")

    except KeyboardInterrupt:
        logger.info("收到中断信号，正在退出...")
    except Exception as e:
        logger.error(f"执行过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()