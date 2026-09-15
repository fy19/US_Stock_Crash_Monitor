import unittest

from calibration import CRISIS_OBSERVATIONS, crisis_calibration_rows


class QQQCalibrationTests(unittest.TestCase):
    def test_all_historical_observations_produce_a_buy_stage(self):
        rows = crisis_calibration_rows()
        self.assertEqual(len(rows), len(CRISIS_OBSERVATIONS))
        self.assertTrue(all(row["buy_tranche"] != (0, 0) for row in rows))

    def test_each_crisis_has_separate_voo_and_qqq_observations(self):
        rows = crisis_calibration_rows()
        events = {row["event"] for row in rows}
        for event in events:
            assets = {row["asset"] for row in rows if row["event"] == event}
            self.assertEqual(assets, {"VOO", "QQQ"})

    def test_2022_uses_vix_for_voo_and_vxn_for_qqq(self):
        rows = [row for row in crisis_calibration_rows() if row["event"] == "2022 Tightening"]
        by_asset = {row["asset"]: row for row in rows}
        self.assertEqual(by_asset["VOO"]["volatility_status"], "Panic")
        self.assertEqual(by_asset["QQQ"]["volatility_status"], "Panic")
        self.assertEqual(by_asset["VOO"]["buy_stage"], "Bear market")
        self.assertEqual(by_asset["QQQ"]["buy_stage"], "Bear market")


if __name__ == "__main__":
    unittest.main()
