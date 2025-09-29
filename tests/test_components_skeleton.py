"""
测试组件骨架初始化（PR-1 验证）
验证组件能正常创建，MMContext 传递正确
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from strategies.components.state import MMContext
from strategies.components.price_engine import PriceEngine
from strategies.components.orders import OrderManager
from strategies.components.inventory import InventoryBalancer
from strategies.components.stats_recorder import StatsRecorder
from strategies.components.ws_manager import WSManager
from strategies.components.dispatcher import OrderUpdateDispatcher
from strategies.components.risk import RiskManager
from strategies.components.runner import StrategyRunner


class FakeClient:
    """模拟交易所客户端"""
    def get_balance(self):
        return {}

    def get_collateral(self):
        return {"assets": []}

    def get_open_orders(self, symbol):
        return []

    def cancel_all_orders(self, symbol):
        return {"success": True}

    def cancel_order(self, order_id, symbol):
        return {"success": True}

    def get_ticker(self, symbol):
        return {"lastPrice": "100.0"}

    def get_order_book(self, symbol):
        return {"bids": [[99.0, 1.0]], "asks": [[101.0, 1.0]]}

    def execute_order(self, order_details):
        return {"id": "fake_order_id", "success": True}


class FakeDB:
    """模拟数据库"""
    def record_rebalance_order(self, order_id, symbol):
        pass

    def get_trading_stats(self, symbol, date):
        return []

    def get_order_history(self, symbol, limit=None):
        return []

    def update_trading_stats(self, stats_data):
        return True


class ComponentSkeletonTests(unittest.TestCase):
    def setUp(self):
        """创建测试用的 MMContext"""
        self.context = MMContext(
            client=FakeClient(),
            db=FakeDB(),
            symbol="SOL_USDC",
            base_asset="SOL",
            quote_asset="USDC",
            base_precision=8,
            quote_precision=6,
            min_order_size=0.1,
            tick_size=0.01,
            base_spread_percentage=0.2,
            max_orders=3,
            rebalance_threshold=15.0,
            enable_rebalance=True,
            base_asset_target_percentage=30.0,
            quote_asset_target_percentage=70.0,
            exchange="backpack",
        )

    def test_price_engine_init(self):
        """测试 PriceEngine 初始化"""
        engine = PriceEngine(self.context)
        self.assertIsNotNone(engine)
        self.assertEqual(engine.context, self.context)

    def test_order_manager_init(self):
        """测试 OrderManager 初始化"""
        manager = OrderManager(self.context)
        self.assertIsNotNone(manager)
        self.assertEqual(manager.context, self.context)

    def test_inventory_balancer_init(self):
        """测试 InventoryBalancer 初始化"""
        balancer = InventoryBalancer(self.context)
        self.assertIsNotNone(balancer)
        self.assertEqual(balancer.context, self.context)

    def test_stats_recorder_init(self):
        """测试 StatsRecorder 初始化"""
        recorder = StatsRecorder(self.context)
        self.assertIsNotNone(recorder)
        self.assertEqual(recorder.context, self.context)

    def test_ws_manager_init(self):
        """测试 WSManager 初始化"""
        ws_mgr = WSManager(self.context)
        self.assertIsNotNone(ws_mgr)
        self.assertEqual(ws_mgr.context, self.context)

    def test_order_dispatcher_init(self):
        """测试 OrderUpdateDispatcher 初始化"""
        dispatcher = OrderUpdateDispatcher(self.context)
        self.assertIsNotNone(dispatcher)
        self.assertEqual(dispatcher.context, self.context)

    def test_risk_manager_init(self):
        """测试 RiskManager 初始化"""
        risk_mgr = RiskManager(self.context)
        self.assertIsNotNone(risk_mgr)
        self.assertEqual(risk_mgr.context, self.context)

    def test_strategy_runner_init(self):
        """测试 StrategyRunner 初始化"""
        runner = StrategyRunner(self.context)
        self.assertIsNotNone(runner)
        self.assertEqual(runner.context, self.context)

    def test_price_engine_get_price_levels(self):
        """测试 PriceEngine.get_price_levels 调用不报错"""
        engine = PriceEngine(self.context)
        buy_prices, sell_prices = engine.get_price_levels(100.0)
        self.assertEqual(len(buy_prices), 3)
        self.assertEqual(len(sell_prices), 3)

    def test_order_manager_methods_callable(self):
        """测试 OrderManager 骨架方法可调用"""
        manager = OrderManager(self.context)
        result = manager.place_grid([], [], 1.0, 1.0)
        self.assertIsInstance(result, dict)
        manager.cancel_all()  # 返回 None
        result = manager.cancel_diff([])  # 参数调整为 keep_ids
        self.assertIsInstance(result, int)

    def test_inventory_balancer_methods_callable(self):
        """测试 InventoryBalancer 骨架方法可调用"""
        balancer = InventoryBalancer(self.context)
        balances = balancer.get_balances()
        self.assertIsNotNone(balances)  # 现在返回 {}
        asset_balance = balancer.get_asset_balance("SOL")
        self.assertEqual(asset_balance, (0, 0))  # 返回 (可用, 总量)
        result = balancer.rebalance()
        self.assertFalse(result)  # 重平衡功能关闭时返回 False

    def test_stats_recorder_methods_callable(self):
        """测试 StatsRecorder 骨架方法可调用"""
        recorder = StatsRecorder(self.context)
        recorder.load_today_stats()
        recorder.load_recent_trades()
        profit = recorder.calculate_db_profit()
        self.assertEqual(profit, 0.0)
        recorder.flush_daily_stats()
        recorder.on_trade({})
        session_profit = recorder.get_session_profit()
        self.assertEqual(session_profit, 0.0)

    def test_ws_manager_methods_callable(self):
        """测试 WSManager 骨架方法可调用"""
        ws_mgr = WSManager(self.context)
        connected = ws_mgr.check_connection()
        self.assertTrue(connected)  # 骨架返回 True
        ws_mgr.recreate()
        ws_mgr.initialize_and_subscribe()
        ws_mgr.subscribe_orders()

    def test_risk_manager_evaluate(self):
        """测试 RiskManager.evaluate 可调用"""
        risk_mgr = RiskManager(self.context)
        result = risk_mgr.evaluate()
        self.assertIsInstance(result, dict)
        self.assertIn("status", result)
        self.assertEqual(result["status"], "ok")


if __name__ == "__main__":
    unittest.main()