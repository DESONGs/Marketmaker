import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from strategies.components.pricing import compute_price_levels
from strategies.components.stats import (
    calculate_session_profit,
    calculate_average_buy_cost,
)
from strategies.components.order_ops import cancel_orders_diff


class FakeClient:
    def __init__(self):
        self._open_orders = [
            {"id": "1", "side": "Bid"},
            {"id": "2", "side": "Ask", "reduceOnly": True},
            {"orderId": "3", "side": "Bid"},
        ]
        self.cancelled = []

    def get_open_orders(self, symbol):  # noqa: D401 - test double
        return list(self._open_orders)

    def cancel_order(self, order_id, symbol):  # noqa: D401 - test double
        self.cancelled.append(str(order_id))
        return {"id": order_id}


class ComponentTests(unittest.TestCase):
    def test_compute_price_levels_monotonic(self):
        buys, sells = compute_price_levels(100.0, 0.2, 3, 0.1)
        self.assertEqual(len(buys), 3)
        self.assertEqual(len(sells), 3)
        self.assertTrue(all(buys[i] > buys[i + 1] for i in range(len(buys) - 1)))
        self.assertTrue(all(sells[i] < sells[i + 1] for i in range(len(sells) - 1)))
        self.assertLess(buys[0], 100.0)
        self.assertGreater(sells[0], 100.0)

    def test_calculate_session_profit(self):
        buys = [(10.0, 1.0), (11.0, 1.0)]
        sells = [(12.0, 1.0), (13.0, 0.5)]
        profit = calculate_session_profit(buys, sells)
        # 12-10 for 1 + 13-11 for 0.5 = 2 + 1 = 3
        self.assertAlmostEqual(profit, 3.0)

    def test_calculate_average_buy_cost_with_fallback(self):
        buys = [(10.0, 1.0)]
        sells = [(11.0, 1.0)]
        avg_cost = calculate_average_buy_cost(buys, sells, fallback_bid=9.5)
        self.assertAlmostEqual(avg_cost, 9.5)

    def test_cancel_orders_diff_skips_reduce_only(self):
        client = FakeClient()
        cancelled = cancel_orders_diff(client, "SOLUSDT")
        self.assertEqual(cancelled, 2)
        self.assertListEqual(sorted(client.cancelled), ["1", "3"])


if __name__ == "__main__":
    unittest.main()
