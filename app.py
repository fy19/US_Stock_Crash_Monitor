import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import random

# ==========================================
# 1. 页面配置与样式 (UI Configuration)
# ==========================================
st.set_page_config(
    page_title="美股崩盘风险监测仪",
    page_icon="📉",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义CSS
st.markdown("""
<style>
    .metric-card {
        background-color: #0e1117;
        border: 1px solid #30333F;
        padding: 15px;
        border-radius: 5px;
        color: white;
    }
    .stProgress > div > div > div > div {
        background-color: #ff4b4b;
    }
    h1, h2, h3 {
        font-family: 'Roboto', sans-serif;
    }
    /* 让Metric的label更明显一点 */
    div[data-testid="stMetricLabel"] {
        font-size: 14px; 
        color: #9da3ad;
    }
    /* 链接样式 */
    .source-link {
        font-size: 0.85em;
        color: #4da6ff;
        text-decoration: none;
        margin-bottom: 5px;
        display: inline-block;
    }
    .source-link:hover {
        text-decoration: underline;
    }
    /* 阈值提示样式 */
    .threshold-info {
        font-size: 0.8em;
        color: #a0a0a0;
        background-color: #262730;
        border-left: 3px solid #ff4b4b;
        padding: 10px;
        margin-top: 5px;
        border-radius: 4px;
    }
</style>
""", unsafe_allow_html=True)


# ==========================================
# 2. 数据获取与处理模块 (Data Pipeline)
# ==========================================

def generate_mock_data(ticker_name="VOO"):
    """
    生成逼真的模拟数据，用于演示模式
    """
    dates = pd.date_range(end=datetime.now(), periods=500, freq='B')
    base_price = 500 if ticker_name == "QQQ" else 450

    trend = np.linspace(0, 50, 500)
    noise = np.random.normal(0, 5, 500).cumsum()
    prices = base_price + trend + noise

    df = pd.DataFrame(index=dates)
    df['Open'] = prices + np.random.uniform(-2, 2, 500)
    df['High'] = df['Open'] + np.random.uniform(0, 5, 500)
    df['Low'] = df['Open'] - np.random.uniform(0, 5, 500)
    df['Close'] = prices
    df['SMA_200'] = df['Close'].rolling(window=200).mean()

    current_price = df['Close'].iloc[-1]
    sma_200 = df['SMA_200'].iloc[-1]

    us_10y_yield = 4.15 + random.uniform(-0.1, 0.1)

    return df, current_price, sma_200, us_10y_yield, True


@st.cache_data(ttl=3600, show_spinner=False)
def get_market_data(ticker="VOO", proxy=None):
    """
    获取数据，失败则回退到模拟数据
    """
    try:
        if proxy:
            import os
            os.environ["http_proxy"] = proxy
            os.environ["https_proxy"] = proxy

        end_date = datetime.now()
        start_date = end_date - timedelta(days=730)

        stock = yf.Ticker(ticker)
        df = stock.history(start=start_date, end=end_date)

        if df.empty:
            raise ValueError("获取到的数据为空")

        current_price = df['Close'].iloc[-1]
        df['SMA_200'] = df['Close'].rolling(window=200).mean()
        sma_200 = df['SMA_200'].iloc[-1]

        try:
            tnx = yf.Ticker("^TNX")
            tnx_hist = tnx.history(period="5d")
            if not tnx_hist.empty:
                us_10y_yield = tnx_hist['Close'].iloc[-1]
            else:
                us_10y_yield = 4.0
        except:
            us_10y_yield = 4.0

        return df, current_price, sma_200, us_10y_yield, False

    except Exception as e:
        return generate_mock_data(ticker)


# ==========================================
# 3. 侧边栏：配置与输入
# ==========================================
st.sidebar.title("🛠️ 设置与校准")

# --- 标的选择 ---
st.sidebar.subheader("0. 监测标的")
target_option = st.sidebar.selectbox(
    "选择你要分析的ETF",
    ["VOO (标普500)", "QQQ (纳指100)"],
    index=0
)
ticker_symbol = "VOO" if "VOO" in target_option else "QQQ"

# --- 权重配置 (新增: 用户可调节) ---
with st.sidebar.expander("⚖️ 模型权重配置 (点击展开)", expanded=False):
    st.caption("您可以根据当前市场环境，拖动滑块调整各指标权重。(非金融专业人士默认权重即可)")

    # 设置默认值为上次的优化值
    w_buffett_input = st.slider("1. 巴菲特指标权重", 0, 50, 15, 5, format="%d%%")
    w_shiller_input = st.slider("2. 席勒市盈率权重", 0, 50, 25, 5, format="%d%%")
    w_yield_input = st.slider("3. 美债利差权重", 0, 50, 25, 5, format="%d%%")
    w_tech_input = st.slider("4. 均线乖离权重", 0, 50, 20, 5, format="%d%%")
    w_sentiment_input = st.slider("5. 恐慌指数权重", 0, 50, 15, 5, format="%d%%")

    total_weight_score = w_buffett_input + w_shiller_input + w_yield_input + w_tech_input + w_sentiment_input

    # 颜色提示
    if total_weight_score != 100:
        st.warning(f"⚠️ 当前权重总和: {total_weight_score}% (建议调整为 100%)")
    else:
        st.success(f"✅ 权重总和: {total_weight_score}% (完美)")

    # 转换为小数供计算使用
    user_weights = {
        'buffett': w_buffett_input / 100.0,
        'shiller': w_shiller_input / 100.0,
        'yield': w_yield_input / 100.0,
        'technical': w_tech_input / 100.0,
        'sentiment': w_sentiment_input / 100.0
    }

# --- 网络设置 ---
with st.sidebar.expander("🌐 网络连接设置", expanded=False):
    st.caption("无法连接Yahoo Finance时请填入代理，或留空使用**模拟演示模式**。")
    proxy_url = st.text_input("HTTP代理地址", placeholder="例如 http://127.0.0.1:7890")

# --- 宏观数据输入 (带详细历史阈值) ---

st.sidebar.markdown("---")
st.sidebar.subheader("1. 巴菲特指标 (Buffett Indicator)")
st.sidebar.markdown("""
[🔗 Wilshire 5000](https://sc.macromicro.me/series/616/wilshire5000) | [🔗 US GDP](https://www.macromicro.me/collections/2/us-gdp-relative/2/us-real-gdp)
""", unsafe_allow_html=True)

wilshire_5000 = st.sidebar.number_input("美股总市值 (Trillion $)", value=59.0, step=0.5)
us_gdp = st.sidebar.number_input("美国 GDP (Trillion $)", value=29.0, step=0.1)
buffett_ratio = (wilshire_5000 / us_gdp) * 100
st.sidebar.caption(f"当前计算值: **{buffett_ratio:.1f}%**")

st.sidebar.info("""
**⚠️ 注意：GDP 数据通常每季度更新，存在滞后性。**
**📊 历史参考阈值:**
* **历史平均 (1950-2023)**: ~100%
* **近10年平均**: ~150% (低利率环境推高)
* **2000年 泡沫峰值**: ~140%
* **2021年 历史峰值**: ~200% (极度高危)
""")

st.sidebar.subheader("2. 席勒市盈率 (Shiller PE)")
st.sidebar.markdown("[🔗 Multpl Shiller PE](https://www.multpl.com/shiller-pe)", unsafe_allow_html=True)
shiller_pe = st.sidebar.number_input("CAPE Ratio", value=40.0, step=0.1)
st.sidebar.info("""
**📊 历史参考阈值:**
* **历史平均**: ~17.0
* **近10年平均**: ~30.0
* **1929年 大萧条**: 30.0
* **2000年 互联网泡沫**: 44.2 (历史最高)
* **2021年 疫情后**: 38.6
""")

st.sidebar.subheader("3. 收益率曲线 (10Y-2Y)")
st.sidebar.markdown("[🔗 CN.Investing 债券](https://cn.investing.com/rates-bonds/usa-government-bonds)",
                    unsafe_allow_html=True)
user_2y_yield = st.sidebar.number_input(
    "2年期美债收益率 (%)",
    value=4.20,
    step=0.01,
    help="输入2年期收益率，系统将自动对比10年期。"
)
st.sidebar.info("""
**📊 历史参考阈值:**
* **正常状态**: +0.8% ~ +2.0%
* **倒挂预警 (< 0%)**: 2000, 2007, 2019, 2022 均出现
* **解挂风险 (倒挂后回升至 > 0%)**: 最危险时刻。
  (例如2008年初，利差从负转正后股市暴跌)
""")

st.sidebar.subheader("4. 恐慌与贪婪指数")
st.sidebar.markdown("[🔗 CNN Fear & Greed](https://edition.cnn.com/markets/fear-and-greed)", unsafe_allow_html=True)
fear_greed = st.sidebar.slider("Fear & Greed Index (0-100)", 0, 100, 45)
st.sidebar.caption("极度贪婪 (>80) 往往是短期顶部信号。")

st.sidebar.markdown("---")
st.sidebar.markdown("**📈 关于 200日均线乖离率 (自动计算)**")
st.sidebar.info("""
**📊 历史参考阈值:**
* **历史平均**: ~0% (均值回归)
* **危险阈值**: > 15% (短期过热)
* **极度泡沫**: > 20% (如 2000年, 2021年)
* **抄底机会**: < -15% (如 2008年, 2020年3月)
""")


# ==========================================
# 4. 风险评分模型
# ==========================================
def calculate_risk_score(current_price, sma_200, us_10y, us_2y, buffett_val, shiller_val, fear_val, weights):
    """
    计算综合风险评分，支持动态权重
    """
    score = 0
    details = {}

    # --- 因子 1: 巴菲特指标 ---
    w_buffett = weights['buffett']
    # 阈值参考：考虑到近10年估值中枢上移，适当放宽一点点，但依然保持警惕
    if buffett_val > 200:
        b_risk = 100  # 2021水平
    elif buffett_val > 180:
        b_risk = 90
    elif buffett_val > 150:
        b_risk = 75  # 近10年均值附近
    elif buffett_val > 120:
        b_risk = 50
    else:
        b_risk = 25
    score += b_risk * w_buffett
    details['Buffett'] = (b_risk, buffett_val)

    # --- 因子 2: Shiller PE ---
    w_shiller = weights['shiller']
    if shiller_val > 40:
        s_risk = 100  # 接近2000年水平
    elif shiller_val > 35:
        s_risk = 90  # 2021年水平
    elif shiller_val > 30:
        s_risk = 70  # 1929年水平/近10年均值
    elif shiller_val > 25:
        s_risk = 50
    else:
        s_risk = 20
    score += s_risk * w_shiller
    details['Shiller'] = (s_risk, shiller_val)

    # --- 因子 3: 收益率曲线 ---
    w_yield = weights['yield']
    spread = us_10y - us_2y
    # 逻辑：深度倒挂虽然预示衰退，但股市往往在“解挂”（spread回到0以上）时才真正崩盘
    if spread < -0.5:
        y_risk = 80
        status = "深度倒挂"
    elif spread < 0:
        y_risk = 60
        status = "轻度倒挂"
    elif spread >= 0 and spread < 0.5:
        y_risk = 70
        status = "解挂/平坦(危)"  # 解挂初期往往最危险
    else:
        y_risk = 30
        status = "正常"
    score += y_risk * w_yield
    details['Yield'] = (y_risk, spread, status)

    # --- 因子 4: 200日均线乖离率 ---
    w_tech = weights['technical']
    if sma_200 and not np.isnan(sma_200):
        deviation = (current_price - sma_200) / sma_200
        deviation_pct = deviation * 100
    else:
        deviation_pct = 0

    if deviation_pct > 25:
        m_risk = 100
    elif deviation_pct > 20:
        m_risk = 85  # 2000年水平
    elif deviation_pct > 15:
        m_risk = 65  # 警戒线
    elif deviation_pct > 5:
        m_risk = 40
    elif deviation_pct < -10:
        m_risk = 10
    else:
        m_risk = 20
    score += m_risk * w_tech
    details['Technical'] = (m_risk, deviation_pct)

    # --- 因子 5: 恐慌贪婪指数 ---
    w_sentiment = weights['sentiment']
    if fear_val > 80:
        f_risk = 100
    elif fear_val > 60:
        f_risk = 70
    elif fear_val < 20:
        f_risk = 0
    else:
        f_risk = 40
    score += f_risk * w_sentiment
    details['Sentiment'] = (f_risk, fear_val)

    return score, details


# ==========================================
# 5. 主程序逻辑
# ==========================================

# 获取数据
df, price, sma200, yield_10y, is_mock = get_market_data(ticker_symbol, proxy=proxy_url)

# --- UI: 标题区 ---
st.title(f"🚨 Wall Street Quant: {ticker_symbol} 崩盘风险监测仪")

if is_mock:
    st.warning("⚠️ **演示模式**：无法连接数据源，当前使用模拟数据。")
else:
    st.success("✅ **实时连接**：数据源正常。")

st.markdown(
    f"**当前标的**: {ticker_symbol} | **最新价格**: ${price:.2f} | **10年期美债收益率**: {yield_10y:.2f}% (自动获取)")
st.markdown("---")

if df is not None:
    # 关键修改：传入 user_weights 字典，确保权重调节生效
    final_risk_score, risk_details = calculate_risk_score(
        price, sma200, yield_10y, user_2y_yield,
        buffett_ratio, shiller_pe, fear_greed,
        user_weights
    )

    # --- 第一行: 仪表盘与建议 ---
    col1, col2 = st.columns([1, 2])
    with col1:
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=final_risk_score,
            title={'text': f"{ticker_symbol} 崩盘风险指数"},
            gauge={
                'axis': {'range': [0, 100]},
                'bar': {'color': "rgba(0,0,0,0)"},
                'steps': [
                    {'range': [0, 40], 'color': '#00cc96'},
                    {'range': [40, 70], 'color': '#ffa15a'},
                    {'range': [70, 100], 'color': '#ef553b'}
                ],
                'threshold': {
                    'line': {'color': "black", 'width': 4},
                    'thickness': 0.75,
                    'value': final_risk_score
                }
            }
        ))
        fig_gauge.update_layout(height=300, margin=dict(l=20, r=20, t=50, b=20))
        st.plotly_chart(fig_gauge, width="stretch")

    with col2:
        st.subheader("🤖 量化建议")
        if final_risk_score > 80:
            bg_color, title_text = "#ef553b", "极高风险 (Extreme Risk)"
            advice = f"模型显示 {ticker_symbol} 极度过热。建议大幅降低仓位，购买Put对冲，持有现金。"
        elif final_risk_score > 60:
            bg_color, title_text = "#ffa15a", "风险累积 (Elevated Risk)"
            advice = f"风险正在积聚。{ticker_symbol} 波动可能加剧，停止追高，考虑适当对冲，收紧止损线。"
        else:
            bg_color, title_text = "#00cc96", "相对安全 (Safe Zone)"
            advice = "市场处于正常波动范围。维持定投计划，关注长期价值。"

        st.markdown(f"""
        <div style="background-color: {bg_color}; padding: 20px; border-radius: 10px; color: white;">
            <h3 style="margin:0;">{title_text}</h3>
            <p style="margin-top:10px;">{advice}</p>
        </div>
        """, unsafe_allow_html=True)

    # --- 第二行: 因子详情 (带权重展示) ---
    st.subheader("🔍 风险因子分解 (含自定义权重)")


    def get_label(name, key):
        return f"{name} (权重: {int(user_weights[key] * 100)}%)"


    m1, m2, m3, m4, m5 = st.columns(5)

    with m1:
        st.metric(
            label=get_label("巴菲特指标", 'buffett'),
            value=f"{risk_details['Buffett'][1]:.1f}%",
            delta=f"Risk: {risk_details['Buffett'][0]}",
            delta_color="inverse"
        )
    with m2:
        st.metric(
            label=get_label("席勒市盈率", 'shiller'),
            value=f"{risk_details['Shiller'][1]:.1f}",
            delta=f"Risk: {risk_details['Shiller'][0]}",
            delta_color="inverse"
        )
    with m3:
        spread_val = risk_details['Yield'][1]
        status_text = risk_details['Yield'][2]
        st.metric(
            label=get_label("10Y-2Y 利差", 'yield'),
            value=f"{spread_val:.2f}%",
            delta=status_text,
            delta_color="off",
            help=f"计算公式: 10年期({yield_10y:.2f}%) - 2年期({user_2y_yield:.2f}%)"
        )
    with m4:
        st.metric(
            label=get_label("均线乖离率", 'technical'),
            value=f"{risk_details['Technical'][1]:.1f}%",
            delta=f"Risk: {risk_details['Technical'][0]}",
            delta_color="inverse"
        )
    with m5:
        st.metric(
            label=get_label("贪婪指数", 'sentiment'),
            value=f"{risk_details['Sentiment'][1]}",
            delta=f"Risk: {risk_details['Sentiment'][0]}",
            delta_color="inverse"
        )

    st.markdown("---")

    # --- 第三行: 图表 ---
    st.subheader(f"📈 {ticker_symbol} 价格 vs 200日均线")
    fig_chart = go.Figure()
    fig_chart.add_trace(go.Candlestick(
        x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name=ticker_symbol
    ))
    fig_chart.add_trace(go.Scatter(
        x=df.index, y=df['SMA_200'], mode='lines', name='SMA 200', line=dict(color='orange', width=2)
    ))
    fig_chart.update_layout(height=450, xaxis_rangeslider_visible=False, template="plotly_dark")
    st.plotly_chart(fig_chart, width="stretch")
