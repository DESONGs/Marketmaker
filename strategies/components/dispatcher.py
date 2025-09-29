"""
OrderUpdateDispatcher: 统一处理 WS 与轮询订单/成交事件
职责：标准化订单更新事件，分发给 StatsRecorder
"""
from typing import Dict, Any, Callable
from strategies.components.state import MMContext
from logger import setup_logger

logger = setup_logger("order_update_dispatcher")


class OrderUpdateDispatcher:
    """订单更新分发器，统一处理 WS 和轮询事件"""

    def __init__(self, context: MMContext):
        self.context = context

    def handle_ws_message(self, message: Dict[str, Any]) -> None:
        """
        处理 WebSocket 消息

        Args:
            message: WS 原始消息
        """
        logger.debug("OrderUpdateDispatcher.handle_ws_message 骨架调用")

    def handle_polled_update(self, order_data: Dict[str, Any]) -> None:
        """
        处理轮询获取的订单更新

        Args:
            order_data: 订单数据
        """
        logger.debug("OrderUpdateDispatcher.handle_polled_update 骨架调用")