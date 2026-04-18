import numpy as np
import pandas as pd
import os
from datetime import datetime, timedelta, timezone
import warnings

warnings.filterwarnings('ignore')
np.random.seed(42)

# ═══════════════════════════════════════════════════
# 1. PATH CONFIGURATION (THE DEEP FIX)
# ═══════════════════════════════════════════════════
# This forces the script to only care about where it is currently sitting
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

# ═══════════════════════════════════════════════════
# 2. DATA GENERATION & INDICATORS
# ═══════════════════════════════════════════════════

def generate_eurusd_m5(start_date="2026-01-02", end_date="2026-04-18"):
    start = pd.Timestamp(start_date, tz='UTC')
    end = pd.Timestamp(end_date, tz='UTC') + pd.Timedelta(days=1)
    idx = pd.date_range(start, end, freq='5min', tz='UTC')
    idx = idx[idx.day_of_week < 5]
    n = len(idx)
    
    price = 1.0450
    prices = []
    regime = 1
    regime_days = 0
    regime_dur = np.random.randint(10, 25)
    vol_state = 0.00008

    for i in range(n):
        ts = idx[i]
        if i > 0 and idx[i].date() != idx[i-1].date():
            regime_days += 1
            if regime_days >= regime_dur:
                regime *= -1
                regime_days = 0
                regime_dur = np.random.randint(10, 25)

        sess_mult = 1.8 if 7 <= ts.hour < 11 else 1.6 if 12 <= ts.hour < 16 else 0.5
        shock = abs(np.random.normal(0, 1))
        vol_state = 0.85 * vol_state + 0.15 * (vol_state * shock)
        vol_state = np.clip(vol_state, 0.00004, 0.00035)
        
        drift = regime * 0.000003 * sess_mult
        price += drift + np.random.normal(0, vol_state * sess_mult)
        prices.append(np.clip(price, 1.020, 1.130))

    df = pd.DataFrame({'time': idx, 'close': prices}).set_index('time')
    df['open'] = df['close'].shift(1).fillna(df['close'])
    df['high'] = df[['open', 'close']].max(axis=1) + 0.0001
    df['low'] = df[['open', 'close']].min(axis=1) - 0.0001
    return df

def ema(series, period): return series.ewm(span=period, adjust=False).mean()

def rsi(closes, period=7):
    delta = closes.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta).clip(lower=0).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

# ═══════════════════════════════════════════════════
# 3. STRATEGY PARAMETERS (OPTIMIZED)
# ═══════════════════════════════════════════════════
PIP = 0.0001
SL_PIPS, TP_PIPS = 10, 20  # Recommended Fix 2
MIN_ATR_PIPS = 4.5         # Slight tightening for quality
RSI_BUY_MAX = 62           # Fix 7: Loosened for better trend entry
RSI_SELL_MIN = 38          # Fix 7: Loosened

# ═══════════════════════════════════════════════════
# 4. SIGNAL ENGINE
# ═══════════════════════════════════════════════════

def check_signal(ts, m5_df, h1_df, h4_df, m15_df, m30_df, l2_state):
    # L0: Macro Trend
    h4 = h4_df[:ts].tail(1)
    if h4.empty: return 0, "NONE", None, l2_state
    direction = "BUY" if h4['close'].iloc > h4['ema50'].iloc else "SELL"

    # VETO: ATR
    h1 = h1_df[:ts].tail(1)
    if h1.empty or (h1['atr14'].iloc / PIP) < MIN_ATR_PIPS:
        return 0, "NONE", None, l2_state

    # L1: EMA Stack (Relaxed as per Fix 1)
    if direction == "BUY" and not (h1['close'].iloc > h1['ema21'].iloc):
        return 1, "NONE", None, l2_state
    if direction == "SELL" and not (h1['close'].iloc < h1['ema21'].iloc):
        return 1, "NONE", None, l2_state

    # L2/L3 State Machine
    m5 = m5_df[:ts].tail(1)
    rsi_val = m5['rsi7'].iloc
    
    if direction == "BUY" and rsi_val < RSI_BUY_MAX:
        return 4, "BUY", "RSI Optimized Entry", None
    elif direction == "SELL" and rsi_val > RSI_SELL_MIN:
        return 4, "SELL", "RSI Optimized Entry", None

    return 0, "NONE", None, l2_state

# ═══════════════════════════════════════════════════
# 5. EXECUTION LOOP
# ═══════════════════════════════════════════════════

m5_df = generate_eurusd_m5()
h1_df = m5_df.resample('1h').agg({'open':'first','high':'max','low':'min','close':'last'})
h4_df = m5_df.resample('4h').agg({'close':'last'})

h1_df['ema21'] = ema(h1_df['close'], 21)
h1_df['atr14'] = (h1_df['high'] - h1_df['low']).rolling(14).mean()
h4_df['ema50'] = ema(h4_df['close'], 50)
m5_df['rsi7'] = rsi(m5_df['close'], 7)

trades = []
open_trade = None

print("Running deep-fix backtest...")

for ts, bar in m5_df.iterrows():
    if not ((7 <= ts.hour < 11) or (12 <= ts.hour < 16)): continue

    if open_trade:
        # Simple TP/SL logic
        pips = (bar['close'] - open_trade['entry']) / PIP if open_trade['dir'] == "BUY" else (open_trade['entry'] - bar['close']) / PIP
        if pips >= TP_PIPS or pips <= -SL_PIPS:
            trades.append({'time': ts, 'pips': pips, 'result': 'WIN' if pips > 0 else 'LOSS'})
            open_trade = None
        continue

    score, dirn, msg, _ = check_signal(ts, m5_df, h1_df, h4_df, None, None, None)
    if score == 4:
        open_trade = {'entry': bar['close'], 'dir': dirn}

# ═══════════════════════════════════════════════════
# 6. SAVE RESULTS (THE FINAL DIRECTORY GUARD)
# ═══════════════════════════════════════════════════
df_results = pd.DataFrame(trades)
final_path = os.path.join(OUTPUT_DIR, "backtest_results_fixed.csv")

try:
    df_results.to_csv(final_path, index=False)
    print(f"\n✅ SUCCESS: Data saved to {final_path}")
    print(f"Total Trades: {len(df_results)} | Win Rate: {len(df_results[df_results['pips']>0])/len(df_results)*100:.1f}%")
except Exception as e:
    print(f"Fallback Save: {e}")
    df_results.to_csv("emergency_results.csv")
