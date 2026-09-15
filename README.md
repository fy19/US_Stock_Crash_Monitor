# US Market Regime Monitor v2.2

这是一个基于 Streamlit 的美股市场状态仪表盘，分别分析 VOO（S&P 500）和 QQQ（Nasdaq-100）。

v2.2 不再输出一个容易误导的“崩盘风险总分”，也不再使用“分数越高、卖得越多”的规则。系统将市场估值与脆弱性、已发生的市场压力，以及恐慌后的分批买入分开处理。

## 三层决策结构

1. **Risk Build-up Engine**：市场是否昂贵、流动性收紧、内部结构变弱？
2. **Escalation Gate**：指数已经回撤至少 10% 后，这次调整是否更可能升级成熊市？
3. **Panic Buy Engine**：高波动叠加大回撤后，应使用多少预留资金分批买入？

## 五个状态模块

| 模块 | 主要输入 | 用途 |
|---|---|---|
| Valuation | CAPE、Buffett Indicator | 长期估值背景；相关指标只计一票 |
| Recession | 10Y-3M、Sahm、信用/金融条件确认 | 区分就业预警与衰退确认 |
| Monetary/Liquidity | Real Fed Funds、NFCI 及 13 周变化 | 捕捉 2018/2022 式紧缩熊市 |
| Fragility | 50/200DMA、等权/市值权重相对强弱；QQQ 另看半导体 | 衡量市场内部结构 |
| Panic/Stress | VIX/VXN、回撤、HY OAS | 确认压力并寻找逆向买入条件 |

这五个模块不会被简单平均成一个总分。同一风险源（例如 CAPE 与 Buffett Indicator）不会重复加权。

## Escalation Gate

只有 52 周回撤达到 **-10%** 才启用。它检查三个实时信号：

- 最近 24 个月出现过 10Y-3M 倒挂；
- Real Fed Funds ≥ 1.5%；
- HY OAS 较 52 周低点扩大 ≥ 200bp。

| 信号数 | 模型判断 |
|---:|---|
| 0 | 普通调整概率更高 |
| 1 | Watch |
| 2 | Bear Escalation |
| 3 | Severe Bear Risk |

这些阈值是待回测的 v1 规则，不代表事件概率。

## VOO 与 QQQ 独立阈值

VOO 使用 VIX；QQQ 使用 VXN，并额外观察 QQEW/QQQ 与 SMH/QQQ。

| 标的 | Normal | Watch | Stress | Panic | Extreme | Systemic |
|---|---:|---:|---:|---:|---:|---:|
| VOO / VIX | <20 | 20–25 | 25–30 | 30–40 | 40–60 | ≥60 |
| QQQ / VXN | <25 | 25–30 | 30–35 | 35–45 | 45–60 | ≥60 |

实际判断同时使用绝对阈值与五年滚动百分位。

## Panic Buy Engine

所有比例均针对预先独立留出的 **Crash Reserve**，不是整个投资组合。

| 市场阶段 | 核心条件 | 本档预备资金 |
|---|---|---:|
| Initial Correction | 回撤 10–15% + Stress | 10–15% |
| Deep Correction | 回撤 15–20% + Panic | 20% |
| Bear Market | 回撤 20–30% + Panic | 25% |
| Extreme Panic | VIX≥40 / VXN≥45 + 大回撤 | 15–20% |
| Recovery | 3 项修复条件满足 2 项 | 25–30% |

若 Sahm 劳动力预警同时得到信用或 NFCI 的确认，系统会把恐慌买入档降至 10–15%，避免在衰退型熊市中过早耗尽资金。

Recovery 的三项条件是：本轮回撤期间波动率曾进入 Panic 且自峰值回落至少 20%、HY OAS 不再扩大、趋势与等权参与度改善。

## 数据

- Yahoo Finance：VOO/QQQ 价格、VIX/VXN、RSP/SPY、QQEW/QQQ、SMH/QQQ。
- FRED：DGS10、DGS3MO、FEDFUNDS、CPIAUCSL、SAHMREALTIME、BAMLH0A0HYM2、NFCI。
- CAPE 与 Buffett Indicator：在侧边栏手动校准，避免把低频或滞后数据伪装成实时数据。

若在线数据失败，Dashboard 会明确进入演示/备用模式；此时不得把结果用于投资决策。

## 安装与运行

```bash
git clone https://github.com/fy19/US_Stock_Crash_Monitor.git
cd US_Stock_Crash_Monitor
python -m pip install -r requirements.txt
streamlit run app.py
```

运行模型测试：

```bash
python -m unittest discover -s tests -v
```

## 当前限制

- Fragility 使用 ETF 趋势与等权相对强弱作为 breadth 代理，并非真实成分股 breadth。
- CAPE/Buffett 的 0–100 值为透明的历史区间近似；完整回测应使用 point-in-time 历史百分位。
- 尚未完成 1995–2026 的逐日无前视偏差回测。
- HY OAS、宏观数据和免费行情源可能存在发布滞后或修订。

下一阶段应建立 Daily Backtest v1，报告 Precision、Recall、False Positive、Lead Time、Max Drawdown、CAGR 与 Sortino，并单独校准 VOO 和 QQQ。

## 免责声明

本项目仅供编程学习和量化研究，不构成投资建议。历史关系不保证未来表现。
