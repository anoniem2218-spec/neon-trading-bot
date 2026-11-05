from datetime import datetime, timezone
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

st.set_page_config(page_title="NEON | Trading Bot", page_icon="⚡", layout="wide")
st.markdown("""<style>
.stApp{background:#080c18;color:#e9f1ff}
[data-testid="stMetric"]{background:#111a30;border:1px solid #275cf3;border-radius:12px;padding:12px}
h1,h2,h3{color:#eaf1ff}
.stButton button{border:1px solid #3778ff;background:#122044;color:white}
</style>""", unsafe_allow_html=True)

START_BALANCE = 50.0
FEE_RATE = 0.001
PAIRS = {"BTC/EUR": "XBTEUR", "ETH/EUR": "ETHEUR", "SOL/EUR": "SOLEUR"}
INTERVALS = {"1m": 1, "5m": 5, "15m": 15, "1h": 60}

@st.cache_data(ttl=35, show_spinner=False)
def candles(symbol, interval):
    response = requests.get(
        "https://api.kraken.com/0/public/OHLC",
        params={"pair": PAIRS[symbol], "interval": INTERVALS[interval]},
        timeout=12,
        headers={"User-Agent": "NEON-Paper-Trading-Demo/1.0"},
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise ValueError("Kraken: " + ", ".join(payload["error"]))
    result = payload.get("result", {})
    pair_keys = [key for key in result if key != "last"]
    if not pair_keys:
        raise ValueError("Geen koersgegevens ontvangen")
    rows = result[pair_keys[0]]
    if len(rows) < 25:
        raise ValueError("Te weinig koersgegevens")
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "vwap", "volume", "count"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="raise")
    if not np.isfinite(df[["open", "high", "low", "close"]].to_numpy()).all():
        raise ValueError("Ongeldige koersen")
    # The last Kraken OHLC candle is still forming.
    return df.tail(220).reset_index(drop=True)

if "account" not in st.session_state:
    st.session_state.account = {"cash": START_BALANCE, "positions": {}, "entries": {},
                                "trades": [], "last_candle": {}, "events": []}
a = st.session_state.account

def log(message):
    a["events"].insert(0, {"Time": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"), "Event": message})
    a["events"] = a["events"][:60]

def trade(side, symbol, price, quantity, reason):
    if not np.isfinite(price) or price <= 0 or not np.isfinite(quantity) or quantity <= 0:
        return False
    held = a["positions"].get(symbol, 0.0)
    fee = price * quantity * FEE_RATE
    if side == "BUY":
        cost = price * quantity + fee
        if cost > a["cash"] + 1e-8:
            return False
        old_cost = a["entries"].get(symbol, price) * held
        a["cash"] -= cost
        a["positions"][symbol] = held + quantity
        a["entries"][symbol] = (old_cost + price * quantity) / (held + quantity)
    else:
        if quantity > held + 1e-10:
            return False
        a["cash"] += price * quantity - fee
        remaining = max(0.0, held - quantity)
        if remaining < 1e-10:
            a["positions"].pop(symbol, None)
            a["entries"].pop(symbol, None)
        else:
            a["positions"][symbol] = remaining
    a["trades"].insert(0, {
        "Time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "Side": side, "Market": symbol, "Price EUR": round(price, 5),
        "Quantity": round(quantity, 8), "Fee EUR": round(fee, 4), "Reason": reason,
    })
    log(f"{side} {quantity:.7f} {symbol} @ €{price:,.2f} ({reason})")
    return True

st.title("⚡ NEON / TRADING TERMINAL")
st.caption("€50 VIRTUEEL STARTSALDO · ALLEEN OEFENEN · GEEN ECHT GELD")
with st.sidebar:
    st.header("⚙️ Bot instellingen")
    symbol = st.selectbox("Markt", list(PAIRS))
    interval = st.selectbox("Kaarsinterval", list(INTERVALS), index=1)
    auto = st.toggle("🤖 Automatisch oefenen AAN/UIT", value=False,
                     help="Werkt alleen wanneer deze Streamlit-app wordt uitgevoerd/vernieuwd.")
    allocation = st.slider("Inzet per automatische aankoop (%)", 1, 25, 10)
    stop_loss = st.slider("Stop-loss (%)", 1, 15, 5)
    take_profit = st.slider("Take-profit (%)", 1, 30, 10)
    fast_period = st.number_input("Snelle SMA", 3, 40, 9)
    slow_period = st.number_input("Langzame SMA", int(fast_period) + 1, 100, max(21, int(fast_period) + 1))
    if st.button("🔄 Vernieuw koersen"):
        st.cache_data.clear()
        st.rerun()
    if st.button("Reset virtuele rekening"):
        st.session_state.account = {"cash": START_BALANCE, "positions": {}, "entries": {},
                                    "trades": [], "last_candle": {}, "events": []}
        st.rerun()

try:
    df = candles(symbol, interval)
    live = True
    error_message = ""
except Exception as exc:
    live = False
    error_message = str(exc)
    df = None

if not live:
    st.error("⚠️ Geen echte koersen beschikbaar. Automatisch en handmatig handelen zijn tijdelijk geblokkeerd.")
    st.caption("Technische melding: " + error_message)
    st.info("Probeer 'Vernieuw koersen' in het zijmenu. Er worden geen nepkoersen als echte prijzen getoond.")
    st.stop()

st.success("🟢 Echte marktgegevens via Kraken (kunnen vertraagd zijn) · prijzen in EUR")
df["fast"] = df["close"].rolling(int(fast_period)).mean()
df["slow"] = df["close"].rolling(int(slow_period)).mean()
price = float(df["close"].iloc[-1])
previous = float(df["close"].iloc[-2])
change = 100 * (price / previous - 1)
fast_now = float(df["fast"].iloc[-1])
slow_now = float(df["slow"].iloc[-1])

# Only evaluate the last fully completed candle; do not trade on a forming candle.
completed = df.iloc[-2]
prior = df.iloc[-3]
completed_key = str(completed["timestamp"])
if pd.notna(completed["fast"]) and pd.notna(completed["slow"]) and pd.notna(prior["fast"]) and pd.notna(prior["slow"]):
    signal = ("BUY" if prior["fast"] <= prior["slow"] and completed["fast"] > completed["slow"]
              else "SELL" if prior["fast"] >= prior["slow"] and completed["fast"] < completed["slow"]
              else "HOLD")
else:
    signal = "HOLD"

held = a["positions"].get(symbol, 0.0)
entry = a["entries"].get(symbol, price)
if auto and a["last_candle"].get((symbol, interval)) != completed_key:
    a["last_candle"][(symbol, interval)] = completed_key
    if held > 0 and price <= entry * (1 - stop_loss / 100):
        trade("SELL", symbol, price, held, "Stop-loss (controle bij refresh)")
    elif held > 0 and price >= entry * (1 + take_profit / 100):
        trade("SELL", symbol, price, held, "Take-profit (controle bij refresh)")
    elif held > 0 and signal == "SELL":
        trade("SELL", symbol, price, held, "SMA signaal")
    elif held <= 0 and signal == "BUY":
        quantity = (a["cash"] * allocation / 100) / (price * (1 + FEE_RATE))
        trade("BUY", symbol, price, quantity, "SMA signaal")

# Estimate other holdings at their entry price, clearly labeled below.
portfolio = a["cash"] + sum(q * (price if s == symbol else a["entries"].get(s, 0))
                              for s, q in a["positions"].items())
cols = st.columns(4)
cols[0].metric("Market price", f"€{price:,.2f}", f"{change:+.2f}% laatste kaars")
cols[1].metric("Portfolio (geschat)", f"€{portfolio:,.2f}", f"€{portfolio-START_BALANCE:+,.2f} t.o.v. start")
cols[2].metric("Virtueel beschikbaar", f"€{a['cash']:,.2f}")
cols[3].metric("SMA trend", "BULLISH 🟢" if fast_now > slow_now else "BEARISH 🔴")

left, right = st.columns([2.2, 1])
with left:
    st.subheader(f"📊 {symbol} / Candles")
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df.timestamp, open=df.open, high=df.high, low=df.low,
                                 close=df.close, name="Prijs", increasing_line_color="#00e18c",
                                 decreasing_line_color="#ff5b5b"))
    fig.add_trace(go.Scatter(x=df.timestamp, y=df.fast, name=f"SMA {fast_period}",
                             line=dict(color="#3c9dff", width=2)))
    fig.add_trace(go.Scatter(x=df.timestamp, y=df.slow, name=f"SMA {slow_period}",
                             line=dict(color="#ffc857", width=2)))
    fig.update_layout(template="plotly_dark", paper_bgcolor="#0b1120", plot_bgcolor="#0b1120",
                      height=470, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)
    st.caption("SMA-signalen zijn geen voorspellingen. De laatste kaars is nog niet afgesloten.")
with right:
    st.subheader("🤖 Analyst")
    st.metric("Signaal afgesloten kaars", signal)
    st.write(f"Snelle SMA: **€{fast_now:,.2f}**")
    st.write(f"Langzame SMA: **€{slow_now:,.2f}**")
    st.write("Automation:", "**ON (virtueel)**" if auto else "**OFF**")
    st.divider()
    st.subheader("🕹️ Handmatig oefenen")
    amount = st.number_input("Virtuele EUR om te kopen", min_value=1.0, max_value=50.0, value=5.0, step=1.0)
    buy_col, sell_col = st.columns(2)
    if buy_col.button("🟢 BUY", use_container_width=True):
        if trade("BUY", symbol, price, amount / (price * (1 + FEE_RATE)), "Handmatig"):
            st.rerun()
        st.error("Onvoldoende virtueel saldo")
    if sell_col.button("🔴 SELL ALL", use_container_width=True):
        if trade("SELL", symbol, price, a["positions"].get(symbol, 0.0), "Handmatig"):
            st.rerun()
        st.error("Geen positie om te verkopen")
    st.write(f"Virtueel bezit: **{a['positions'].get(symbol, 0.0):.7f} {symbol.split('/')[0]}**")

p, t = st.columns(2)
with p:
    st.subheader("💼 Posities")
    if a["positions"]:
        st.dataframe(pd.DataFrame([{"Market": s, "Quantity": round(q, 8),
                                   "Gemiddelde instap EUR": round(a["entries"].get(s, 0), 4)}
                                  for s, q in a["positions"].items()]),
                     hide_index=True, use_container_width=True)
    else:
        st.info("Geen open virtuele posities")
    st.subheader("📜 Trade history")
    if a["trades"]:
        st.dataframe(pd.DataFrame(a["trades"]), hide_index=True, use_container_width=True)
with t:
    st.subheader("📡 Bot activity")
    if a["events"]:
        st.dataframe(pd.DataFrame(a["events"]), hide_index=True, use_container_width=True)
    st.warning("Automatische controles werken alleen bij een actieve app-run/vernieuwing. Stop-loss is NIET gegarandeerd en werkt niet continu.")
st.caption("Virtueel oefenprogramma. Trades en saldo bestaan alleen in de huidige Streamlit-sessie en kunnen bij herstart verdwijnen. Andere posities zijn gewaardeerd tegen hun instapprijs, niet de huidige marktprijs. Geen echt geld of echte orders.")
