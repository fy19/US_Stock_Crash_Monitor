### Disclaimer: The tool is written in Gemini3 and currently has the best compatibility with VOO (S&P 500); the thresholds for each indicator are based on the thresholds before the crashes in 2000, 2008, and 2021.
# **🚨 Wall Street Quant: US Stock Crash Monitor**

**A full-stack quantitative analysis tool built with Python and Streamlit. It integrates macroeconomic indicators and technical analysis to monitor crash risks for the S\&P 500 (VOO) and Nasdaq 100 (QQQ) in real-time.**

### [**🇨🇳 View Chinese Version / 中文文档**](https://github.com/middletoo/US_Stock_Crash_Monitor/blob/main/README.md)

**Note:** This tool was developed with the assistance of Gemini. Currently, it is best optimized for **VOO (S\&P 500\)**.

## **📖 Introduction**

In financial markets, single indicators can often be deceptive. This project aims to build a **Multi-factor Risk-Weighted Model**. By integrating Wall Street's most-watched macro valuation metrics (e.g., the Buffett Indicator, Shiller PE) with technical indicators (e.g., Moving Average Deviation, Treasury Yield Curve), it calculates a comprehensive **"Crash Risk Score."**

The tool helps investors stay rational during periods of extreme market euphoria and identify opportunities during extreme panic, avoiding the "herd mentality."
![](https://github.com/middletoo/US_Stock_Crash_Monitor/blob/main/main.png?raw=true)
## **✨ Core Features & Advantages**

* **Multi-dimensional Quantitative Model**: More than just price tracking; it's a comprehensive scoring system combining **Macro**, **Valuation**, **Sentiment**, and **Technical** factors.  
* **Dual Asset Switching**: Supports seamless switching between **VOO (S\&P 500\)** and **QQQ (Nasdaq 100\)**, with independent analysis for assets with different volatility profiles.  
* **High Customizability**:  
  * **Weight Adjustment**: Users can dynamically adjust the weight of each indicator based on the current market environment (e.g., high-interest rate environments or AI bubbles).  
  * **Manual Calibration**: For non-real-time API data like GDP, a sidebar is provided for manual input with links to authoritative data sources to ensure precision.  
* **Robust Design**: Built-in network fault tolerance. If the Yahoo Finance API fails to connect, it automatically switches to a **Demo Mode** to prevent the application from crashing.  
* **Historical Comparison**: Provides threshold references for key historical crashes (e.g., 2000, 2008, 2021\) to learn from the past.  
* **Interactive Charts**: High-performance interactive K-line charts and dashboards rendered using Plotly.

## **🛠️ Monitoring Indicator System**

The model calculates risk based on 5 core factors (default weights are adjustable):

1. **Buffett Indicator**: Total US Market Cap / US GDP. Measures the overall degree of the stock market bubble.  
2. **Shiller PE (CAPE)**: Inflation-adjusted cyclically adjusted price-to-earnings ratio; a valuation benchmark that spans bull and bear markets.  
3. **Treasury Yield Curve (10Y-2Y Spread)**: A famous recession warning indicator, specifically monitoring the high-risk moment when the curve "uninverts" after a period of inversion.  
4. **200-Day Moving Average Deviation**: Measures how much the short-term price deviates from the long-term trend to determine if an asset is severely overbought.  
5. **Fear & Greed Index**: A contrarian indicator; extreme greed often signals a short-term market top.

## **🚀 Quick Start**

### **Prerequisites**

* Python 3.8 or higher

### **Installation Steps**

1. **Clone the Repository**  
   git clone \[https://github.com/middletoo/US\_Stock\_Crash\_Monitor.git\](https://github.com/middletoo/US\_Stock\_Crash\_Monitor.git)  
   cd US\_Stock\_Crash\_Monitor

2. Install Dependencies  
   It is recommended to use a virtual environment:  
   pip install streamlit yfinance pandas numpy plotly

3. **Run the Application**  
   streamlit run app.py

4. Access the App  
   The browser will automatically open http://localhost:8501.
5. Configuration parameters (Important)  
   After launching, please follow the prompts in the left sidebar of the application page, click the link to obtain the latest GDP, PE, and other values, and manually enter them for accurate analysis.
   
## **⚠️ Limitations**

* **Data Lag**: Some macro data (like GDP) is updated quarterly and cannot reflect real-time intraday changes. Thus, the Buffett Indicator is better for long-term trends than short-term timing.  
* **Linear Weighting Flaw**: The current model uses linear weighted summation, whereas real market crashes are often non-linear chain reactions triggered by "Black Swan" events.  
* **API Constraints**: Relies on the free yfinance interface, which may have rate limits or connectivity issues in certain regions (proxy settings are built-in).  
* **Subjective Factors**: While the model is quantitative, inputs (like GDP forecasts) and weight settings still involve user subjectivity.

## **🛡️ Disclaimer**

**This project is for programming education and quantitative research purposes only. It does not constitute any investment advice.**

* Financial markets involve significant risk; invest with caution.  
* The "Risk Score" provided by this tool is based on historical statistical data; past performance does not guarantee future results.  
* The author is not responsible for any financial losses resulting from the use of this code.

**If you find this project helpful, please give it a ⭐️ Star\!**
