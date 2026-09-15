# US Market Regime Monitor v2.3

A Streamlit dashboard that classifies the market regime for VOO (S&P 500) and QQQ (Nasdaq-100).

Version 2.3 removes the misleading single “Crash Risk Score” and the rule that higher stress should automatically lead to more selling. It separates risk build-up from an active drawdown and from contrarian buying during panic, with a dedicated QQQ structure and drawdown calibration.

## Decision architecture

1. **Risk Build-up Engine** — Is the market expensive, tightening and internally fragile?
2. **Escalation Gate** — Once drawdown reaches 10%, is the correction more likely to become a bear market?
3. **Panic Buy Engine** — During high volatility and a large drawdown, how much of a predefined reserve should be deployed?

## Five modules

| Module | Main inputs | Purpose |
|---|---|---|
| Valuation | CAPE, Buffett Indicator | Long-horizon valuation background; correlated measures get one vote |
| Recession | 10Y-3M, Sahm, credit/conditions confirmation | Separates a labor warning from recession confirmation |
| Monetary/Liquidity | Real Fed Funds, NFCI and 13-week change | Captures tightening bears such as 2018 and 2022 |
| Fragility | 50/200DMA; Nasdaq-100 breadth, QQQ/QQEW, SMH/QQQ and Top-10 weight for QQQ | Measures internal market deterioration |
| Panic/Stress | VIX/VXN, drawdown and HY OAS | Confirms stress and finds contrarian buying conditions |

The five modules are not averaged into a single score. Correlated indicators such as CAPE and the Buffett Indicator do not receive duplicate votes.

## Escalation Gate

The gate activates only after a **10% drawdown** from the 52-week high. It then checks:

- a 10Y-3M inversion within the prior 24 months;
- Real Fed Funds ≥ 1.5%;
- HY OAS at least 200bp above its 52-week low.

| Active signals | Classification |
|---:|---|
| 0 | Ordinary correction more likely |
| 1 | Watch |
| 2 | Bear Escalation |
| 3 | Severe Bear Risk |

These are v1 rules awaiting full backtest calibration, not event probabilities.

## Separate VOO and QQQ thresholds

VOO uses VIX. QQQ uses VXN and additionally monitors current-constituent Nasdaq-100 breadth, QQQ/QQEW, SMH/QQQ and mega-cap concentration. QQQ/QQEW and Top-10 weight form one concentration vote rather than two correlated votes.

| Asset | Normal | Watch | Stress | Panic | Extreme | Systemic |
|---|---:|---:|---:|---:|---:|---:|
| VOO / VIX | <20 | 20–25 | 25–30 | 30–40 | 40–60 | ≥60 |
| QQQ / VXN | <25 | 25–30 | 30–35 | 35–45 | 45–60 | ≥60 |

The live model combines these absolute thresholds with a five-year rolling percentile.

The drawdown ladder is also asset-specific:

| Asset | Initial | Deep Correction | Bear Market |
|---|---:|---:|---:|
| VOO | -10% | -15% | -20% |
| QQQ | -12% | -20% | -30% |

With other conditions held constant, an 18% drawdown therefore reaches Deep for VOO but only Initial for QQQ.

## Panic Buy Engine

All percentages refer to a separately predefined **Crash Reserve**, not the entire portfolio.

| Stage | Core condition | Reserve tranche |
|---|---|---:|
| Initial Correction | Asset-specific Initial drawdown + Stress | 10–15% |
| Deep Correction | Asset-specific Deep drawdown + Panic | 20% |
| Bear Market | Asset-specific Bear drawdown + Panic | 25% |
| Extreme Panic | VIX≥40 / VXN≥45 plus large drawdown | 15–20% |
| Recovery | Two of three recovery conditions | 25–30% |

When a Sahm labor warning is confirmed by credit or NFCI stress, the panic tranche slows to 10–15% to avoid exhausting reserves too early in a recessionary bear market.

Recovery requires two of: volatility having reached Panic during the current drawdown and then falling at least 20% from that peak, HY OAS no longer widening, and improving trend/equal-weight participation.

## Data

- Nasdaq: the current Nasdaq-100 security list.
- Yahoo Finance: VOO/QQQ prices, VIX/VXN, SPY/RSP, QQQ/QQEW, SMH/QQQ, constituent moving averages and QQQ holdings.
- FRED: DGS10, DGS3MO, FEDFUNDS, CPIAUCSL, SAHMREALTIME, BAMLH0A0HYM2 and NFCI.
- CAPE and the Buffett Indicator remain manual inputs so low-frequency data is not presented as real-time.

The dashboard clearly marks demo/fallback data. Do not use a fallback result for an investment decision.

## Install and run

```bash
git clone https://github.com/fy19/US_Stock_Crash_Monitor.git
cd US_Stock_Crash_Monitor
python -m pip install -r requirements.txt
streamlit run app.py
```

Run the model tests:

```bash
python -m unittest discover -s tests -v
```

## Current limitations

- Nasdaq-100 breadth uses actual constituent moving averages but the current constituent list. It is suitable for live diagnosis; historical use has survivorship bias and is not a point-in-time backtest.
- CAPE/Buffett 0–100 readings are transparent historical-range approximations; a full backtest should use point-in-time percentiles.
- A daily, look-ahead-free 1995–2026 backtest has not yet been completed.
- Free market and macro data may be delayed or revised.

The next milestone is a point-in-time Nasdaq-100 constituent history and Daily Backtest v1 with Precision, Recall, False Positive rate, Lead Time, Max Drawdown, CAGR and Sortino.

## Disclaimer

This project is for programming education and quantitative research only. It is not investment advice, and historical relationships do not guarantee future results.
