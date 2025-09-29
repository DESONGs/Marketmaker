"""
StrategyRunner: 主循环编排
职责：调度策略主循环、抖动、优雅收尾
"""
from strategies.components.state import MMContext
from logger import setup_logger

logger = setup_logger("strategy_runner")


class StrategyRunner:
    """策略运行器，负责主循环编排"""

    def __init__(self, context: MMContext):
        self.context = context

    def run_loop(self) -> None:
        """
        运行策略主循环

        此方法将承载 MarketMaker.run 中的主循环逻辑
        """
        logger.debug("StrategyRunner.run_loop 骨架调用")
        logger.info("策略运行器骨架启动（待迁移实现）")