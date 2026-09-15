import unittest

from model import MarketInputs, assess_market, volatility_status


def market(**overrides):
    values = {
        "ticker": "VOO",
        "current_price": 95.0,
        "peak_52w": 100.0,
        "sma_50": 94.0,
        "sma_200": 90.0,
        "volatility": 18.0,
        "volatility_peak_since_price_peak": 25.0,
        "cape": 25.0,
        "buffett_ratio": 120.0,
        "curve_inverted_24m": False,
        "real_fed_funds": 0.5,
        "sahm_rule": 0.0,
        "hy_oas": 3.0,
        "hy_oas_low_52w": 2.5,
        "hy_oas_delta_13w": 0.1,
        "nfci": -0.5,
        "nfci_delta_13w": 0.0,
        "equal_weight_ratio": 1.0,
        "equal_weight_sma_50": 0.99,
        "semi_ratio": None,
        "semi_ratio_sma_50": None,
    }
    values.update(overrides)
    return MarketInputs(**values)


class RegimeModelTests(unittest.TestCase):
    def test_voo_and_qqq_use_different_volatility_thresholds(self):
        self.assertEqual(volatility_status("VOO", 32.0), "Panic")
        self.assertEqual(volatility_status("QQQ", 32.0), "Stress")

    def test_escalation_gate_is_inactive_before_ten_percent_drawdown(self):
        result = assess_market(
            market(curve_inverted_24m=True, real_fed_funds=2.0, hy_oas=5.0),
            live_vol_percentile=30.0,
        )
        self.assertFalse(result.escalation_active)
        self.assertEqual(result.escalation_count, 0)

    def test_two_macro_signals_escalate_an_existing_correction(self):
        result = assess_market(
            market(
                current_price=88.0,
                curve_inverted_24m=True,
                real_fed_funds=2.0,
            ),
            live_vol_percentile=60.0,
        )
        self.assertTrue(result.escalation_active)
        self.assertEqual(result.escalation_count, 2)
        self.assertEqual(result.escalation_status, "Bear escalation")

    def test_high_volatility_and_drawdown_create_buy_not_sell_signal(self):
        result = assess_market(
            market(current_price=78.0, volatility=42.0, volatility_peak_since_price_peak=45.0),
            live_vol_percentile=97.0,
        )
        self.assertEqual(result.regime, "PANIC")
        self.assertEqual(result.buy_stage, "Extreme panic")
        self.assertEqual(result.buy_tranche, (15, 20))
        self.assertIn("staged-buy", result.action)

    def test_recession_confirmation_slows_panic_buying(self):
        result = assess_market(
            market(
                current_price=72.0,
                volatility=65.0,
                volatility_peak_since_price_peak=70.0,
                sahm_rule=0.7,
                hy_oas=7.0,
                hy_oas_low_52w=2.5,
                hy_oas_delta_13w=2.0,
            ),
            live_vol_percentile=99.0,
        )
        self.assertEqual(result.regime, "SYSTEMIC")
        self.assertTrue(result.recession_modifier)
        self.assertEqual(result.buy_tranche, (10, 15))

    def test_recovery_requires_two_of_three_confirmations(self):
        result = assess_market(
            market(
                current_price=88.0,
                sma_50=85.0,
                volatility=32.0,
                volatility_peak_since_price_peak=45.0,
                hy_oas_delta_13w=-0.1,
                equal_weight_ratio=1.01,
                equal_weight_sma_50=1.0,
            ),
            live_vol_percentile=80.0,
        )
        self.assertTrue(result.recovery_confirmed)
        self.assertEqual(result.regime, "RECOVERY")
        self.assertEqual(result.buy_tranche, (25, 30))

if __name__ == "__main__":
    unittest.main()
