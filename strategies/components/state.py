"""
MMContext 共享上下文与状态数据模型
用于组件间共享依赖与运行期状态，避免组件直接耦合 MarketMaker
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class MMContext:
    """
    做市商共享上下文，承载不变依赖与运行期引用

    不变依赖：client, db, symbol, 精度参数等
    运行期引用：活跃订单列表、统计字段引用等
    """
    # 不变依赖
    client: Any  # 交易所客户端
    db: Any  # 数据库实例
    symbol: str
    base_asset: str
    quote_asset: str
    base_precision: int
    quote_precision: int
    min_order_size: float
    tick_size: float

    # 配置参数
    base_spread_percentage: float
    max_orders: int
    rebalance_threshold: float
    enable_rebalance: bool
    base_asset_target_percentage: float
    quote_asset_target_percentage: float
    exchange: str

    # 运行期引用（由 MarketMaker 管理，组件访问）
    active_buy_orders: List[Dict[str, Any]] = field(default_factory=list)
    active_sell_orders: List[Dict[str, Any]] = field(default_factory=list)

    # 统计字段引用（由 StatsRecorder 更新）
    session_buy_trades: List[tuple] = field(default_factory=list)
    session_sell_trades: List[tuple] = field(default_factory=list)
    session_fees: float = 0.0
    session_maker_buy_volume: float = 0.0
    session_maker_sell_volume: float = 0.0
    session_taker_buy_volume: float = 0.0
    session_taker_sell_volume: float = 0.0

    # 累计交易统计
    total_bought: float = 0.0
    total_sold: float = 0.0
    buy_trades: List[tuple] = field(default_factory=list)
    sell_trades: List[tuple] = field(default_factory=list)
    total_profit: float = 0.0
    trades_executed: int = 0
    orders_placed: int = 0
    orders_cancelled: int = 0

    # 交易量与手续费
    maker_buy_volume: float = 0.0
    maker_sell_volume: float = 0.0
    taker_buy_volume: float = 0.0
    taker_sell_volume: float = 0.0
    total_fees: float = 0.0

    # WebSocket 引用（可选）
    ws: Optional[Any] = None
    ws_proxy: Optional[str] = None