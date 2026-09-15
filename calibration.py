"""Transparent event fixtures for the VOO/QQQ threshold audit.

The observations are peak-to-trough adjusted-close drawdowns and maximum
VIX/VXN readings inside the named event windows, downloaded from Yahoo Finance
on 2026-09-15. They are descriptive fixtures, not a point-in-time backtest.
"""

from dataclasses import dataclass

from model import buy_decision, volatility_status


@dataclass(frozen=True)
class CrisisObservation:
    event: str
    asset: str
    drawdown_pct: float
    volatility_peak: float


CRISIS_OBSERVATIONS = (
    CrisisObservation("2018 Q4", "VOO", -19.35, 36.07),
    CrisisObservation("2018 Q4", "QQQ", -22.70, 38.68),
    CrisisObservation("2020 COVID", "VOO", -33.72, 82.69),
    CrisisObservation("2020 COVID", "QQQ", -28.56, 80.08),
    CrisisObservation("2022 Tightening", "VOO", -24.50, 36.45),
    CrisisObservation("2022 Tightening", "QQQ", -34.77, 41.43),
)


def evaluate_observation(observation: CrisisObservation) -> dict[str, object]:
    status = volatility_status(observation.asset, observation.volatility_peak)
    stage, tranche, _ = buy_decision(observation.asset, observation.drawdown_pct, status)
    return {
        "event": observation.event,
        "asset": observation.asset,
        "drawdown_pct": observation.drawdown_pct,
        "volatility_peak": observation.volatility_peak,
        "volatility_status": status,
        "buy_stage": stage,
        "buy_tranche": tranche,
    }


def crisis_calibration_rows() -> list[dict[str, object]]:
    return [evaluate_observation(observation) for observation in CRISIS_OBSERVATIONS]
