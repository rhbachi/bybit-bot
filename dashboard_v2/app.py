import streamlit as st
import pandas as pd
import requests
import time
import os
import sys

# Ajouter le dossier parent au PATH pour importer config, etc.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    import config
except ImportError:
    pass

# ==========================================================
# Configurable Bot API URLs via environment variables
# Set these in Coolify to the internal service hostnames
# e.g. BOT_MULTISYMBOL_URL=http://bybit-bot-multisymbol:5001
# ==========================================================
BOT_MULTISYMBOL_URL = os.environ.get("BOT_MULTISYMBOL_URL", "http://127.0.0.1:5001")
BOT_ZONE2_URL = os.environ.get("BOT_ZONE2_URL", "http://127.0.0.1:5002")

st.set_page_config(
    page_title="Bybit Bots Dashboard Pro",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==========================================================
# AUTHENTICATION
# Credentials are set via environment variables in Coolify:
# DASHBOARD_USERNAME and DASHBOARD_PASSWORD
# ==========================================================
ADMIN_USERNAME = os.environ.get("DASHBOARD_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "bybit2024")

def check_auth():
    """Returns True if user is authenticated."""
    return st.session_state.get("authenticated", False)

def login_page():
    """Shows the login form and handles authentication."""
    st.markdown("""
    <style>
        .login-container { max-width: 400px; margin: 100px auto; padding: 30px; 
            background: #1E1E2E; border-radius: 16px; border: 1px solid #333; }
        .login-title { text-align: center; color: #00FF88; font-size: 32px; font-weight: bold; margin-bottom: 8px;}
        .login-sub { text-align: center; color: #888; font-size: 14px; margin-bottom: 24px;}
    </style>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown('<div class="login-title">🤖 Bybit Dashboard</div>', unsafe_allow_html=True)
        st.markdown('<div class="login-sub">Accès Administrateur</div>', unsafe_allow_html=True)
        st.markdown("---")
        
        username = st.text_input("👤 Identifiant", placeholder="admin")
        password = st.text_input("🔑 Mot de passe", type="password", placeholder="••••••••")
        
        if st.button("🔓 Se Connecter", type="primary", use_container_width=True):
            if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
                st.session_state.authenticated = True
                st.success("✅ Connexion réussie !")
                st.rerun()
            else:
                st.error("❌ Identifiants incorrects.")

# Gate the entire app behind login
if not check_auth():
    login_page()
    st.stop()

# ==========================================================
# MAIN APP (only visible when authenticated)
# ==========================================================

# Custom CSS for a darker, more modern look
st.markdown("""
<style>
    .metric-card {
        background-color: #1E1E1E;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        text-align: center;
    }
    .metric-value {
        font-size: 24px;
        font-weight: bold;
        color: #00FF00;
    }
    .metric-label {
        color: #A0A0A0;
        font-size: 14px;
    }
</style>
""", unsafe_allow_html=True)

st.sidebar.title("🤖 Bots Dashboard V2")
page = st.sidebar.radio(
    "Navigation", 
    ["📊 Live Monitoring", "📡 Market Scanner", "🧪 Visual Backtester"]
)

st.sidebar.markdown("---")
st.sidebar.info("Dashboard Pro for Auto-Tuned Bybit Scalping Bots.")
st.sidebar.markdown("---")
st.sidebar.caption(f"👤 Connecté : **{ADMIN_USERNAME}**")
if st.sidebar.button("🔒 Se Déconnecter"):
    st.session_state.authenticated = False
    st.rerun()


# ==========================================
# PAGE 1: LIVE MONITORING
# ==========================================
if page == "📊 Live Monitoring":
    st.title("📊 Live Bots Monitoring")
    
    # Refresh mechanism
    refresh_rate = st.sidebar.slider("Auto-Refresh (seconds)", 5, 60, 10)
    
    # Create two columns for two bots
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🌐 Multi-Symbol Bot")
        try:
            res_status = requests.get(f"{BOT_MULTISYMBOL_URL}/api/status", timeout=2)
            if res_status.status_code == 200:
                data = res_status.json()
                
                m1, m2, m3 = st.columns(3)
                m1.metric("Daily PnL", f"{data.get('daily_pnl', 0):.2f} USDT")
                m2.metric("Active Trades", data.get('active_count', 0))
                m3.metric("Total Trades", data.get('total_trades', 0))
                
                st.markdown("### 🧠 Auto-Tuner Status")
                st.info(f"**Strategy**: {data.get('active_strategy', 'v6_aggressive')}\n\n"
                        f"**Threshold**: {data.get('threshold', 3)}\n\n"
                        f"**SL Multi**: {data.get('sl_multi', 1.5)}x | **TP Multi**: {data.get('tp_multi', 3.0)}x")
                
                # Fetch recent trades
                res_trades = requests.get(f"{BOT_MULTISYMBOL_URL}/api/trades", timeout=2)
                if res_trades.status_code == 200:
                    trades = res_trades.json()
                    if trades:
                        st.markdown("#### Recent Trades")
                        df_trades = pd.DataFrame(trades)
                        # Format dataframe
                        st.dataframe(df_trades[['timestamp', 'symbol', 'result', 'pnl_usdt', 'exit_reason']], use_container_width=True)
            else:
                st.warning("Bot is offline or starting.")
        except Exception as e:
            st.error(f"Cannot connect to Multi-Symbol API ({BOT_MULTISYMBOL_URL}). Is it running?")
            
    with col2:
        st.subheader("🎯 Zone 2 AI Bot")
        try:
            res_status2 = requests.get(f"{BOT_ZONE2_URL}/api/status", timeout=2)
            if res_status2.status_code == 200:
                data2 = res_status2.json()
                
                m1, m2, m3 = st.columns(3)
                m1.metric("Daily PnL", f"{data2.get('daily_pnl', 0):.2f} USDT")
                m2.metric("Active Trades", data2.get('active_count', 0))
                
                res_trades2 = requests.get(f"{BOT_ZONE2_URL}/api/trades", timeout=2)
                if res_trades2.status_code == 200:
                    trades2 = res_trades2.json()
                    if trades2:
                        st.markdown("#### Recent Activity")
                        df_trades2 = pd.DataFrame(trades2)
                        st.dataframe(df_trades2[['timestamp', 'symbol', 'pnl_usdt', 'result']], use_container_width=True)
            else:
                st.warning("Bot is offline or starting.")
        except Exception as e:
            st.error(f"Cannot connect to Zone 2 API ({BOT_ZONE2_URL}). Is it running?")
            
    time.sleep(refresh_rate)
    st.rerun()

# ==========================================
# PAGE 2: MARKET SCANNER
# ==========================================
elif page == "📡 Market Scanner":
    st.title("📡 Live Market Scanner")
    st.markdown("Scans all configured symbols using the robust V7 strategy.")
    
    col1, col2 = st.columns([1, 3])
    with col1:
        timeframe = st.selectbox("Timeframe", ["1m", "5m", "15m", "30m", "1h"])
        if st.button("🚀 Run Scan", type="primary"):
            st.session_state.run_scan = True
    
    with col2:
        if st.session_state.get('run_scan'):
            st.info(f"Scanning symbols from config.yaml on {timeframe}...")
            
            from strategy_v7_robust import apply_indicators, check_signal
            try:
                from config import SYMBOLS, exchange
            except ImportError:
                st.error("Could not import config. Make sure you are in the right directory.")
                st.stop()
                
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            results = []
            
            for i, symbol in enumerate(SYMBOLS):
                status_text.text(f"Scanning {symbol} ({i+1}/{len(SYMBOLS)})...")
                try:
                    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=250)
                    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
                    df = apply_indicators(df)
                    signal, score, atr = check_signal(df)
                    
                    price = df['close'].iloc[-1]
                    
                    if signal:
                        results.append({
                            "Symbol": symbol,
                            "Signal": "🟢 BUY" if signal == "long" else "🔴 SELL",
                            "Score": f"{score}/3",
                            "Price": f"{price:.4f}",
                            "RSI": f"{df['rsi'].iloc[-1]:.1f}"
                        })
                except Exception as e:
                    pass # Ignore fetch errors for smooth scanning
                
                progress_bar.progress((i + 1) / len(SYMBOLS))
                time.sleep(0.1) # Be gentle with the API
                
            status_text.text("Scan complete!")
            
            if results:
                st.success(f"Found {len(results)} potential setups!")
                st.dataframe(pd.DataFrame(results), use_container_width=True)
            else:
                st.warning("No high-probability setups found right now.")
                
            st.session_state.run_scan = False

# ==========================================
# PAGE 3: VISUAL BACKTESTER
# ==========================================
elif page == "🧪 Visual Backtester":
    st.title("🧪 Visual Strategy Backtester")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        symbol = st.text_input("Symbol", value="BTC/USDT")
    with col2:
        tf = st.selectbox("Timeframe", ["1m", "5m", "15m", "30m", "1h", "4h"], index=1)
    with col3:
        strat = st.selectbox("Strategy", ["V6 Aggressive", "V7 Robust"])
        
    p1, p2, p3 = st.columns(3)
    with p1:
        sl_m = st.number_input("SL ATR Multiplier", value=1.5, step=0.1)
    with p2:
        tp_m = st.number_input("TP ATR Multiplier", value=3.0, step=0.1)
    with p3:
        score_th = st.number_input("Score Threshold", value=3, min_value=1, max_value=5)
        
    if st.button("▶️ Run Simulation"):
        st.info(f"Fetching data for {symbol} on {tf}...")
        
        try:
            from config import exchange
            from auto_tuner import AutoTuner
            import plotly.graph_objects as go
            
            # Fetch Data
            tuner = AutoTuner(exchange, None)
            df = tuner.fetch_historical_data(symbol, tf, hours=72) # 3 days of data for visual test
            
            if df.empty:
                st.error("Could not fetch data.")
            else:
                strat_name = 'v6_aggressive' if strat == "V6 Aggressive" else 'v7_robust'
                p = {'sl_multi': sl_m, 'tp_multi': tp_m, 'threshold': score_th}
                
                apply_ind, check_sig = tuner.strategies[strat_name]
                df = apply_ind(df)
                
                # Convert timestamps from ms to readable datetime for Plotly
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                
                # Arrays to store markers for plotting
                buy_markers_x = []
                buy_markers_y = []
                sell_markers_x = []
                sell_markers_y = []
                
                start_idx = 200 if strat_name == 'v7_robust' else 25
                pnl_usdt = 0.0
                capital = 1000.0 # Hypothetical starting capital
                equity_curve = [capital]
                time_axis = [df['timestamp'].iloc[0]]
                
                with st.spinner("Simulating trades..."):
                    for i in range(start_idx, len(df) - 1):
                        slice_df = df.iloc[:i+1]
                        signal, score, atr = check_sig(slice_df)
                        current_date = df['timestamp'].iloc[i]
                        close_price = df['close'].iloc[i]
                        
                        if signal and score >= p['threshold']:
                            # Fake trade execution based on AutoTuner logic
                            outcome_atr_multi = tuner.simulate_trade(df, i, signal, p)
                            if outcome_atr_multi != 0:
                                trade_pnl = outcome_atr_multi * atr * (capital * 0.02 / (atr * p['sl_multi'])) # simplified risk
                                capital += trade_pnl
                                
                                if signal == 'long':
                                    buy_markers_x.append(current_date)
                                    buy_markers_y.append(close_price)
                                else:
                                    sell_markers_x.append(current_date)
                                    sell_markers_y.append(close_price)
                                
                                equity_curve.append(capital)
                                time_axis.append(current_date)
                
                # Plotly Chart
                st.subheader("📊 Price Action & Signals")
                fig = go.Figure(data=[go.Candlestick(x=df['timestamp'],
                                open=df['open'], high=df['high'],
                                low=df['low'], close=df['close'],
                                name='Price')])
                
                if buy_markers_x:
                    fig.add_trace(go.Scatter(x=buy_markers_x, y=buy_markers_y, mode='markers',
                                    marker=dict(symbol='triangle-up', size=12, color='green'), name='BUY'))
                if sell_markers_x:
                    fig.add_trace(go.Scatter(x=sell_markers_x, y=sell_markers_y, mode='markers',
                                    marker=dict(symbol='triangle-down', size=12, color='red'), name='SELL'))
                
                fig.update_layout(template="plotly_dark", height=600, margin=dict(l=0, r=0, t=30, b=0))
                # Disable rangeslider
                fig.update_layout(xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)
                
                # Equity Curve
                st.subheader("💰 Equity Curve ($1000 Start, 2% Risk)")
                fig_eq = go.Figure(data=[go.Scatter(x=time_axis, y=equity_curve, mode='lines', line=dict(color='#00FF00', width=2))])
                fig_eq.update_layout(template="plotly_dark", height=300, margin=dict(l=0, r=0, t=10, b=0))
                st.plotly_chart(fig_eq, use_container_width=True)
                
                st.success(f"Final Capital: ${capital:.2f} ({((capital/1000)-1)*100:.2f}%)")
                
        except Exception as e:
            st.error(f"Error during backtest: {e}")
