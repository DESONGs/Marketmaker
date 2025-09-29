from typing import Iterable, Optional, Set, Dict, Any
from logger import setup_logger

logger = setup_logger("order_ops")


def build_limit_order(
    symbol: str,
    side: str,
    price: float,
    quantity: float,
    *,
    time_in_force: str = "GTC",
    post_only: Optional[bool] = None,
    reduce_only: Optional[bool] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """构建标准限价单 payload，统一字符串化与标志位设置。"""

    order: Dict[str, Any] = {
        "orderType": "Limit",
        "price": str(price),
        "quantity": str(quantity),
        "side": side,
        "symbol": symbol,
        "timeInForce": time_in_force.upper(),
    }

    if post_only is not None:
        order["postOnly"] = bool(post_only)
    if reduce_only is not None:
        order["reduceOnly"] = bool(reduce_only)

    if extra:
        order.update(extra)

    return order


def cancel_orders_diff(client, symbol: str, keep_ids: Optional[Iterable[str]] = None) -> int:
    """
    差分撤单：仅撤掉不在 keep_ids 中且非 ReduceOnly 的订单。

    Args:
        client: 交易所客户端，需提供 `get_open_orders(symbol)` 与 `cancel_order(order_id, symbol)` 方法。
        symbol: 交易对。
        keep_ids: 保留的订单ID集合；None/空 表示撤掉所有非 ReduceOnly 的订单。

    Returns:
        实际取消成功的订单数量。
    """
    try:
        open_orders = client.get_open_orders(symbol)
        if isinstance(open_orders, dict) and "error" in open_orders:
            logger.error(f"获取开放订单失败: {open_orders['error']}")
            return 0

        keep: Set[str] = set(map(str, keep_ids or []))
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
                res = client.cancel_order(oid, symbol)
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
