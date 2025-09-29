"""
Lightweight taker executor used by PerpetualMarketMaker.

This module focuses on near-best-price IOC placement with basic guards.
The goal is to minimize churn and keep behavior predictable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, List
import time

from utils.helpers import round_to_precision, round_to_tick_size
from logger import setup_logger
from strategies.components.order_ops import build_limit_order as _cmp_build_limit_order

logger = setup_logger("taker_executor")


@dataclass
class TakerConfig:
    symbol: str
    base_precision: int
    tick_size: float
    slippage_bps: float = 3.0
    slice_count: int = 1


@dataclass
class OrderAttempt:
    side: str
    quantity: float
    price: float
    status: str
    error: Optional[str] = None
    order_id: str = ""
    latency_ms: float = 0.0
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None
    raw_result: Optional[Dict[str, Any]] = None


class TakerExecutor:
    def __init__(self, client, cfg: TakerConfig):
        self.client = client
        self.cfg = cfg

    def _best_bid_ask(self) -> Tuple[Optional[float], Optional[float]]:
        ob = self.client.get_order_book(self.cfg.symbol)
        try:
            # 处理Apex API响应格式
            if ob.get("error"):
                logger.error(f"获取盘口失败: {ob.get('error')}")
                return None, None

            data = ob.get("data", ob)  # Apex可能包装在data字段中

            # Apex API返回格式: {"a": [...], "b": [...]} 而不是 {"bids": [...], "asks": [...]}
            # "b"表示买单(bids), "a"表示卖单(asks)
            bids = data.get("b", data.get("bids", [])) if isinstance(data, dict) else []
            asks = data.get("a", data.get("asks", [])) if isinstance(data, dict) else []

            # Apex的bids通常是降序排列，取第一个就是最高买价
            # asks通常是升序排列，取第一个就是最低卖价
            best_bid = float(bids[0][0]) if bids else None
            best_ask = float(asks[0][0]) if asks else None
            return best_bid, best_ask
        except Exception as e:
            logger.error(f"读取盘口失败: {e}")
            return None, None

    def _price_with_slippage(self, side: str, best_bid: float, best_ask: float) -> Optional[float]:
        if best_bid is None or best_ask is None:
            return None
        s = float(self.cfg.slippage_bps) / 10000.0
        if side == "Bid":
            raw = best_ask * (1.0 + s)
        else:
            raw = best_bid * (1.0 - s)
        return round_to_tick_size(raw, self.cfg.tick_size)

    def submit_ioc(self, side: str, quantity: float) -> OrderAttempt:
        best_bid, best_ask = self._best_bid_ask()
        price = self._price_with_slippage(side, best_bid, best_ask)
        if price is None:
            return OrderAttempt(
                side=side,
                quantity=0.0,
                price=0.0,
                status="book_unavailable",
                error="无法获取盘口",
                best_bid=best_bid,
                best_ask=best_ask,
            )

        qty = round_to_precision(quantity, self.cfg.base_precision)
        order = _cmp_build_limit_order(
            self.cfg.symbol,
            side,
            price,
            qty,
            time_in_force="IOC",
            post_only=False,
        )
        start = time.perf_counter()
        res = self.client.execute_order(order)
        latency_ms = (time.perf_counter() - start) * 1000.0

        status = "accepted"
        error = None
        order_id = ""
        if isinstance(res, dict):
            if res.get("error"):
                status = "error"
                error = str(res.get("error"))
            else:
                order_id = str(res.get("id") or res.get("orderId") or res.get("clientOrderId") or "")
                # IOC 未成交会立即返回 status/cumulative 字段，此处仅标记提交成功，等待后续回调确认
        else:
            order_id = str(res)

        return OrderAttempt(
            side=side,
            quantity=qty,
            price=price,
            status=status,
            error=error,
            order_id=order_id,
            latency_ms=latency_ms,
            best_bid=best_bid,
            best_ask=best_ask,
            raw_result=res if isinstance(res, dict) else None,
        )

    def run_sliced(self, side: str, total_quantity: float) -> List[OrderAttempt]:
        slices = max(1, int(self.cfg.slice_count))
        qty = max(0.0, float(total_quantity)) / slices
        results: List[OrderAttempt] = []
        for i in range(slices):
            result = self.submit_ioc(side, qty)
            if result.status != "accepted":
                logger.warning(f"IOC 下单失败(切片 {i+1}/{slices}): {result.error}")
            results.append(result)
            # 简化：不引入冷却时间，尽快完成切片下单
        return results
