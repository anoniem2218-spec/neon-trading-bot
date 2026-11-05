import time
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title='NEON | Trading Bot', page_icon='📈', layout='wide')
st.markdown('''<style>
.stApp{background:#080c18;color:#e9f1ff} [data-testid="stMetric"]{background:#111a30;border:1px solid #275cf3;border-radius:12px;padding:12px} div[data-testid="stVerticalBlockBorderWrapper"]>div{border-color:#275cf3!important} h1,h2,h3{color:#eaf1ff} .stButton button{border:1px solid #3778ff;background:#122044;color:white} .stButton button:hover{background:#2352bd;color:white}
</style>''',unsafe_allow_html=True)

START_BALANCE=50.0
SYMBOLS={'BTC/USDT':'BTCUSDT','ETH/USDT':'ETHUSDT','SOL/USDT':'SOLUSDT'}
@st.cache_data(ttl=40,show_spinner=False)
def candles(symbol, interval):
    import requests
    r=requests.get('https://api.binance.com/api/v3/klines',params={'symbol':SYMBOLS[symbol],'interval':interval,'limit':220},timeout=8)
    r.raise_for_status()
    data=r.json()
    if not isinstance(data,list) or not data: raise ValueError('Market data unavailable')
    df=pd.DataFrame(data)
    df=df.iloc[:,:6];df.columns=['timestamp','open','high','low','close','volume']
    df['timestamp']=pd.to_datetime(df['timestamp'],unit='ms',utc=True)
    for c in ['open','high','low','close','volume']:df[c]=pd.to_numeric(df[c])
    return df

@st.cache_data(ttl=40,show_spinner=False)
def eur_conversion():
    import requests
    r=requests.get('https://api.binance.com/api/v3/ticker/price',params={'symbol':'EURUSDT'},timeout=8)
    r.raise_for_status()
    rate=float(r.json()['price'])
    if not np.isfinite(rate) or rate<=0: raise ValueError('Invalid EUR exchange rate')
    return rate

def fallback(symbol,interval):
    # Synthetic prices are explicitly labeled and NEVER presented as live market data.
    seed={'BTC/USDT':69000,'ETH/USDT':3200,'SOL/USDT':160}[symbol]
    rng=np.random.default_rng(42)
    steps=rng.normal(0,.003,220)
    close=seed*np.exp(np.cumsum(steps))
    opens=np.r_[close[0],close[:-1]]
    spread=np.abs(rng.normal(.002,.001,220))*close
    freq={'1m':'min','5m':'5min','15m':'15min','1h':'h'}[interval]
    return pd.DataFrame({'timestamp':pd.date_range(end=pd.Timestamp.now(tz='UTC'),periods=220,freq=freq),'open':opens,'high':np.maximum(opens,close)+spread,'low':np.minimum(opens,close)-spread,'close':close,'volume':rng.integers(10,100,220)})

if 'account' not in st.session_state:
    st.session_state.account={'cash':START_BALANCE,'positions':{},'trades':[],'events':[],'last_candle':{},'entries':{}}
a=st.session_state.account

def event(message):
    a['events'].insert(0,{'Time':datetime.now(timezone.utc).strftime('%H:%M:%S UTC'),'Event':message})
    a['events']=a['events'][:80]

def trade(side,symbol,price,quantity,reason):
    if not np.isfinite(price) or price<=0 or not np.isfinite(quantity) or quantity<=0:return False
    fee=price*quantity*.001
    held=a['positions'].get(symbol,0.)
    if side=='BUY':
        cost=price*quantity+fee
        if cost>a['cash']+1e-8:return False
        a['cash']-=cost;a['positions'][symbol]=held+quantity;a['entries'][symbol]=price
    else:
        if quantity>held+1e-10:return False
        a['cash']+=price*quantity-fee;a['positions'][symbol]=max(0.,held-quantity)
        if a['positions'][symbol]<1e-10:a['positions'].pop(symbol,None);a['entries'].pop(symbol,None)
    a['trades'].insert(0,{'Time':datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),'Side':side,'Symbol':symbol,'Price':round(price,5),'Quantity':round(quantity,8),'Fee':round(fee,4),'Reason':reason})
    event(f'{side} {quantity:.6f} {symbol} @ €{price:,.2f} ({reason})')
    return True

st.title('⚡ NEON / TRADING TERMINAL')
st.caption('€50 VIRTUAL STARTING BALANCE · PAPER TRADING ONLY · No real-money orders')
with st.sidebar:
    st.header('⚙️ Bot controls')
    symbol=st.selectbox('Market',list(SYMBOLS))
    interval=st.selectbox('Candle interval',['1m','5m','15m','1h'],index=1)
    auto=st.toggle('Enable automated paper trades',value=False)
    allocation=st.slider('Allocation per trade (%)',1,25,10)
    stop_loss=st.slider('Stop loss (%)',1,15,5)
    take_profit=st.slider('Take profit (%)',1,30,10)
    short=st.number_input('Fast SMA candles',min_value=3,max_value=40,value=9)
    long=st.number_input('Slow SMA candles',min_value=short+1,max_value=100,value=max(short+1,21))
    if st.button('🔄 Refresh market data'):st.cache_data.clear();st.rerun()
    if st.button('Reset paper account'):
        st.session_state.account={'cash':START_BALANCE,'positions':{},'trades':[],'events':[],'last_candle':{},'entries':{}}
        st.rerun()

try:
    df=candles(symbol,interval)
    eur_usdt=eur_conversion()
    for c in ['open','high','low','close']: df[c]=df[c]/eur_usdt
    source='LIVE PUBLIC MARKET DATA (Binance; may be delayed)'
    live=True
except Exception as ex:
    df=fallback(symbol,interval)
    eur_usdt=None
    source='SYNTHETIC DEMO DATA — NOT LIVE'
    live=False
    st.warning('Live market feed unavailable. Showing synthetic demonstration candles. Automated trading is disabled until live data returns.')

df['fast']=df.close.rolling(short).mean();df['slow']=df.close.rolling(long).mean()
price=float(df.close.iloc[-1]);previous=float(df.close.iloc[-2]);change=(price/previous-1)*100
fast_now=float(df.fast.iloc[-1]);slow_now=float(df.slow.iloc[-1]);fast_prev=float(df.fast.iloc[-2]);slow_prev=float(df.slow.iloc[-2])
signal='BUY' if fast_prev<=slow_prev and fast_now>slow_now else 'SELL' if fast_prev>=slow_prev and fast_now<slow_now else 'HOLD'
held=a['positions'].get(symbol,0.)
entry=a['entries'].get(symbol,price)
# A signal is evaluated at most once per completed candle. The final candle is still forming.
completed=df.iloc[-2]
completed_key=str(completed.timestamp)
cf=float(df.fast.iloc[-2]);cs=float(df.slow.iloc[-2]);pf=float(df.fast.iloc[-3]);ps=float(df.slow.iloc[-3])
completed_signal='BUY' if pf<=ps and cf>cs else 'SELL' if pf>=ps and cf<cs else 'HOLD'
if auto and live and a['last_candle'].get((symbol,interval))!=completed_key:
    a['last_candle'][(symbol,interval)]=completed_key
    if held>0 and price<=entry*(1-stop_loss/100):trade('SELL',symbol,price,held,'Stop loss')
    elif held>0 and price>=entry*(1+take_profit/100):trade('SELL',symbol,price,held,'Take profit')
    elif completed_signal=='SELL' and held>0:trade('SELL',symbol,price,held,'SMA crossover')
    elif completed_signal=='BUY' and held<=0:
        qty=a['cash']*allocation/100/(price*1.001)
        trade('BUY',symbol,price,qty,'SMA crossover')

value=a['cash']+sum(q*(price if s==symbol else a['entries'].get(s,0)) for s,q in a['positions'].items())
st.caption(source + (' · EUR converted using current EUR/USDT quote' if live else ''))
cols=st.columns(4)
cols[0].metric('Market price',f'€{price:,.2f}',f'{change:+.2f}% last candle')
cols[1].metric('Portfolio (estimated)',f'€{value:,.2f}',f'€{value-START_BALANCE:+,.2f} vs starting cash')
cols[2].metric('Available virtual cash',f'€{a["cash"]:,.2f}')
cols[3].metric('SMA trend','BULLISH 🟢' if fast_now>slow_now else 'BEARISH 🔴')
left,right=st.columns([2.3,1])
with left:
    st.subheader(f'📊 {symbol} / Candles')
    fig=go.Figure()
    fig.add_trace(go.Candlestick(x=df.timestamp,open=df.open,high=df.high,low=df.low,close=df.close,name='Price',increasing_line_color='#00e18c',decreasing_line_color='#ff5b5b'))
    fig.add_trace(go.Scatter(x=df.timestamp,y=df.fast,name=f'SMA {short}',line=dict(color='#3c9dff',width=2)))
    fig.add_trace(go.Scatter(x=df.timestamp,y=df.slow,name=f'SMA {long}',line=dict(color='#ffc857',width=2)))
    fig.update_layout(template='plotly_dark',paper_bgcolor='#0b1120',plot_bgcolor='#0b1120',height=475,xaxis_rangeslider_visible=False,margin=dict(l=15,r=15,t=15,b=15),legend=dict(orientation='h'))
    st.plotly_chart(fig,use_container_width=True)
    st.caption('Strategy: simple moving-average crossover on completed candles. Signals are not predictions or guaranteed profits.')
with right:
    st.subheader('🤖 Analyst')
    st.metric('Latest candle signal',signal)
    st.write(f'Fast SMA: **€{fast_now:,.2f}**')
    st.write(f'Slow SMA: **€{slow_now:,.2f}**')
    st.write('Automation:', '**ON**' if auto and live else '**OFF**')
    st.divider()
    st.subheader('🕹️ Manual paper trades')
    eur=st.number_input('Virtual EUR to buy',min_value=1.,max_value=50.,value=5.,step=1.)
    b,s=st.columns(2)
    if b.button('🟢 BUY',use_container_width=True):
        if trade('BUY',symbol,price,eur/(price*1.001),'Manual'):st.success('Virtual buy executed');st.rerun()
        else:st.error('Not enough virtual cash.')
    if s.button('🔴 SELL ALL',use_container_width=True):
        if trade('SELL',symbol,price,a['positions'].get(symbol,0.),'Manual'):st.success('Virtual sell executed');st.rerun()
        else:st.error('No position to sell.')
    st.write(f'Current holding: **{a["positions"].get(symbol,0.):.7f} {symbol.split("/")[0]}**')

p,t=st.columns(2)
with p:
    st.subheader('💼 Positions')
    if a['positions']:
        st.dataframe(pd.DataFrame([{'Market':s,'Quantity':round(q,8),'Last known entry':round(a['entries'].get(s,0),4)} for s,q in a['positions'].items()]),hide_index=True,use_container_width=True)
    else:st.info('No open paper positions.')
    st.subheader('📜 Trade history')
    if a['trades']:st.dataframe(pd.DataFrame(a['trades']),hide_index=True,use_container_width=True)
    else:st.caption('No trades yet.')
with t:
    st.subheader('📡 Bot activity')
    if a['events']:st.dataframe(pd.DataFrame(a['events']),hide_index=True,use_container_width=True)
    else:st.caption('Waiting for trading activity.')
    st.info('Risk controls are evaluated when the app runs or refreshes. They are NOT guaranteed stops and do not operate while the app is closed.')
st.caption('Refresh manually for new candles. Positions and history are stored in this browser session only; reloading the server can reset them. Other market holdings use their last entry price for the estimated portfolio value.')
