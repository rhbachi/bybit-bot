import streamlit as st

# MUST BE THE FIRST ST COMMAND
st.set_page_config(
    page_title="Bybit Bots Dashboard Pro",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

import pandas as pd
import requests
import time
import os
import sys
import plotly.express as px
import plotly.graph_objects as go

# Initialization
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "run_scan" not in st.session_state:
    st.session_state.run_scan = False

BOT_MULTISYMBOL_URL = os.environ.get("BOT_MULTISYMBOL_URL", "http://127.0.0.1:5001")
BOT_ZONE2_URL = os.environ.get("BOT_ZONE2_URL", "http://127.0.0.1:5002")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ==========================================================
# CSS GLOBAL — RESPONSIVE + DARK THEME
# ==========================================================
st.markdown("""
<style>
    /* ---- Base ---- */
    html, body, [data-testid="stAppViewContainer"] {
        background-color: #0F0F17;
        color: #E0E0E0;
    }
    [data-testid="stSidebar"] {
        background-color: #14141F;
        border-right: 1px solid #2A2A3D;
    }

    /* ---- Metric cards ---- */
    .metric-row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
    .metric-card {
        flex: 1 1 120px;
        background: #1A1A2E;
        border: 1px solid #2A2A3D;
        border-radius: 12px;
        padding: 14px 16px;
        text-align: center;
        min-width: 110px;
    }
    .metric-label { font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: .06em; margin-bottom: 4px; }
    .metric-value { font-size: 22px; font-weight: 700; color: #00FF88; line-height: 1.2; }
    .metric-value.neg { color: #FF4B4B; }
    .metric-value.neutral { color: #CCCCCC; }

    /* ---- Section titles ---- */
    .section-title {
        font-size: 15px; font-weight: 600; color: #00CC77;
        border-left: 3px solid #00CC77; padding-left: 8px;
        margin: 16px 0 8px;
    }

    /* ---- Status badge ---- */
    .badge {
        display: inline-block; padding: 3px 10px;
        border-radius: 20px; font-size: 12px; font-weight: 600;
    }
    .badge-green  { background: #0D3D2A; color: #00FF88; border: 1px solid #00CC77; }
    .badge-red    { background: #3D0D0D; color: #FF4B4B; border: 1px solid #CC0000; }
    .badge-yellow { background: #3D300D; color: #FFD700; border: 1px solid #CCA800; }
    .badge-blue   { background: #0D1F3D; color: #4DB8FF; border: 1px solid #0070CC; }

    /* ---- Signal row ---- */
    .signal-row {
        display: flex; align-items: center; gap: 8px;
        padding: 6px 10px; border-radius: 8px;
        background: #1A1A2E; margin-bottom: 4px; font-size: 13px;
    }
    .sig-long  { color: #00FF88; font-weight: 700; }
    .sig-short { color: #FF4B4B; font-weight: 700; }
    .sig-none  { color: #666; }

    /* ---- Dataframe overrides ---- */
    [data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }
    [data-testid="stDataFrame"] th { background: #1A1A2E !important; color: #888 !important; font-size: 12px; }
    [data-testid="stDataFrame"] td { font-size: 13px; }

    /* ---- Login ---- */
    .login-title { text-align: center; color: #00FF88; font-size: 32px; font-weight: bold; margin-bottom: 6px; }
    .login-sub   { text-align: center; color: #888; font-size: 14px; margin-bottom: 20px; }

    /* ---- Responsive: stack columns on narrow screens ---- */
    @media (max-width: 768px) {
        .metric-card { flex: 1 1 100%; }
        [data-testid="column"] { min-width: 100% !important; width: 100% !important; }
        .section-title { font-size: 14px; }
        .metric-value { font-size: 18px; }
    }

    /* ---- Divider ---- */
    hr.light { border-color: #2A2A3D; margin: 12px 0; }
</style>
""", unsafe_allow_html=True)

# ==========================================================
# AUTHENTICATION
# ==========================================================
ADMIN_USERNAME = os.environ.get("DASHBOARD_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "bybit2024")

def check_auth():
    return st.session_state.authenticated

def login_page():
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

if not check_auth():
    login_page()
    st.stop()

# ==========================================================
# SIDEBAR
# ==========================================================
st.sidebar.title("🤖 Bots Dashboard V2")
page = st.sidebar.radio(
    "Navigation",
    ["📊 Live Monitoring", "📡 Market Scanner", "🧪 Visual Backtester"]
)
st.sidebar.markdown("---")

if page == "📊 Live Monitoring":
    refresh_rate = st.sidebar.slider("Auto-Refresh (sec)", 5, 60, 10)

st.sidebar.markdown("---")
st.sidebar.caption(f"👤 Connecté : **{ADMIN_USERNAME}**")
if st.sidebar.button("🔒 Se Déconnecter"):
    st.session_state.authenticated = False
    st.rerun()


# ==========================================================
# HELPERS
# ==========================================================
def api_get(url, path, timeout=3):
    """Safe API GET, returns None on failure."""
    try:
        r = requests.get(f"{url}{path}", timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None

def pnl_html(value):
    cls = "neg" if value < 0 else "metric-value"
    sign = "+" if value >= 0 else ""
    return f'<span class="metric-value {cls}">{sign}{value:.2f} USDT</span>'

def fmt_pnl(val):
    try:
        v = float(val)
        return f"+{v:.2f}" if v >= 0 else f"{v:.2f}"
    except Exception:
        return str(val)

def color_result(val):
    if str(val).upper() in ("WIN", "LONG"):
        return "color: #00FF88"
    if str(val).upper() in ("LOSS", "SHORT"):
        return "color: #FF4B4B"
    return ""

def calculate_stats(trades):
    if not trades:
        return None
    df = pd.DataFrame(trades)
    if df.empty:
        return None
    
    stats = {}
    if 'symbol' in df.columns and 'pnl_usdt' in df.columns:
        # Convert pnl_usdt to numeric
        df['pnl_usdt'] = pd.to_numeric(df['pnl_usdt'], errors='coerce').fillna(0)
        
        # Group by symbol
        for symbol, group in df.groupby('symbol'):
            wins = len(group[group['pnl_usdt'] > 0])
            total = len(group)
            wr = (wins / total * 100) if total > 0 else 0
            profit = group['pnl_usdt'].sum()
            stats[symbol] = {'win_rate': wr, 'profit': profit, 'trades': total}
            
    return stats

def get_global_stats(trades):
    if not trades:
        return 0, "N/A"
    df = pd.DataFrame(trades)
    if df.empty:
        return 0, "N/A"
    
    # Global Win Rate
    if 'pnl_usdt' in df.columns:
        df['pnl_usdt'] = pd.to_numeric(df['pnl_usdt'], errors='coerce').fillna(0)
        wins = len(df[df['pnl_usdt'] > 0])
        wr = (wins / len(df) * 100) if len(df) > 0 else 0
    else:
        wr = 0
        
    # Best Symbol
    stats = calculate_stats(trades)
    best_sym = "N/A"
    if stats:
        best_sym = max(stats, key=lambda x: stats[x]['profit'])
        
    return wr, best_sym


# ==========================================================
# PAGE 1: LIVE MONITORING
# ==========================================================
if page == "📊 Live Monitoring":
    st.title("📊 Live Bots Monitoring")

    tab1, tab2 = st.tabs(["🌐 Multi-Symbol Bot", "🎯 Zone 2 AI Bot (FVG+Fib)"])

    # ── Tab 1: Multi-Symbol Bot ──────────────────────────────
    with tab1:
        trades_ms = api_get(BOT_MULTISYMBOL_URL, "/api/trades")
        data = api_get(BOT_MULTISYMBOL_URL, "/api/status")

        if data:
            mode_badge = '<span class="badge badge-yellow">📝 PAPER</span>' if data.get('paper_mode') else '<span class="badge badge-green">💰 LIVE</span>'
            st.markdown(f"**Statut** : <span class='badge badge-green'>● En ligne</span> &nbsp; {mode_badge}", unsafe_allow_html=True)

            pnl = data.get('daily_pnl', 0)
            pnl_cls = "neg" if pnl < 0 else ""
            sign = "+" if pnl >= 0 else ""

            # Calculate WR and Best Symbol from already fetched trades
            wr_ms, best_ms = get_global_stats(trades_ms)

            st.markdown(f"""
            <div class="metric-row">
              <div class="metric-card">
                <div class="metric-label">Daily PnL</div>
                <div class="metric-value {pnl_cls}">{sign}{pnl:.2f} USDT</div>
              </div>
              <div class="metric-card">
                <div class="metric-label">Win Rate</div>
                <div class="metric-value neutral">{wr_ms:.1f}%</div>
              </div>
              <div class="metric-card">
                <div class="metric-label">Best Symbol</div>
                <div class="metric-value neutral" style="font-size: 16px;">{best_ms}</div>
              </div>
              <div class="metric-card">
                <div class="metric-label">Positions</div>
                <div class="metric-value neutral">{data.get('active_count', 0)}</div>
              </div>
              <div class="metric-card">
                <div class="metric-label">Total Trades</div>
                <div class="metric-value neutral">{data.get('total_trades', 0)}</div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown('<div class="section-title">🧠 Auto-Tuner & Config</div>', unsafe_allow_html=True)
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Stratégie", data.get('active_strategy', 'v6'))
            c2.metric("Threshold", data.get('threshold', 3))
            c3.metric("SL Multi", f"{data.get('sl_multi', 1.5)}x")
            c4.metric("TP Multi", f"{data.get('tp_multi', 3.0)}x")
            c5.metric("Capital", f"{data.get('capital', 0)} USDT")
        else:
            st.error(f"❌ Multi-Symbol API hors ligne ({BOT_MULTISYMBOL_URL})")

        # Open Positions Multi-Symbol
        positions_ms = api_get(BOT_MULTISYMBOL_URL, "/api/positions")
        if positions_ms:
            st.markdown('<div class="section-title">📍 Positions Ouvertes</div>', unsafe_allow_html=True)
            df_pos_ms = pd.DataFrame(positions_ms)
            pos_cols = [c for c in ['symbol', 'side', 'entry_price', 'qty', 'timestamp'] if c in df_pos_ms.columns]
            if pos_cols:
                st.dataframe(df_pos_ms[pos_cols], use_container_width=True, hide_index=True)
        elif data:
            st.info("Aucune position ouverte.")

        # Recent Signals Multi-Symbol
        signals_ms = api_get(BOT_MULTISYMBOL_URL, "/api/signals")
        if signals_ms:
            st.markdown('<div class="section-title">📡 Signaux Récents</div>', unsafe_allow_html=True)
            df_sig_ms = pd.DataFrame(signals_ms)
            sig_cols = [c for c in ['timestamp', 'symbol', 'signal', 'price', 'strength', 'executed', 'reason'] if c in df_sig_ms.columns]
            if sig_cols:
                st.dataframe(df_sig_ms[sig_cols].tail(10), use_container_width=True, hide_index=True)

        # Charts for Multi-Symbol
        if trades_ms:
            st.markdown('<div class="section-title">📊 Performance par Symbole</div>', unsafe_allow_html=True)
            ms_stats = calculate_stats(trades_ms)
            if ms_stats:
                df_stats_ms = pd.DataFrame.from_dict(ms_stats, orient='index').reset_index().rename(columns={'index': 'symbol'})
                
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    fig_wr = px.bar(df_stats_ms, x='symbol', y='win_rate', title="Winning Rate % per Symbol",
                                   color='win_rate', color_continuous_scale='Viridis')
                    fig_wr.update_layout(template="plotly_dark", height=300, margin=dict(l=0, r=0, t=30, b=0))
                    st.plotly_chart(fig_wr, use_container_width=True)
                
                with col_c2:
                    fig_profit = px.bar(df_stats_ms, x='symbol', y='profit', title="Total Profit USDT per Symbol",
                                       color='profit', color_continuous_scale='RdYlGn')
                    fig_profit.update_layout(template="plotly_dark", height=300, margin=dict(l=0, r=0, t=30, b=0))
                    st.plotly_chart(fig_profit, use_container_width=True)

        # Recent trades
        if trades_ms:
            st.markdown('<div class="section-title">📋 Trades Récents</div>', unsafe_allow_html=True)
            df_t = pd.DataFrame(trades_ms)
            cols = [c for c in ['timestamp', 'symbol', 'side', 'result', 'pnl_usdt', 'pnl_percent', 'exit_reason'] if c in df_t.columns]
            if cols:
                df_show = df_t[cols].copy()
                if 'pnl_usdt' in df_show.columns:
                    df_show['pnl_usdt'] = df_show['pnl_usdt'].apply(fmt_pnl)
                if 'pnl_percent' in df_show.columns:
                    df_show['pnl_percent'] = df_show['pnl_percent'].apply(lambda x: fmt_pnl(float(x)) + "%" if x else "–")
                st.dataframe(df_show.tail(20), use_container_width=True, hide_index=True)
        elif data:
            st.info("Aucun trade enregistré.")

    # ── Tab 2: Zone2 AI Bot ──────────────────────────────────
    with tab2:
        trades_z2 = api_get(BOT_ZONE2_URL, "/api/trades")
        data2 = api_get(BOT_ZONE2_URL, "/api/status")

        if data2:
            mode_badge = '<span class="badge badge-yellow">📝 PAPER</span>' if data2.get('paper_mode') else '<span class="badge badge-green">💰 LIVE</span>'
            st.markdown(f"**Statut** : <span class='badge badge-green'>● En ligne</span> &nbsp; {mode_badge}", unsafe_allow_html=True)

            pnl2 = data2.get('daily_pnl', 0)
            pnl_cls2 = "neg" if pnl2 < 0 else ""
            sign2 = "+" if pnl2 >= 0 else ""
            cons_loss = data2.get('consecutive_losses', 0)
            cons_cls = "neg" if cons_loss >= 2 else "neutral"

            # Calculate WR and Best Symbol from already fetched trades
            wr_z2, best_z2 = get_global_stats(trades_z2)

            st.markdown(f"""
            <div class="metric-row">
              <div class="metric-card">
                <div class="metric-label">Daily PnL</div>
                <div class="metric-value {pnl_cls2}">{sign2}{pnl2:.2f} USDT</div>
              </div>
              <div class="metric-card">
                <div class="metric-label">Win Rate</div>
                <div class="metric-value neutral">{wr_z2:.1f}%</div>
              </div>
              <div class="metric-card">
                <div class="metric-label">Best Symbol</div>
                <div class="metric-value neutral" style="font-size: 16px;">{best_z2}</div>
              </div>
              <div class="metric-card">
                <div class="metric-label">Positions</div>
                <div class="metric-value neutral">{data2.get('active_count', 0)}</div>
              </div>
              <div class="metric-card">
                <div class="metric-label">Pertes conséc.</div>
                <div class="metric-value {cons_cls}">{cons_loss}</div>
              </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.error(f"❌ Zone2 API hors ligne ({BOT_ZONE2_URL})")

        # Positions ouvertes
        positions = api_get(BOT_ZONE2_URL, "/api/positions")
        if positions:
            st.markdown('<div class="section-title">📍 Positions Ouvertes</div>', unsafe_allow_html=True)
            df_pos = pd.DataFrame(positions)
            pos_cols = [c for c in ['symbol', 'side', 'entry_price', 'last_price', 'sl_price', 'tp_price', 'qty', 'trailing_activated'] if c in df_pos.columns]
            if pos_cols:
                st.dataframe(df_pos[pos_cols], use_container_width=True, hide_index=True)
        elif data2:
            st.info("Aucune position ouverte.")

        # Signaux récents
        signals = api_get(BOT_ZONE2_URL, "/api/signals")
        if signals:
            st.markdown('<div class="section-title">📡 Signaux FVG+Fibonacci Récents</div>', unsafe_allow_html=True)
            df_sig = pd.DataFrame(signals)
            sig_cols = [c for c in ['timestamp', 'bot', 'signal', 'price', 'strength', 'executed', 'reason'] if c in df_sig.columns]
            if sig_cols:
                df_sig_show = df_sig[sig_cols].tail(20)
                st.dataframe(df_sig_show, use_container_width=True, hide_index=True)

        # Trades récents
        if trades_z2:
            st.markdown('<div class="section-title">📋 Trades Récents</div>', unsafe_allow_html=True)
            df_t2 = pd.DataFrame(trades_z2)
            t2_cols = [c for c in ['timestamp', 'symbol', 'side', 'entry_price', 'exit_price', 'pnl_usdt', 'pnl_percent', 'result', 'exit_reason'] if c in df_t2.columns]
            if t2_cols:
                df_t2_show = df_t2[t2_cols].copy()
                if 'pnl_usdt' in df_t2_show.columns:
                    df_t2_show['pnl_usdt'] = df_t2_show['pnl_usdt'].apply(fmt_pnl)
                if 'pnl_percent' in df_t2_show.columns:
                    df_t2_show['pnl_percent'] = df_t2_show['pnl_percent'].apply(lambda x: fmt_pnl(float(x)) + "%" if x else "–")
                st.dataframe(df_t2_show.tail(20), use_container_width=True, hide_index=True)

            # Charts for Zone2
            st.markdown('<div class="section-title">📊 Performance par Symbole</div>', unsafe_allow_html=True)
            z2_stats = calculate_stats(trades_z2)
            if z2_stats:
                df_stats_z2 = pd.DataFrame.from_dict(z2_stats, orient='index').reset_index().rename(columns={'index': 'symbol'})
                
                col_z1, col_z2 = st.columns(2)
                with col_z1:
                    fig_wr2 = px.bar(df_stats_z2, x='symbol', y='win_rate', title="Winning Rate % per Symbol",
                                    color='win_rate', color_continuous_scale='Viridis')
                    fig_wr2.update_layout(template="plotly_dark", height=300, margin=dict(l=0, r=0, t=30, b=0))
                    st.plotly_chart(fig_wr2, use_container_width=True)
                
                with col_z2:
                    fig_profit2 = px.bar(df_stats_z2, x='symbol', y='profit', title="Total Profit USDT per Symbol",
                                        color='profit', color_continuous_scale='RdYlGn')
                    fig_profit2.update_layout(template="plotly_dark", height=300, margin=dict(l=0, r=0, t=30, b=0))
                    st.plotly_chart(fig_profit2, use_container_width=True)
        elif data2:
            st.info("Aucun trade enregistré.")

    # Auto-refresh logic (Improved)
    if refresh_rate > 0:
        time.sleep(refresh_rate)
        st.rerun()


# ==========================================================
# PAGE 2: MARKET SCANNER
# ==========================================================
elif page == "📡 Market Scanner":
    st.title("📡 Live Market Scanner")
    st.markdown("Scanne tous les symboles configurés avec la stratégie V7 Robust.")

    col_l, col_r = st.columns([1, 3])
    with col_l:
        timeframe = st.selectbox("Timeframe", ["1m", "5m", "15m", "30m", "1h"])
        run = st.button("🚀 Lancer le scan", type="primary", use_container_width=True)
        if run:
            st.session_state.run_scan = True

    with col_r:
        if st.session_state.get('run_scan'):
            try:
                from strategy_v7_robust import apply_indicators, check_signal
                from config import SYMBOLS, exchange
            except ImportError as e:
                st.error(f"Import impossible : {e}")
                st.stop()

            progress = st.progress(0)
            status = st.empty()
            results = []

            for i, symbol in enumerate(SYMBOLS):
                status.text(f"Scan {symbol} ({i+1}/{len(SYMBOLS)})...")
                try:
                    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=250)
                    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
                    df = apply_indicators(df)
                    signal, score, atr = check_signal(df)
                    price = df['close'].iloc[-1]
                    rsi = df['rsi'].iloc[-1] if 'rsi' in df.columns else 0
                    results.append({
                        "Symbole": symbol,
                        "Signal": "🟢 BUY" if signal == "long" else ("🔴 SELL" if signal == "short" else "⬜ Neutre"),
                        "Score": f"{score}/3" if signal else "–",
                        "Prix": f"{price:.4f}",
                        "RSI": f"{rsi:.1f}",
                    })
                except Exception:
                    pass
                progress.progress((i + 1) / len(SYMBOLS))
                time.sleep(0.1)

            status.text("Scan terminé !")
            df_results = pd.DataFrame(results)

            active = df_results[df_results['Signal'] != "⬜ Neutre"]
            st.success(f"{len(active)} setup(s) potentiel(s) trouvé(s) sur {len(results)} symboles.")
            st.dataframe(df_results, use_container_width=True, hide_index=True)
            st.session_state.run_scan = False


# ==========================================================
# PAGE 3: VISUAL BACKTESTER
# ==========================================================
elif page == "🧪 Visual Backtester":
    st.title("🧪 Visual Strategy Backtester")

    with st.form("backtest_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            symbol = st.text_input("Symbole", value="BTC/USDT")
        with c2:
            tf = st.selectbox("Timeframe", ["1m", "5m", "15m", "30m", "1h", "4h"], index=1)
        with c3:
            strat = st.selectbox("Stratégie", ["V6 Aggressive", "V7 Robust"])

        p1, p2, p3 = st.columns(3)
        with p1:
            sl_m = st.number_input("SL ATR Multiplier", value=1.5, step=0.1)
        with p2:
            tp_m = st.number_input("TP ATR Multiplier", value=3.0, step=0.1)
        with p3:
            score_th = st.number_input("Score Threshold", value=3, min_value=1, max_value=5)

        submitted = st.form_submit_button("▶️ Lancer la simulation", type="primary", use_container_width=True)

    if submitted:
        try:
            from config import exchange
            from auto_tuner import AutoTuner
            import plotly.graph_objects as go

            with st.spinner(f"Récupération des données {symbol} ({tf})..."):
                tuner = AutoTuner(exchange, None)
                df = tuner.fetch_historical_data(symbol, tf, hours=72)

            if df is None or df.empty:
                st.error("Impossible de récupérer les données.")
            else:
                strat_name = 'v6_aggressive' if strat == "V6 Aggressive" else 'v7_robust'
                p = {'sl_multi': sl_m, 'tp_multi': tp_m, 'threshold': score_th}

                apply_ind, check_sig = tuner.strategies[strat_name]
                df = apply_ind(df)
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

                buy_x, buy_y, sell_x, sell_y = [], [], [], []
                capital = 1000.0
                equity_curve = [capital]
                time_axis = [df['timestamp'].iloc[0]]

                start_idx = 200 if strat_name == 'v7_robust' else 25

                with st.spinner("Simulation en cours..."):
                    for i in range(start_idx, len(df) - 1):
                        slice_df = df.iloc[:i+1]
                        signal, score, atr = check_sig(slice_df)
                        if signal and score >= p['threshold']:
                            outcome = tuner.simulate_trade(df, i, signal, p)
                            if outcome != 0:
                                trade_pnl = outcome * atr * (capital * 0.02 / (atr * p['sl_multi']))
                                capital += trade_pnl
                                if signal == 'long':
                                    buy_x.append(df['timestamp'].iloc[i])
                                    buy_y.append(df['close'].iloc[i])
                                else:
                                    sell_x.append(df['timestamp'].iloc[i])
                                    sell_y.append(df['close'].iloc[i])
                                equity_curve.append(capital)
                                time_axis.append(df['timestamp'].iloc[i])

                # Candlestick chart
                st.subheader("📊 Price Action & Signaux")
                fig = go.Figure(data=[go.Candlestick(
                    x=df['timestamp'], open=df['open'], high=df['high'],
                    low=df['low'], close=df['close'], name='Prix'
                )])
                if buy_x:
                    fig.add_trace(go.Scatter(x=buy_x, y=buy_y, mode='markers',
                        marker=dict(symbol='triangle-up', size=12, color='#00FF88'), name='BUY'))
                if sell_x:
                    fig.add_trace(go.Scatter(x=sell_x, y=sell_y, mode='markers',
                        marker=dict(symbol='triangle-down', size=12, color='#FF4B4B'), name='SELL'))

                fig.update_layout(
                    template="plotly_dark", height=500,
                    margin=dict(l=0, r=0, t=30, b=0),
                    xaxis_rangeslider_visible=False,
                    paper_bgcolor='#0F0F17', plot_bgcolor='#0F0F17'
                )
                st.plotly_chart(fig, use_container_width=True)

                # Equity curve
                st.subheader("💰 Courbe d'Équité (départ $1000, risque 2%)")
                roi = ((capital / 1000) - 1) * 100
                line_color = '#00FF88' if roi >= 0 else '#FF4B4B'
                fig_eq = go.Figure(data=[go.Scatter(
                    x=time_axis, y=equity_curve, mode='lines',
                    line=dict(color=line_color, width=2), fill='tozeroy',
                    fillcolor='rgba(0,255,136,0.07)' if roi >= 0 else 'rgba(255,75,75,0.07)'
                )])
                fig_eq.update_layout(
                    template="plotly_dark", height=280,
                    margin=dict(l=0, r=0, t=10, b=0),
                    paper_bgcolor='#0F0F17', plot_bgcolor='#0F0F17'
                )
                st.plotly_chart(fig_eq, use_container_width=True)

                roi_sign = "+" if roi >= 0 else ""
                if roi >= 0:
                    st.success(f"Capital final : **${capital:.2f}** ({roi_sign}{roi:.2f}%)")
                else:
                    st.error(f"Capital final : **${capital:.2f}** ({roi_sign}{roi:.2f}%)")

        except Exception as e:
            st.error(f"Erreur simulation : {e}")
