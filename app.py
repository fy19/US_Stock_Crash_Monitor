"""Streamlit dashboard for the US Market Regime Monitor v2.2."""

from dataclasses import dataclass
from datetime import datetime, timedelta
import html
import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from model import MarketInputs, VOLATILITY_THRESHOLDS, assess_market


GITHUB_URL = "https://github.com/fy19/US_Stock_Crash_Monitor"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"


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
    equal_weight_ratio: float
    equal_weight_sma_50: float
    semi_ratio: float | None
    semi_ratio_sma_50: float | None
    is_mock: bool


st.set_page_config(
    page_title="US Market Regime Monitor v2.2",
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
        equal_weight_ratio=1.0,
        equal_weight_sma_50=1.0,
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
        equal_ratio = ratio["equal"] / ratio["benchmark"]

        semi_ratio = None
        semi_ratio_sma = None
        if ticker == "QQQ":
            semi_close = _close(_history("SMH"))
            semi = pd.concat([semi_close, benchmark_close], axis=1, join="inner").dropna()
            semi.columns = ["semi", "benchmark"]
            semi_series = semi["semi"] / semi["benchmark"]
            semi_ratio = float(semi_series.iloc[-1])
            semi_ratio_sma = float(semi_series.rolling(50).mean().iloc[-1])

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
            equal_weight_ratio=float(equal_ratio.iloc[-1]),
            equal_weight_sma_50=float(equal_ratio.rolling(50).mean().iloc[-1]),
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
        ratio_name = "RSP/SPY" if ticker == "VOO" else "QQEW/QQQ + SMH/QQQ"
        return f"50/200日均线 · {ratio_name} 相对强弱"
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
    equal_weight_ratio=market.equal_weight_ratio,
    equal_weight_sma_50=market.equal_weight_sma_50,
    semi_ratio=market.semi_ratio,
    semi_ratio_sma_50=market.semi_ratio_sma_50,
)
assessment = assess_market(inputs, market.volatility_percentile_5y)

st.title(f"US Market Regime — {ticker}")
st.caption("v2.2 · Risk Build-up → Escalation Gate → Panic Buy Engine")

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

with st.expander("查看 VOO / QQQ 独立恐慌阈值"):
    rows = []
    for asset, values in VOLATILITY_THRESHOLDS.items():
        rows.append({
            "标的": asset,
            "Watch": values[0],
            "Stress": values[1],
            "Panic": values[2],
            "Extreme": values[3],
            "Systemic": values[4],
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption("VOO 使用 VIX；QQQ 使用 VXN。最终判断同时采用绝对阈值与5年滚动百分位。")

st.markdown("---")
st.caption(
    "数据：Yahoo Finance（价格、VIX/VXN、相对强弱）与 FRED（利率、Sahm、HY OAS、NFCI）。"
    "模型仍需完整的1995–2026日频回测与真实成分股 breadth 数据校准；本项目仅供研究，不构成投资建议。"
)
