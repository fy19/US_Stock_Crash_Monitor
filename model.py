"""Pure decision logic for the US Market Regime Monitor.

The module deliberately keeps risk build-up, drawdown escalation and panic
buying separate.  Streamlit is only a presentation layer; these functions can
therefore be unit-tested and reused by a future backtest.
"""

from dataclasses import dataclass
from typing import Dict, Tuple


VOLATILITY_THRESHOLDS = {
    "VOO": (20.0, 25.0, 30.0, 40.0, 60.0),
    "QQQ": (25.0, 30.0, 35.0, 45.0, 60.0),
}

# QQQ normally moves more than VOO, so the same absolute drawdown must not
# automatically consume the same Crash Reserve tranche.
BUY_DRAWDOWN_THRESHOLDS = {
    "VOO": (-10.0, -15.0, -20.0),
    "QQQ": (-12.0, -20.0, -30.0),
}


@dataclass(frozen=True)
class MarketInputs:
    ticker: str
    current_price: float
    peak_52w: float
    sma_50: float
    sma_200: float
    volatility: float
    volatility_peak_since_price_peak: float
    cape: float
    buffett_ratio: float
    curve_inverted_24m: bool
    real_fed_funds: float
    sahm_rule: float
    hy_oas: float
    hy_oas_low_52w: float
    hy_oas_delta_13w: float
    nfci: float
    nfci_delta_13w: float
    cap_equal_ratio: float
    cap_equal_sma_50: float
    breadth_50_pct: float | None = None
    breadth_200_pct: float | None = None
    breadth_is_current_constituents: bool = True
    mega_cap_top10_pct: float | None = None
    semi_ratio: float | None = None
    semi_ratio_sma_50: float | None = None


@dataclass(frozen=True)
class ModuleResult:
    score: int
    status: str
    detail: str


@dataclass(frozen=True)
class Assessment:
    modules: Dict[str, ModuleResult]
    regime: str
    action: str
    drawdown_pct: float
    escalation_active: bool
    escalation_count: int
    escalation_status: str
    escalation_signals: Dict[str, bool]
    fragility_signals: Dict[str, bool]
    volatility_status: str
    volatility_percentile: float
    recovery_signals: Dict[str, bool]
    recovery_confirmed: bool
    buy_stage: str
    buy_tranche: Tuple[int, int]
    recession_modifier: bool


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def approximate_percentile(value: float, points: Tuple[Tuple[float, float], ...]) -> int:
    """Linearly interpolate a transparent historical-percentile approximation."""
    if value <= points[0][0]:
        return round(points[0][1])
    if value >= points[-1][0]:
        return round(points[-1][1])

    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= value <= x1:
            ratio = (value - x0) / (x1 - x0)
            return round(y0 + ratio * (y1 - y0))
    raise ValueError("percentile breakpoints must be sorted")


def drawdown_pct(current_price: float, peak_52w: float) -> float:
    if peak_52w <= 0:
        return 0.0
    return (current_price / peak_52w - 1.0) * 100.0


def volatility_status(ticker: str, value: float) -> str:
    watch, stress, panic, extreme, systemic = VOLATILITY_THRESHOLDS[ticker]
    if value >= systemic:
        return "Systemic"
    if value >= extreme:
        return "Extreme"
    if value >= panic:
        return "Panic"
    if value >= stress:
        return "Stress"
    if value >= watch:
        return "Watch"
    return "Normal"


def volatility_percentile(ticker: str, value: float) -> float:
    """Absolute-threshold percentile proxy used when a live history is unavailable."""
    watch, stress, panic, extreme, systemic = VOLATILITY_THRESHOLDS[ticker]
    anchors = ((0.0, 0.0), (watch, 50.0), (stress, 70.0), (panic, 85.0),
               (extreme, 95.0), (systemic, 99.0), (systemic * 1.5, 100.0))
    return float(approximate_percentile(value, anchors))


def _valuation(cape: float, buffett_ratio: float) -> ModuleResult:
    cape_pct = approximate_percentile(
        cape,
        ((10.0, 5.0), (15.0, 25.0), (20.0, 45.0), (25.0, 60.0),
         (30.0, 75.0), (35.0, 88.0), (40.0, 96.0), (44.0, 100.0)),
    )
    buffett_pct = approximate_percentile(
        buffett_ratio,
        ((60.0, 5.0), (80.0, 20.0), (100.0, 40.0), (120.0, 55.0),
         (150.0, 75.0), (180.0, 90.0), (200.0, 98.0), (220.0, 100.0)),
    )
    # CAPE and Buffett measure the same valuation risk source, so it gets one vote.
    score = max(cape_pct, buffett_pct)
    status = "Extreme" if score >= 90 else "Expensive" if score >= 75 else "Elevated" if score >= 55 else "Normal"
    return ModuleResult(score, status, f"CAPE≈P{cape_pct}; Buffett≈P{buffett_pct}; correlated pair counted once")


def _monetary(real_fed_funds: float, nfci: float, nfci_delta_13w: float) -> ModuleResult:
    rates_score = round(_clamp((real_fed_funds + 0.5) / 3.5 * 100.0))
    momentum_score = round(_clamp(nfci_delta_13w / 0.75 * 100.0))
    level_score = round(_clamp((nfci + 0.75) / 1.5 * 100.0))
    score = max(rates_score, round(0.7 * momentum_score + 0.3 * level_score))
    status = "Tight" if score >= 75 else "Rising pressure" if score >= 50 else "Watch" if score >= 35 else "Loose/Normal"
    return ModuleResult(score, status, f"Real Fed Funds {real_fed_funds:.2f}%; NFCI 13W Δ {nfci_delta_13w:+.2f}")


def _recession(inputs: MarketInputs) -> ModuleResult:
    credit_confirmation = (inputs.hy_oas - inputs.hy_oas_low_52w) >= 2.0
    conditions_confirmation = inputs.nfci_delta_13w >= 0.5
    confirmation = credit_confirmation or conditions_confirmation

    if inputs.sahm_rule >= 0.5 and confirmation:
        return ModuleResult(90, "Confirmed stress", "Sahm labor warning plus credit/financial-conditions confirmation")
    if inputs.sahm_rule >= 0.5:
        return ModuleResult(60, "Labor warning", "Sahm warning is not treated as recession confirmation by itself")
    if inputs.sahm_rule >= 0.3:
        return ModuleResult(45, "Watch", "Labor momentum is deteriorating")
    if inputs.curve_inverted_24m:
        return ModuleResult(35, "Background risk", "10Y-3M inversion occurred within the last 24 months")
    return ModuleResult(15, "Not confirmed", "No confirmed labor/credit recession signal")


def _fragility(inputs: MarketInputs) -> Tuple[ModuleResult, Dict[str, bool]]:
    breadth_floor_50 = 40.0 if inputs.ticker == "QQQ" else 45.0
    breadth_floor_200 = 50.0
    breadth_available = inputs.breadth_50_pct is not None and inputs.breadth_200_pct is not None
    breadth_weak = bool(
        breadth_available
        and (
            inputs.breadth_50_pct < breadth_floor_50
            or inputs.breadth_200_pct < breadth_floor_200
        )
    )

    # Cap/equal leadership and Top-10 weight describe the same concentration
    # risk source. They are deliberately combined into one vote.
    concentration_weak = inputs.cap_equal_ratio > inputs.cap_equal_sma_50 * 1.005
    if inputs.ticker == "QQQ" and inputs.mega_cap_top10_pct is not None:
        concentration_weak = concentration_weak or inputs.mega_cap_top10_pct >= 50.0

    votes = {
        "price_below_50dma": inputs.current_price < inputs.sma_50,
        "price_below_200dma": inputs.current_price < inputs.sma_200,
        "concentration_narrowing": concentration_weak,
    }
    if breadth_available:
        votes["breadth_weak"] = breadth_weak
    if inputs.ticker == "QQQ" and inputs.semi_ratio is not None and inputs.semi_ratio_sma_50 is not None:
        votes["semiconductors_weak"] = inputs.semi_ratio < inputs.semi_ratio_sma_50

    broken = sum(votes.values())
    score = round(broken / len(votes) * 100.0)
    status = "Broken" if score >= 75 else "Deteriorating" if score >= 50 else "Watch" if score > 0 else "Healthy"
    labels = [name for name, active in votes.items() if active]
    detail = ", ".join(labels) if labels else "Trend, breadth and participation are healthy"
    return ModuleResult(score, status, detail), votes


def _panic(inputs: MarketInputs, dd: float, live_vol_percentile: float | None) -> Tuple[ModuleResult, str, float]:
    vol_status = volatility_status(inputs.ticker, inputs.volatility)
    vol_pct = live_vol_percentile if live_vol_percentile is not None else volatility_percentile(inputs.ticker, inputs.volatility)
    drawdown_score = round(_clamp(abs(min(dd, 0.0)) / 30.0 * 100.0))
    credit_move = inputs.hy_oas - inputs.hy_oas_low_52w
    credit_score = round(_clamp(credit_move / 4.0 * 100.0))
    score = round(0.5 * vol_pct + 0.3 * drawdown_score + 0.2 * credit_score)
    status = "Systemic" if vol_status == "Systemic" else "Extreme" if vol_status == "Extreme" else "Panic" if vol_status == "Panic" else "Stress" if vol_status == "Stress" else "Watch" if vol_status == "Watch" else "Normal"
    return ModuleResult(score, status, f"{inputs.ticker} volatility={inputs.volatility:.1f}; drawdown={dd:.1f}%; HY vs 52W low={credit_move:+.2f}pp"), vol_status, vol_pct


def _escalation(inputs: MarketInputs, dd: float) -> Tuple[bool, Dict[str, bool], int, str]:
    active = dd <= -10.0
    signals = {
        "Yield curve": inputs.curve_inverted_24m,
        "Real rates": inputs.real_fed_funds >= 1.5,
        "Credit": (inputs.hy_oas - inputs.hy_oas_low_52w) >= 2.0,
    }
    count = sum(signals.values()) if active else 0
    if not active:
        status = "Inactive — drawdown is below 10%"
    elif count == 0:
        status = "Ordinary correction more likely"
    elif count == 1:
        status = "Watch"
    elif count == 2:
        status = "Bear escalation"
    else:
        status = "Severe bear risk"
    return active, signals, count, status


def _recovery(inputs: MarketInputs, dd: float) -> Tuple[Dict[str, bool], bool]:
    panic_threshold = VOLATILITY_THRESHOLDS[inputs.ticker][2]
    vol_reversal = (
        inputs.volatility_peak_since_price_peak >= panic_threshold
        and inputs.volatility <= inputs.volatility_peak_since_price_peak * 0.8
    )
    credit_stable = inputs.hy_oas_delta_13w <= 0.0
    participation_improving = (
        inputs.current_price >= inputs.sma_50
        and inputs.cap_equal_ratio <= inputs.cap_equal_sma_50
        and (inputs.breadth_50_pct is None or inputs.breadth_50_pct >= 50.0)
    )
    signals = {
        "Volatility down ≥20% from peak": vol_reversal,
        "HY OAS no longer widening": credit_stable,
        "Trend/participation improving": participation_improving,
    }
    return signals, dd <= -10.0 and sum(signals.values()) >= 2


def buy_decision(
    ticker: str,
    dd: float,
    vol_status: str,
    recovery_confirmed: bool = False,
    recession_confirmed: bool = False,
) -> Tuple[str, Tuple[int, int], bool]:
    if ticker not in BUY_DRAWDOWN_THRESHOLDS:
        raise ValueError("ticker must be VOO or QQQ")
    initial_dd, deep_dd, bear_dd = BUY_DRAWDOWN_THRESHOLDS[ticker]
    recession_modifier = recession_confirmed and vol_status in {"Panic", "Extreme", "Systemic"}
    if recovery_confirmed:
        return "Recovery confirmation", (25, 30), False
    if recession_modifier and dd <= initial_dd:
        return "Systemic/recession panic — slow tranche", (10, 15), True
    if dd <= initial_dd and vol_status in {"Extreme", "Systemic"}:
        return "Extreme panic", (15, 20), False
    if dd <= bear_dd and vol_status in {"Panic", "Extreme", "Systemic"}:
        return "Bear market", (25, 25), False
    if dd <= deep_dd and vol_status in {"Panic", "Extreme", "Systemic"}:
        return "Deep correction", (20, 20), False
    if dd <= initial_dd and vol_status in {"Stress", "Panic", "Extreme", "Systemic"}:
        return "Initial correction", (10, 15), False
    return "No panic-buy tranche", (0, 0), False


def assess_market(inputs: MarketInputs, live_vol_percentile: float | None = None) -> Assessment:
    if inputs.ticker not in VOLATILITY_THRESHOLDS:
        raise ValueError("ticker must be VOO or QQQ")

    dd = drawdown_pct(inputs.current_price, inputs.peak_52w)
    valuation = _valuation(inputs.cape, inputs.buffett_ratio)
    recession = _recession(inputs)
    monetary = _monetary(inputs.real_fed_funds, inputs.nfci, inputs.nfci_delta_13w)
    fragility, fragility_signals = _fragility(inputs)
    panic, vol_status, vol_pct = _panic(inputs, dd, live_vol_percentile)
    active, escalation_signals, escalation_count, escalation_status = _escalation(inputs, dd)
    recovery_signals, recovery_confirmed = _recovery(inputs, dd)

    recession_confirmed = recession.status == "Confirmed stress"
    buy_stage, buy_tranche, recession_modifier = buy_decision(
        inputs.ticker, dd, vol_status, recovery_confirmed, recession_confirmed
    )

    if recovery_confirmed:
        regime = "RECOVERY"
        action = "Panic is receding and participation is improving: deploy the final reserve tranche gradually."
    elif vol_status == "Systemic" and recession_confirmed:
        regime = "SYSTEMIC"
        action = "Systemic stress with recession confirmation: keep buying slowly; do not exhaust the reserve at once."
    elif dd <= -10.0 and vol_status in {"Panic", "Extreme", "Systemic"}:
        regime = "PANIC"
        action = "High volatility plus a large drawdown is a staged-buy signal, not an automatic sell signal."
    elif dd <= -10.0 or (fragility.score >= 50 and panic.score >= 50):
        regime = "BREAKDOWN"
        action = "Protect against uncontrolled high beta and use the Escalation Gate before increasing risk."
    elif fragility.score >= 50 and (valuation.score >= 75 or monetary.score >= 50):
        regime = "FRAGILE"
        action = "Keep core positions, avoid leverage and preserve the crash reserve."
    elif valuation.score >= 75:
        regime = "OVERHEATED"
        action = "The market is expensive without confirmed stress: do not chase, but valuation alone is not a sell signal."
    else:
        regime = "HEALTHY"
        action = "Maintain the long-term allocation and normal contribution plan."

    return Assessment(
        modules={
            "Valuation": valuation,
            "Recession": recession,
            "Monetary/Liquidity": monetary,
            "Fragility": fragility,
            "Panic/Stress": panic,
        },
        regime=regime,
        action=action,
        drawdown_pct=dd,
        escalation_active=active,
        escalation_count=escalation_count,
        escalation_status=escalation_status,
        escalation_signals=escalation_signals,
        fragility_signals=fragility_signals,
        volatility_status=vol_status,
        volatility_percentile=vol_pct,
        recovery_signals=recovery_signals,
        recovery_confirmed=recovery_confirmed,
        buy_stage=buy_stage,
        buy_tranche=buy_tranche,
        recession_modifier=recession_modifier,
    )
