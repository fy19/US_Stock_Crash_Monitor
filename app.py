"""Streamlit dashboard for the US Market Regime Monitor v2.3."""

from dataclasses import dataclass
from datetime import datetime, timedelta
import html
import json
import os
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from calibration import crisis_calibration_rows
from model import (
    BUY_DRAWDOWN_THRESHOLDS,
    MarketInputs,
    VOLATILITY_THRESHOLDS,
    assess_market,
)


GITHUB_URL = "https://github.com/fy19/US_Stock_Crash_Monitor"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"
NASDAQ_100_URL = "https://api.nasdaq.com/api/quote/list-type/nasdaq100"
UI_VERSION = "v2.3.0"


@dataclass
class MarketSnapshot:
    price_history: pd.DataFrame
    current_price: float
    peak_52w: float
    sma_50: float
    sma_200: float
    volatility: float
    volatility_peak_since_price_peak: float
    volatility_percentile_5y: float
    cap_equal_ratio: float
    cap_equal_sma_50: float
    breadth_50_pct: float | None
    breadth_200_pct: float | None
    breadth_constituent_count: int
    breadth_is_current_constituents: bool
    mega_cap_top10_pct: float | None
    mega_cap_is_fallback: bool
    semi_ratio: float | None
    semi_ratio_sma_50: float | None
    is_mock: bool


st.set_page_config(
    page_title="US Market Regime Monitor v2.3",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .regime-box {
        padding: 24px 26px;
        border-radius: 14px;
        color: #ffffff;
        margin: 10px 0 22px 0;
        box-shadow: 0 8px 24px rgba(15, 23, 42, 0.12);
    }
    .regime-box h2 {
        color: #ffffff !important;
        font-size: clamp(1.55rem, 2.5vw, 2rem) !important;
        line-height: 1.15 !important;
        margin: 0 0 12px 0 !important;
    }
    .regime-box div {color: #ffffff; font-size: 1.05rem; line-height: 1.6;}
    .summary-card, .module-card {
        background: #ffffff;
        border: 1px solid #d9e2ec;
        border-top: 5px solid var(--accent);
        border-radius: 12px;
        box-shadow: 0 4px 14px rgba(15, 23, 42, 0.07);
        color: #172033;
        width: 100%;
    }
    .summary-card {padding: 15px 16px 17px; min-height: 112px;}
    .module-card {padding: 15px 14px 14px; min-height: 210px;}
    .card-label {
        color: #526071;
        font-size: 0.9rem;
        font-weight: 650;
        line-height: 1.3;
        margin-bottom: 9px;
    }
    .summary-value {
        color: #111827;
        font-size: clamp(1.55rem, 2.2vw, 2rem);
        font-weight: 760;
        letter-spacing: -0.025em;
        line-height: 1.15;
    }
    .summary-meta, .module-score {
        color: #66758a;
        font-size: 0.78rem;
        line-height: 1.35;
        margin-top: 7px;
    }
    .status-row {
        align-items: center;
        color: #111827;
        display: flex;
        font-size: clamp(1.05rem, 1.45vw, 1.35rem);
        font-weight: 760;
        gap: 8px;
        line-height: 1.25;
        min-height: 42px;
        overflow-wrap: anywhere;
    }
    .status-dot {
        background: var(--accent);
        border-radius: 999px;
        box-shadow: 0 0 0 4px color-mix(in srgb, var(--accent) 16%, transparent);
        display: inline-block;
        flex: 0 0 11px;
        height: 11px;
        width: 11px;
    }
    .module-detail {
        border-top: 1px solid #edf1f5;
        color: #4b596b;
        font-size: 0.78rem;
        line-height: 1.5;
        margin-top: 12px;
        padding-top: 11px;
    }
    @media (max-width: 900px) {
        .module-card {min-height: 0; margin-bottom: 8px;}
        .summary-card {min-height: 0; margin-bottom: 6px;}
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _close(history: pd.DataFrame) -> pd.Series:
    if history.empty or "Close" not in history:
        raise ValueError("price history is empty")
    return history["Close"].dropna().astype(float)


@st.cache_data(ttl=3600, show_spinner=False)
def _history(symbol: str, period: str = "5y") -> pd.DataFrame:
    data = yf.Ticker(symbol).history(period=period, auto_adjust=True)
    if data.empty:
        raise ValueError(f"no data returned for {symbol}")
    return data


@st.cache_data(ttl=21600, show_spinner=False)
def _nasdaq100_symbols() -> list[str]:
    """Load the live Nasdaq-100 security list from Nasdaq's public endpoint."""
    request = Request(
        NASDAQ_100_URL,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
    )
    with urlopen(request, timeout=15) as response:
        payload = json.load(response)
    rows = payload.get("data", {}).get("data", {}).get("rows", [])
    symbols = sorted({row["symbol"].replace(".", "-") for row in rows if row.get("symbol")})
    if len(symbols) < 90:
        raise ValueError("Nasdaq-100 constituent response is incomplete")
    return symbols


def _close_matrix(download: pd.DataFrame) -> pd.DataFrame:
    if download.empty:
        raise ValueError("constituent price download is empty")
    if isinstance(download.columns, pd.MultiIndex):
        if "Close" in download.columns.get_level_values(0):
            close = download["Close"]
        elif "Close" in download.columns.get_level_values(1):
            close = download.xs("Close", axis=1, level=1)
        else:
            raise ValueError("bulk download has no Close field")
    elif "Close" in download:
        close = download[["Close"]]
    else:
        raise ValueError("bulk download has no Close field")
    return close.apply(pd.to_numeric, errors="coerce")


@st.cache_data(ttl=21600, show_spinner=False)
def get_nasdaq100_breadth() -> tuple[float | None, float | None, int]:
    """Current-constituent breadth; not a point-in-time historical backtest."""
    try:
        symbols = _nasdaq100_symbols()
        downloaded = yf.download(
            symbols,
            period="1y",
            auto_adjust=True,
            progress=False,
            threads=20,
            group_by="column",
            timeout=5,
        )
        close = _close_matrix(downloaded)
        above_50: list[bool] = []
        above_200: list[bool] = []
        for symbol in close.columns:
            series = close[symbol].dropna()
            if len(series) < 200:
                continue
            above_50.append(bool(series.iloc[-1] > series.tail(50).mean()))
            above_200.append(bool(series.iloc[-1] > series.tail(200).mean()))
        if len(above_200) < 70:
            raise ValueError("too few constituents have 200-day histories")
        return 100.0 * sum(above_50) / len(above_50), 100.0 * sum(above_200) / len(above_200), len(above_200)
    except Exception:
        return None, None, 0


@st.cache_data(ttl=21600, show_spinner=False)
def get_qqq_top10_weight() -> tuple[float, bool]:
    """Return QQQ Top-10 portfolio weight, with a disclosed research fallback."""
    try:
        holdings = yf.Ticker("QQQ").funds_data.top_holdings
        if holdings is None or holdings.empty:
            raise ValueError("QQQ holdings are unavailable")
        weight_column = next(
            column for column in holdings.columns if "holding" in str(column).lower() and "percent" in str(column).lower()
        )
        weights = pd.to_numeric(holdings[weight_column], errors="coerce").dropna().head(10)
        total = float(weights.sum())
        if total <= 1.5:
            total *= 100.0
        if not 20.0 <= total <= 80.0:
            raise ValueError("QQQ Top-10 weight is outside a plausible range")
        return total, False
    except Exception:
        # Invesco's published concentration discussion reports about 53%.
        # Keeping the flag makes this fallback visible in the dashboard.
        return 53.0, True


def _mock_snapshot(ticker: str) -> MarketSnapshot:
    rng = np.random.default_rng(22 if ticker == "QQQ" else 11)
    dates = pd.date_range(end=datetime.now(), periods=1260, freq="B")
    base = 350.0 if ticker == "QQQ" else 400.0
    returns = rng.normal(0.00035, 0.012 if ticker == "QQQ" else 0.009, len(dates))
    prices = base * np.exp(np.cumsum(returns))
    frame = pd.DataFrame(index=dates)
    frame["Close"] = prices
    frame["Open"] = frame["Close"] * (1 + rng.normal(0, 0.002, len(frame)))
    frame["High"] = frame[["Open", "Close"]].max(axis=1) * 1.004
    frame["Low"] = frame[["Open", "Close"]].min(axis=1) * 0.996
    frame["SMA_50"] = frame["Close"].rolling(50).mean()
    frame["SMA_200"] = frame["Close"].rolling(200).mean()
    current = float(frame["Close"].iloc[-1])
    vol = 27.0 if ticker == "QQQ" else 18.0
    return MarketSnapshot(
        price_history=frame,
        current_price=current,
        peak_52w=float(frame["Close"].tail(252).max()),
        sma_50=float(frame["SMA_50"].iloc[-1]),
        sma_200=float(frame["SMA_200"].iloc[-1]),
        volatility=vol,
        volatility_peak_since_price_peak=vol * 1.7,
        volatility_percentile_5y=55.0,
        cap_equal_ratio=1.0,
        cap_equal_sma_50=1.0,
        breadth_50_pct=55.0 if ticker == "QQQ" else None,
        breadth_200_pct=60.0 if ticker == "QQQ" else None,
        breadth_constituent_count=100 if ticker == "QQQ" else 0,
        breadth_is_current_constituents=ticker == "QQQ",
        mega_cap_top10_pct=53.0 if ticker == "QQQ" else None,
        mega_cap_is_fallback=ticker == "QQQ",
        semi_ratio=1.0 if ticker == "QQQ" else None,
        semi_ratio_sma_50=1.0 if ticker == "QQQ" else None,
        is_mock=True,
    )


@st.cache_data(ttl=3600, show_spinner=False)
def get_market_snapshot(ticker: str, proxy: str = "") -> MarketSnapshot:
    if os.getenv("US_MARKET_MONITOR_OFFLINE") == "1":
        return _mock_snapshot(ticker)
    try:
        if proxy:
            os.environ["http_proxy"] = proxy
            os.environ["https_proxy"] = proxy

        vol_symbol = "^VIX" if ticker == "VOO" else "^VXN"
        equal_symbol = "RSP" if ticker == "VOO" else "QQEW"
        benchmark_symbol = "SPY" if ticker == "VOO" else "QQQ"

        price_history = _history(ticker).copy()
        price_close = _close(price_history)
        price_history["SMA_50"] = price_close.rolling(50).mean()
        price_history["SMA_200"] = price_close.rolling(200).mean()

        vol_close = _close(_history(vol_symbol))
        equal_close = _close(_history(equal_symbol))
        benchmark_close = _close(_history(benchmark_symbol))
        ratio = pd.concat([equal_close, benchmark_close], axis=1, join="inner").dropna()
        ratio.columns = ["equal", "benchmark"]
        cap_equal_ratio = ratio["benchmark"] / ratio["equal"]

        semi_ratio = None
        semi_ratio_sma = None
        breadth_50 = None
        breadth_200 = None
        breadth_count = 0
        top10_weight = None
        top10_fallback = False
        if ticker == "QQQ":
            semi_close = _close(_history("SMH"))
            semi = pd.concat([semi_close, benchmark_close], axis=1, join="inner").dropna()
            semi.columns = ["semi", "benchmark"]
            semi_series = semi["semi"] / semi["benchmark"]
            semi_ratio = float(semi_series.iloc[-1])
            semi_ratio_sma = float(semi_series.rolling(50).mean().iloc[-1])
            breadth_50, breadth_200, breadth_count = get_nasdaq100_breadth()
            top10_weight, top10_fallback = get_qqq_top10_weight()

        price_peak_date = price_close.tail(252).idxmax()
        vol_since_price_peak = vol_close.loc[vol_close.index >= price_peak_date]
        current_vol = float(vol_close.iloc[-1])
        vol_percentile = float((vol_close <= current_vol).mean() * 100.0)
        return MarketSnapshot(
            price_history=price_history,
            current_price=float(price_close.iloc[-1]),
            peak_52w=float(price_close.tail(252).max()),
            sma_50=float(price_history["SMA_50"].iloc[-1]),
            sma_200=float(price_history["SMA_200"].iloc[-1]),
            volatility=current_vol,
            volatility_peak_since_price_peak=float(vol_since_price_peak.max()),
            volatility_percentile_5y=vol_percentile,
            cap_equal_ratio=float(cap_equal_ratio.iloc[-1]),
            cap_equal_sma_50=float(cap_equal_ratio.rolling(50).mean().iloc[-1]),
            breadth_50_pct=breadth_50,
            breadth_200_pct=breadth_200,
            breadth_constituent_count=breadth_count,
            breadth_is_current_constituents=ticker == "QQQ" and breadth_count > 0,
            mega_cap_top10_pct=top10_weight,
            mega_cap_is_fallback=top10_fallback,
            semi_ratio=semi_ratio,
            semi_ratio_sma_50=semi_ratio_sma,
            is_mock=False,
        )
    except Exception:
        return _mock_snapshot(ticker)


@st.cache_data(ttl=21600, show_spinner=False)
def _fred_series(series_id: str) -> pd.Series:
    frame = pd.read_csv(FRED_URL.format(series_id))
    frame.columns = ["date", "value"]
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    return frame.dropna().set_index("date")["value"].sort_index()


def _prior_value(series: pd.Series, days: int) -> float:
    cutoff = series.index[-1] - timedelta(days=days)
    prior = series.loc[:cutoff]
    return float(prior.iloc[-1] if not prior.empty else series.iloc[0])


@st.cache_data(ttl=21600, show_spinner=False)
def get_macro_snapshot() -> tuple[dict, bool]:
    fallback = {
        "curve_inverted_24m": False,
        "curve_spread": 0.50,
        "real_fed_funds": 0.25,
        "sahm": 0.00,
        "hy_oas": 3.00,
        "hy_low_52w": 2.70,
        "hy_delta_13w": 0.10,
        "nfci": -0.50,
        "nfci_delta_13w": 0.00,
    }
    if os.getenv("US_MARKET_MONITOR_OFFLINE") == "1":
        return fallback, True
    try:
        ten_year = _fred_series("DGS10")
        three_month = _fred_series("DGS3MO")
        rates = pd.concat([ten_year, three_month], axis=1).ffill().dropna()
        rates.columns = ["10Y", "3M"]
        spread = rates["10Y"] - rates["3M"]
        cutoff = spread.index[-1] - timedelta(days=730)

        fed_funds = _fred_series("FEDFUNDS")
        cpi = _fred_series("CPIAUCSL")
        cpi_yoy = cpi.pct_change(12).dropna() * 100.0
        sahm = _fred_series("SAHMREALTIME")
        hy = _fred_series("BAMLH0A0HYM2")
        nfci = _fred_series("NFCI")
        hy_cutoff = hy.index[-1] - timedelta(days=365)

        return {
            "curve_inverted_24m": bool((spread.loc[cutoff:] < 0).any()),
            "curve_spread": float(spread.iloc[-1]),
            "real_fed_funds": float(fed_funds.iloc[-1] - cpi_yoy.iloc[-1]),
            "sahm": float(sahm.iloc[-1]),
            "hy_oas": float(hy.iloc[-1]),
            "hy_low_52w": float(hy.loc[hy_cutoff:].min()),
            "hy_delta_13w": float(hy.iloc[-1] - _prior_value(hy, 91)),
            "nfci": float(nfci.iloc[-1]),
            "nfci_delta_13w": float(nfci.iloc[-1] - _prior_value(nfci, 91)),
        }, False
    except Exception:
        return fallback, True


REGIME_STYLE = {
    "HEALTHY": ("🟢 HEALTHY", "#087f5b"),
    "OVERHEATED": ("🟡 OVERHEATED", "#b7791f"),
    "FRAGILE": ("🟠 FRAGILE", "#c05621"),
    "BREAKDOWN": ("🔴 BREAKDOWN", "#c53030"),
    "PANIC": ("🟣 PANIC", "#6b46c1"),
    "SYSTEMIC": ("⚫ SYSTEMIC", "#30343b"),
    "RECOVERY": ("🔵 RECOVERY", "#2b6cb0"),
}

ACTION_ZH = {
    "HEALTHY": "维持核心仓位与正常定投。",
    "OVERHEATED": "估值昂贵但压力尚未确认：不追高；估值本身不是卖出信号。",
    "FRAGILE": "维持核心仓位、不加杠杆，并保留 Crash Reserve。",
    "BREAKDOWN": "控制高 Beta 风险；用 Escalation Gate 判断普通调整是否可能升级。",
    "PANIC": "高波动叠加大回撤转为分批买入信号，而不是机械卖出信号。",
    "SYSTEMIC": "系统性压力与衰退共振：继续慢速分批买入，不要一次打完预备资金。",
    "RECOVERY": "恐慌回落且市场参与度修复：逐步投入最后一档预备资金。",
}

MODULE_ZH = {
    "Valuation": "估值",
    "Recession": "衰退风险",
    "Monetary/Liquidity": "货币 / 流动性",
    "Fragility": "市场脆弱度",
    "Panic/Stress": "恐慌 / 压力",
}

STATUS_ZH = {
    "Healthy": "健康",
    "Normal": "正常",
    "Loose/Normal": "宽松 / 正常",
    "Not confirmed": "尚未确认",
    "Elevated": "偏高",
    "Background risk": "背景风险",
    "Watch": "观察",
    "Labor warning": "就业预警",
    "Expensive": "昂贵",
    "Rising pressure": "压力上升",
    "Deteriorating": "正在恶化",
    "Stress": "明显压力",
    "Extreme": "极端",
    "Tight": "紧缩",
    "Broken": "结构破坏",
    "Confirmed stress": "压力确认",
    "Panic": "恐慌",
    "Systemic": "系统性压力",
}

STATUS_COLOR = {
    "Healthy": "#16805b", "Normal": "#16805b", "Loose/Normal": "#16805b", "Not confirmed": "#16805b",
    "Elevated": "#c58a12", "Background risk": "#c58a12", "Watch": "#c58a12",
    "Labor warning": "#dd6b20", "Expensive": "#dd6b20", "Rising pressure": "#dd6b20",
    "Deteriorating": "#dd6b20", "Stress": "#dd6b20",
    "Extreme": "#d63b3b", "Tight": "#d63b3b", "Broken": "#d63b3b", "Confirmed stress": "#d63b3b",
    "Panic": "#7c4dcc", "Systemic": "#343a40",
}


def summary_card(label: str, value: str, meta: str = "", accent: str = "#3867d6") -> None:
    st.markdown(
        f"""
        <div class="summary-card" style="--accent:{accent}">
            <div class="card-label">{html.escape(label)}</div>
            <div class="summary-value">{html.escape(value)}</div>
            <div class="summary-meta">{html.escape(meta)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def module_detail(name: str, drawdown: float, vol_name: str) -> str:
    if name == "Valuation":
        return f"CAPE {cape:.1f} · Buffett {buffett:.0f}% · 同源只计一票"
    if name == "Recession":
        inverted = "是" if curve_inverted else "否"
        return f"Sahm {sahm:.2f} · 近24个月倒挂：{inverted}"
    if name == "Monetary/Liquidity":
        return f"实际政策利率 {real_fed_funds:.2f}% · NFCI 13周 {nfci_delta:+.2f}"
    if name == "Fragility":
        if ticker == "QQQ":
            breadth_text = "breadth 暂缺" if breadth_50 is None else f"50DMA breadth {breadth_50:.0f}%"
            return f"{breadth_text} · QQQ/QQEW · SMH/QQQ · Top 10"
        return "50/200日均线 · SPY/RSP 集中度代理"
    return f"{vol_name} {market.volatility:.1f} · 回撤 {drawdown:.1f}% · HY较低点 {hy_oas - hy_low:+.2f}pp"


def module_card(name: str, result, drawdown: float, vol_name: str) -> None:
    accent = STATUS_COLOR.get(result.status, "#66758a")
    st.markdown(
        f"""
        <div class="module-card" style="--accent:{accent}">
            <div class="card-label">{html.escape(MODULE_ZH[name])}</div>
            <div class="status-row">
                <span class="status-dot"></span>
                <span>{html.escape(STATUS_ZH.get(result.status, result.status))}</span>
            </div>
            <div class="module-score">诊断值 {result.score}/100</div>
            <div class="module-detail">{html.escape(module_detail(name, drawdown, vol_name))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


st.sidebar.title("🧭 模型输入")
st.sidebar.markdown(f"[查看 GitHub 源码]({GITHUB_URL})")
ticker = st.sidebar.selectbox("监测标的", ["VOO", "QQQ"])

with st.sidebar.expander("网络设置", expanded=False):
    proxy_url = st.text_input("HTTP 代理（可选）", value="")

market = get_market_snapshot(ticker, proxy_url)
macro, macro_fallback = get_macro_snapshot()

st.sidebar.subheader("估值（手动校准）")
cape = st.sidebar.number_input("Shiller CAPE", min_value=0.0, value=40.0, step=0.1)
buffett = st.sidebar.number_input("Buffett Indicator (%)", min_value=0.0, value=200.0, step=1.0)
st.sidebar.caption("CAPE 与 Buffett 属于同一估值风险源，模型只计一票。")

with st.sidebar.expander("宏观与信用输入", expanded=False):
    st.caption("默认值由 FRED 自动读取；可用最新发布值覆盖。")
    st.metric("当前 10Y-3M", f"{macro['curve_spread']:+.2f}%")
    curve_inverted = st.checkbox("过去24个月曾持续倒挂", value=macro["curve_inverted_24m"])
    real_fed_funds = st.number_input("Real Fed Funds (%)", value=float(macro["real_fed_funds"]), step=0.05)
    sahm = st.number_input("Sahm Rule", value=float(macro["sahm"]), step=0.01)
    hy_oas = st.number_input("HY OAS (%)", value=float(macro["hy_oas"]), step=0.05)
    hy_low = st.number_input("HY OAS 52周低点 (%)", value=float(macro["hy_low_52w"]), step=0.05)
    hy_delta = st.number_input("HY OAS 13周变化 (百分点)", value=float(macro["hy_delta_13w"]), step=0.05)
    nfci = st.number_input("NFCI", value=float(macro["nfci"]), step=0.05)
    nfci_delta = st.number_input("NFCI 13周变化", value=float(macro["nfci_delta_13w"]), step=0.05)

breadth_50 = market.breadth_50_pct
breadth_200 = market.breadth_200_pct
mega_cap_top10 = market.mega_cap_top10_pct
if ticker == "QQQ":
    with st.sidebar.expander("QQQ 专用校准", expanded=True):
        st.caption("自动读取 Nasdaq-100 当前成分股 breadth；可在数据缺失时手动覆盖。")
        if breadth_50 is None or breadth_200 is None:
            st.warning("当前成分股行情未完整返回，breadth 暂不参与模型。")
            use_manual_breadth = st.checkbox("使用手动 breadth", value=False)
            manual_breadth_50 = st.number_input("50DMA breadth (%)", 0.0, 100.0, 50.0, 1.0)
            manual_breadth_200 = st.number_input("200DMA breadth (%)", 0.0, 100.0, 50.0, 1.0)
            if use_manual_breadth:
                breadth_50 = float(manual_breadth_50)
                breadth_200 = float(manual_breadth_200)
        else:
            st.metric("Nasdaq-100 50DMA breadth", f"{breadth_50:.1f}%")
            st.metric("Nasdaq-100 200DMA breadth", f"{breadth_200:.1f}%")
        mega_cap_top10 = st.number_input(
            "QQQ Top-10 权重 (%)",
            min_value=0.0,
            max_value=100.0,
            value=float(mega_cap_top10 or 53.0),
            step=0.1,
        )
        if market.mega_cap_is_fallback:
            st.caption("Top-10 自动持仓读取失败，当前 53% 为 Invesco 已披露的研究基准，可手动覆盖。")

already_deployed = st.sidebar.slider("Crash Reserve 已投入", 0, 100, 0, 5, format="%d%%")

inputs = MarketInputs(
    ticker=ticker,
    current_price=market.current_price,
    peak_52w=market.peak_52w,
    sma_50=market.sma_50,
    sma_200=market.sma_200,
    volatility=market.volatility,
    volatility_peak_since_price_peak=market.volatility_peak_since_price_peak,
    cape=cape,
    buffett_ratio=buffett,
    curve_inverted_24m=curve_inverted,
    real_fed_funds=real_fed_funds,
    sahm_rule=sahm,
    hy_oas=hy_oas,
    hy_oas_low_52w=hy_low,
    hy_oas_delta_13w=hy_delta,
    nfci=nfci,
    nfci_delta_13w=nfci_delta,
    cap_equal_ratio=market.cap_equal_ratio,
    cap_equal_sma_50=market.cap_equal_sma_50,
    breadth_50_pct=breadth_50,
    breadth_200_pct=breadth_200,
    breadth_is_current_constituents=market.breadth_is_current_constituents,
    mega_cap_top10_pct=mega_cap_top10,
    semi_ratio=market.semi_ratio,
    semi_ratio_sma_50=market.semi_ratio_sma_50,
)
assessment = assess_market(inputs, market.volatility_percentile_5y)

st.title(f"US Market Regime — {ticker}")
st.caption(f"{UI_VERSION} · Risk Build-up → Escalation Gate → Panic Buy Engine")

if market.is_mock:
    st.warning("Yahoo Finance 连接失败：价格、波动率和趋势正在使用模拟数据，不能用于投资决策。")
if macro_fallback:
    st.warning("FRED 连接失败：宏观栏位正在使用备用示例值，请在侧边栏手动校准。")

regime_label, regime_color = REGIME_STYLE[assessment.regime]
st.markdown(
    f'<div class="regime-box" style="background:{regime_color}"><h2>{regime_label}</h2>'
    f'<div>{ACTION_ZH[assessment.regime]}</div></div>',
    unsafe_allow_html=True,
)

top1, top2, top3, top4 = st.columns(4)
vol_name = "VIX" if ticker == "VOO" else "VXN"
with top1:
    summary_card("最新价格", f"${market.current_price:,.2f}", ticker, "#3867d6")
with top2:
    dd_accent = "#d63b3b" if assessment.drawdown_pct <= -10 else "#16805b"
    summary_card("52周回撤", f"{assessment.drawdown_pct:.1f}%", "Escalation Gate 于 -10% 启动", dd_accent)
with top3:
    vol_accent = STATUS_COLOR.get(assessment.volatility_status, "#3867d6")
    summary_card(vol_name, f"{market.volatility:.1f}", STATUS_ZH.get(assessment.volatility_status, assessment.volatility_status), vol_accent)
with top4:
    summary_card("5年波动率百分位", f"P{market.volatility_percentile_5y:.0f}", "滚动历史位置", "#6b5bd2")

st.subheader("五模块状态（不计算简单平均总分）")
module_cols = st.columns(5)
for column, (name, result) in zip(module_cols, assessment.modules.items()):
    with column:
        module_card(name, result, assessment.drawdown_pct, vol_name)

if ticker == "QQQ":
    st.subheader("QQQ 专用内部结构")
    structure_cols = st.columns(5)
    structure_cols[0].metric(
        "Nasdaq-100 > 50DMA",
        "N/A" if breadth_50 is None else f"{breadth_50:.1f}%",
        help="按当前 Nasdaq-100 成分股计算。历史回看会有幸存者偏差。",
    )
    structure_cols[1].metric(
        "Nasdaq-100 > 200DMA",
        "N/A" if breadth_200 is None else f"{breadth_200:.1f}%",
        help="按当前 Nasdaq-100 成分股计算。",
    )
    cap_equal_delta = (market.cap_equal_ratio / market.cap_equal_sma_50 - 1.0) * 100.0
    structure_cols[2].metric(
        "QQQ / QQEW",
        f"{market.cap_equal_ratio:.3f}",
        f"{cap_equal_delta:+.1f}% vs 50DMA",
        delta_color="inverse",
        help="上升表示市值权重股相对等权股更强，市场领导面趋窄。",
    )
    semi_delta = None
    if market.semi_ratio is not None and market.semi_ratio_sma_50:
        semi_delta = (market.semi_ratio / market.semi_ratio_sma_50 - 1.0) * 100.0
    structure_cols[3].metric(
        "SMH / QQQ",
        "N/A" if market.semi_ratio is None else f"{market.semi_ratio:.3f}",
        None if semi_delta is None else f"{semi_delta:+.1f}% vs 50DMA",
        help="低于 50DMA 表示半导体相对强弱恶化。",
    )
    structure_cols[4].metric(
        "QQQ Top-10",
        "N/A" if mega_cap_top10 is None else f"{mega_cap_top10:.1f}%",
        "≥50% 集中度预警" if mega_cap_top10 is not None and mega_cap_top10 >= 50.0 else "低于预警线",
        delta_color="inverse",
    )
    breadth_note = (
        f"breadth 覆盖 {market.breadth_constituent_count} 只证券；使用当前成分股口径，适合实时诊断，"
        "不等于 point-in-time 无偏历史 breadth。"
        if market.breadth_constituent_count
        else "breadth 当前不可用，因此没有计入 Fragility；模型不会用代理值伪装真实 breadth。"
    )
    st.caption(breadth_note + " QQQ/QQEW 与 Top-10 属于同一集中度风险源，在 Fragility 中合计只投一票。")

left, right = st.columns(2)
with left:
    st.subheader("Escalation Gate")
    st.caption("仅在指数从52周高点回撤至少10%后启用；它判断调整是否可能升级，而不是预测顶部。")
    if assessment.escalation_active:
        st.info(f"**{assessment.escalation_status}** · 压力信号 {assessment.escalation_count}/3")
    else:
        st.info("**未启用** · 当前回撤尚未达到 -10%")
    escalation_rows = [
        {"信号": "过去24个月10Y-3M倒挂", "触发": "是" if assessment.escalation_signals["Yield curve"] else "否"},
        {"信号": "Real Fed Funds ≥ 1.5%", "触发": "是" if assessment.escalation_signals["Real rates"] else "否"},
        {"信号": "HY OAS较52周低点扩大≥200bp", "触发": "是" if assessment.escalation_signals["Credit"] else "否"},
    ]
    st.dataframe(pd.DataFrame(escalation_rows), hide_index=True, width="stretch")

with right:
    st.subheader("Panic Buy Engine")
    low, high = assessment.buy_tranche
    remaining = max(0, 100 - already_deployed)
    deploy_low = min(low, remaining)
    deploy_high = min(high, remaining)
    st.info(f"**当前阶段：{assessment.buy_stage}**")
    if high > 0 and remaining > 0:
        tranche_text = f"{deploy_low}%" if deploy_low == deploy_high else f"{deploy_low}–{deploy_high}%"
        st.metric("本档建议投入（占 Crash Reserve）", tranche_text)
    elif remaining == 0:
        st.metric("剩余 Crash Reserve", "0%")
    else:
        st.metric("本档建议投入", "0%")
    if assessment.recession_modifier:
        st.warning("衰退/信用确认正在减慢买入速度；高恐慌并不等于当天见底。")
    st.caption("每档比例针对预先独立留出的 Crash Reserve，不是整个投资组合。")

st.subheader("Recovery 确认")
recovery_cols = st.columns(3)
for column, (name, active) in zip(recovery_cols, assessment.recovery_signals.items()):
    column.metric(name, "✅ 满足" if active else "— 未满足")
st.caption("大回撤期间满足3项中的2项，才进入 Recovery 并考虑投入最后25–30%。")

st.subheader(f"{ticker} 价格与趋势")
chart = go.Figure()
history = market.price_history.tail(504)
chart.add_trace(go.Scatter(x=history.index, y=history["Close"], name=ticker, line=dict(color="#4da6ff", width=2)))
chart.add_trace(go.Scatter(x=history.index, y=history["SMA_50"], name="50DMA", line=dict(color="#f6c85f", width=1.5)))
chart.add_trace(go.Scatter(x=history.index, y=history["SMA_200"], name="200DMA", line=dict(color="#ed553b", width=1.5)))
chart.update_layout(height=430, template="plotly_dark", margin=dict(l=20, r=20, t=20, b=20))
st.plotly_chart(chart, width="stretch")

with st.expander("查看 VOO / QQQ 独立恐慌与买入阈值"):
    rows = []
    for asset, values in VOLATILITY_THRESHOLDS.items():
        initial_dd, deep_dd, bear_dd = BUY_DRAWDOWN_THRESHOLDS[asset]
        rows.append({
            "标的": asset,
            "波动率": "VIX" if asset == "VOO" else "VXN",
            "Watch": values[0],
            "Stress": values[1],
            "Panic": values[2],
            "Extreme": values[3],
            "Systemic": values[4],
            "初始买入回撤": f"{initial_dd:.0f}%",
            "深度调整回撤": f"{deep_dd:.0f}%",
            "熊市回撤": f"{bear_dd:.0f}%",
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption("VOO 使用 VIX；QQQ 使用 VXN。QQQ 的波动率和回撤阈值更高，避免把正常科技股波动误判成同等危机。")

with st.expander("查看同一冲击下的 VOO / QQQ 档位校准"):
    calibration_rows = [
        {"共同回撤": "-10%", "VOO 档位": "Initial · 10–15%", "QQQ 档位": "等待 -12%"},
        {"共同回撤": "-18%", "VOO 档位": "Deep · 20%", "QQQ 档位": "Initial · 10–15%"},
        {"共同回撤": "-25%", "VOO 档位": "Bear · 25%", "QQQ 档位": "Deep · 20%"},
        {"共同回撤": "-32%", "VOO 档位": "Bear · 25%", "QQQ 档位": "Bear · 25%"},
    ]
    st.dataframe(pd.DataFrame(calibration_rows), hide_index=True, width="stretch")
    st.caption(
        "这是控制变量校准：假设各自 VIX/VXN 已达到相应 Stress/Panic 门槛，只比较相同回撤下的档位。"
        "它用于验证两套规则不同，不是对下一次危机收益的预测。"
    )

with st.expander("查看 2018 / 2020 / 2022 历史事件审计"):
    historical_rows = []
    for row in crisis_calibration_rows():
        low, high = row["buy_tranche"]
        tranche = f"{low}%" if low == high else f"{low}–{high}%"
        historical_rows.append({
            "事件": row["event"],
            "标的": row["asset"],
            "事件窗口最大回撤": f"{row['drawdown_pct']:.1f}%",
            "VIX / VXN峰值": f"{row['volatility_peak']:.1f}",
            "压力状态": row["volatility_status"],
            "模型档位": row["buy_stage"],
            "Crash Reserve": tranche,
        })
    st.dataframe(pd.DataFrame(historical_rows), hide_index=True, width="stretch")
    st.caption(
        "事件窗口数据用于阈值审计；2020 的 QQQ 最大回撤小于 VOO，而 2022 明显更深。"
        "这里使用事件内峰值，不能当作无前视的逐日回测结果。"
    )

st.markdown("---")
st.caption(
    "数据：Nasdaq（当前 Nasdaq-100 成分列表）、Yahoo Finance（价格、VIX/VXN、breadth 与相对强弱）"
    "和 FRED（利率、Sahm、HY OAS、NFCI）。历史 breadth 仍需 point-in-time 成分数据做无幸存者偏差回测；"
    "本项目仅供研究，不构成投资建议。"
)
