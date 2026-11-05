# NEON Trading Terminal — paper-trading demo

Starts with €50 of VIRTUAL money (not a real deposit). A dark neon-blue Streamlit dashboard inspired by the supplied video. This is an original recreation, not the original video's source code or trading algorithm.

## Install (Windows / macOS / Linux)
1. Install Python 3.11 or 3.12 from https://www.python.org/downloads/ (on Windows check **Add Python to PATH**).
2. Extract the ZIP, open a terminal in the `neon_trading_bot` folder.
3. Create a virtual environment:
   - Windows: `py -m venv .venv` then `.venv\Scripts\activate`
   - macOS/Linux: `python3 -m venv .venv` then `source .venv/bin/activate`
4. Install: `python -m pip install -r requirements.txt`
5. Start: `python -m streamlit run app.py`
6. Open the local URL printed by Streamlit, usually http://localhost:8501

## How to use
Choose BTC, ETH or SOL and a candle interval. Press BUY or SELL ALL to simulate orders. Toggle **Enable automated paper trades** to trade SMA crossovers on completed candles when live data is available. Click **Refresh market data** to check for new candles. Stop-loss and take-profit are only checked during app execution; this is not a continuously running execution engine.

## Limitations and safety
- **Paper trading only**: No exchange keys, no real orders, no guarantee of profit.
- Binance public candle endpoint may be blocked in some regions. In that case the app displays clearly labeled synthetic demonstration candles and disables automated trades.
- Trades, cash, and positions are session-only, not stored permanently.
- Portfolio value for holdings in other selected markets uses their last entry price, not a current market quote.
- 0.1% illustrative transaction fee; does not model spreads, slippage, tax or funding.
- Do not use this code for live money without substantial testing, persistent state, secure credentials, robust error handling, exchange-specific order sizing and independent risk controls.

## Android phone: easiest installation (no terminal)
Streamlit is a Python web app. The most practical Android route is to host it on Streamlit Community Cloud and open it in Chrome. You will need free GitHub and Streamlit Community Cloud accounts.

1. On Android, download and extract this ZIP with Files by Google or another ZIP manager.
2. Go to https://github.com/new in Chrome (enable Desktop site if needed). Create a new public repository, e.g. `neon-eur-bot`.
3. In the repository, select **Add file > Upload files**. Upload `app.py` and `requirements.txt` from inside the extracted `neon_trading_bot` folder (not the ZIP itself). Commit changes.
4. Open https://share.streamlit.io/ and sign in with GitHub. Choose **Create app / Deploy a public app**. Select your repository, branch `main`, and main file path `app.py`, then deploy.
5. Wait for package installation, then open the provided Streamlit URL in Chrome. Use Chrome menu **Add to Home screen** for an app-like shortcut.
6. The dashboard starts with €50 of *virtual* cash. Enable automated *paper* trades only if you want to simulate trading.

**Important:** This is not a continuously running background bot. Free cloud hosting can sleep; session data can reset; price feeds can be unavailable. The app never connects to an exchange account or deposits or trades real euros.
