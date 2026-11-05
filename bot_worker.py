"""NEON scheduled paper trader. No real orders or API credentials."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

STATE = Path(__file__).with_name('paper_state.json')
START_CASH = 50.0
FEE = 0.001
MAX_BUY_EUR = 5.0
STOP_LOSS = 0.05
TAKE_PROFIT = 0.14
MAX_DAILY_LOSS_EUR = 2.0
FAST, SLOW = 9, 21


def fetch():
    response = requests.get('https://api.kraken.com/0/public/OHLC', params={'pair': 'XBTEUR', 'interval': 5}, timeout=20)
    response.raise_for_status()
    payload = response.json()
    if payload.get('error'):
        raise RuntimeError(str(payload['error']))
    data = payload['result']
    key = next(k for k in data if k != 'last')
    rows = data[key]
    if len(rows) < SLOW + 3:
        raise RuntimeError('Not enough candles')
    # Kraken's final row is the still-open candle. Never use it for signals or execution.
    closed = rows[:-1]
    closes = [float(row[4]) for row in closed]
    if any(not (0 < x < float('inf')) for x in closes[-SLOW-2:]):
        raise RuntimeError('Invalid prices')
    return str(int(closed[-1][0])), closes


def default_state():
    return {'cash': START_CASH, 'btc': 0.0, 'entry_eur': 0.0, 'last_candle': '',
            'day': '', 'day_start_equity': START_CASH, 'trades': []}


def main():
    state = json.loads(STATE.read_text()) if STATE.exists() else default_state()
    candle, closes = fetch()
    if state.get('last_candle') == candle:
        print('Already processed candle', candle)
        return
    price = closes[-1]
    now = datetime.now(timezone.utc)
    day = now.strftime('%Y-%m-%d')
    cash = float(state['cash'])
    btc = float(state['btc'])
    equity = cash + btc * price
    if state.get('day') != day:
        state['day'] = day
        state['day_start_equity'] = equity
    daily_loss_hit = equity <= float(state['day_start_equity']) - MAX_DAILY_LOSS_EUR
    fast_now = sum(closes[-FAST:]) / FAST
    slow_now = sum(closes[-SLOW:]) / SLOW
    fast_prev = sum(closes[-FAST-1:-1]) / FAST
    slow_prev = sum(closes[-SLOW-1:-1]) / SLOW
    buy_signal = fast_prev <= slow_prev and fast_now > slow_now
    sell_signal = fast_prev >= slow_prev and fast_now < slow_now
    action = None
    reason = ''
    if btc > 0:
        entry = float(state['entry_eur'])
        if price <= entry * (1 - STOP_LOSS):
            reason = 'stop-loss check'
        elif price >= entry * (1 + TAKE_PROFIT):
            reason = 'take-profit check'
        elif sell_signal:
            reason = 'SMA SELL crossover'
        elif daily_loss_hit:
            reason = 'daily loss limit'
        if reason:
            proceeds = btc * price * (1 - FEE)
            state['cash'] = round(cash + proceeds, 10)
            state['btc'] = 0.0
            state['entry_eur'] = 0.0
            action = 'SELL'
    elif buy_signal and not daily_loss_hit:
        budget = min(MAX_BUY_EUR, cash)
        if budget >= 1.0:
            state['btc'] = budget / (price * (1 + FEE))
            state['cash'] = round(cash - budget, 10)
            state['entry_eur'] = price
            reason = 'SMA BUY crossover'
            action = 'BUY'
    if action:
        state['trades'].insert(0, {'utc': now.isoformat(timespec='seconds'), 'side': action,
                                   'price_eur': round(price, 2), 'reason': reason,
                                   'equity_eur_after': round(float(state['cash']) + float(state['btc']) * price, 2)})
        state['trades'] = state['trades'][:100]
    state['last_candle'] = candle
    state['last_price_eur'] = round(price, 2)
    state['last_checked_utc'] = now.isoformat(timespec='seconds')
    state['equity_eur'] = round(float(state['cash']) + float(state['btc']) * price, 2)
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + '\n')
    print(f'{now.isoformat()} price={price:.2f} action={action or "HOLD"} equity={state["equity_eur"]}')


if __name__ == '__main__':
    main()
