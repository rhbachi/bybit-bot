import sys
import os

# AUTO-LAUNCHER: Force Streamlit execution if ran via `python app.py`
# Use an environment flag to prevent infinite reload loops
if os.environ.get("STREAMLIT_AUTORUN") != "1":
    print(f"Auto-relaunching Dashboard V2 via Streamlit...", flush=True)
    os.environ["STREAMLIT_AUTORUN"] = "1"
    
    # Force the path to be dashboard_v2 to avoid launching the old dashboard by mistake
    target_app = "dashboard_v2/app.py" if os.path.exists("dashboard_v2/app.py") else sys.argv[0]
    
    # Coolify passes the expected port in the PORT env var. Default to 8501 if not set.
    port = os.environ.get("PORT", "8501")
    
    os.execv(sys.executable, ["python", "-m", "streamlit", "run", target_app, 
                              f"--server.port={port}", 
                              "--server.address=0.0.0.0", 
                              "--server.headless=true",
                              "--server.enableCORS=false",
                              "--server.enableXsrfProtection=false",
                              "--server.enableWebsocketCompression=false"])
import streamlit as st
import pandas as pd
import requests
import time
import os
import sys
import plotly.express as px
import plotly.graph_objects as go

# MUST BE THE FIRST ST COMMAND
st.set_page_config(
    page_title="Bybit Bots Dashboard Pro",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

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

def calculate_stats(trades):
    if not trades:
        return None
    df = pd.DataFrame(trades)
    if df.empty:
        return None
    
    stats = {}
    if 'symbol' in df.columns and 'pnl_usdt' in df.columns:
        df['pnl_usdt'] = pd.to_numeric(df['pnl_usdt'], errors='coerce').fillna(0)
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
    
    if 'pnl_usdt' in df.columns:
        df['pnl_usdt'] = pd.to_numeric(df['pnl_usdt'], errors='coerce').fillna(0)
        wins = len(df[df['pnl_usdt'] > 0])
        wr = (wins / len(df) * 100) if len(df) > 0 else 0
    else:
        wr = 0
        
    stats = calculate_stats(trades)
    best_sym = "N/A"
    if stats:
        best_sym = max(stats, key=lambda x: stats[x]['profit'])
    return wr, best_sym

# ==========================================================
# RENDER FUNCTIONS
# ==========================================================
def render_live_monitoring(refresh_rate):
    st.title("📊 Live Bots Monitoring")
    tab1, tab2 = st.tabs(["🌐 Multi-Symbol Bot", "🎯 Zone 2 AI Bot (FVG+Fib)"])

    with tab1:
        trades_ms = api_get(BOT_MULTISYMBOL_URL, "/api/trades")
        data = api_get(BOT_MULTISYMBOL_URL, "/api/status")

        if data:
            mode_badge = '<span class="badge badge-yellow">📝 PAPER</span>' if data.get('paper_mode') else '<span class="badge badge-green">💰 LIVE</span>'
            st.markdown(f"**Statut** : <span class='badge badge-green'>● En ligne</span> &nbsp; {mode_badge}", unsafe_allow_html=True)

            pnl = data.get('daily_pnl', 0)
            pnl_cls = "neg" if pnl < 0 else ""
            sign = "+" if pnl >= 0 else ""

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

        positions_ms = api_get(BOT_MULTISYMBOL_URL, "/api/positions")
        if positions_ms:
            st.markdown('<div class="section-title">📍 Positions Ouvertes</div>', unsafe_allow_html=True)
            df_pos_ms = pd.DataFrame(positions_ms)
            pos_cols = [c for c in ['symbol', 'side', 'entry_price', 'qty', 'timestamp'] if c in df_pos_ms.columns]
            if pos_cols:
                st.dataframe(df_pos_ms[pos_cols], use_container_width=True, hide_index=True)
        elif data:
            st.info("Aucune position ouverte.")

        signals_ms = api_get(BOT_MULTISYMBOL_URL, "/api/signals")
        if signals_ms:
            st.markdown('<div class="section-title">📡 Signaux Récents</div>', unsafe_allow_html=True)
            df_sig_ms = pd.DataFrame(signals_ms)
            sig_cols = [c for c in ['timestamp', 'symbol', 'signal', 'price', 'strength', 'executed', 'reason'] if c in df_sig_ms.columns]
            if sig_cols:
                st.dataframe(df_sig_ms[sig_cols].tail(10), use_container_width=True, hide_index=True)

        if trades_ms:
            st.markdown('<div class="section-title">📊 Performance par Symbole</div>', unsafe_allow_html=True)
            ms_stats = calculate_stats(trades_ms)
            if ms_stats:
                df_stats_ms = pd.DataFrame.from_dict(ms_stats, orient='index').reset_index().rename(columns={'index': 'symbol'})
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    fig_wr = px.bar(df_stats_ms, x='symbol', y='win_rate', title="Winning Rate % per Symbol", color='win_rate', color_continuous_scale='Viridis')
                    fig_wr.update_layout(template="plotly_dark", height=300, margin=dict(l=0, r=0, t=30, b=0))
                    st.plotly_chart(fig_wr, use_container_width=True)
                with col_c2:
                    fig_profit = px.bar(df_stats_ms, x='symbol', y='profit', title="Total Profit USDT per Symbol", color='profit', color_continuous_scale='RdYlGn')
                    fig_profit.update_layout(template="plotly_dark", height=300, margin=dict(l=0, r=0, t=30, b=0))
                    st.plotly_chart(fig_profit, use_container_width=True)

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

        positions = api_get(BOT_ZONE2_URL, "/api/positions")
        if positions:
            st.markdown('<div class="section-title">📍 Positions Ouvertes</div>', unsafe_allow_html=True)
            df_pos = pd.DataFrame(positions)
            pos_cols = [c for c in ['symbol', 'side', 'entry_price', 'last_price', 'sl_price', 'tp_price', 'qty', 'trailing_activated'] if c in df_pos.columns]
            if pos_cols:
                st.dataframe(df_pos[pos_cols], use_container_width=True, hide_index=True)
        elif data2:
            st.info("Aucune position ouverte.")

        signals = api_get(BOT_ZONE2_URL, "/api/signals")
        if signals:
            st.markdown('<div class="section-title">📡 Signaux FVG+Fibonacci Récents</div>', unsafe_allow_html=True)
            df_sig = pd.DataFrame(signals)
            sig_cols = [c for c in ['timestamp', 'bot', 'signal', 'price', 'strength', 'executed', 'reason'] if c in df_sig.columns]
            if sig_cols:
                st.dataframe(df_sig[sig_cols].tail(20), use_container_width=True, hide_index=True)

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

            st.markdown('<div class="section-title">📊 Performance par Symbole</div>', unsafe_allow_html=True)
            z2_stats = calculate_stats(trades_z2)
            if z2_stats:
                df_stats_z2 = pd.DataFrame.from_dict(z2_stats, orient='index').reset_index().rename(columns={'index': 'symbol'})
                col_z1, col_z2 = st.columns(2)
                with col_z1:
                    fig_wr2 = px.bar(df_stats_z2, x='symbol', y='win_rate', title="Winning Rate % per Symbol", color='win_rate', color_continuous_scale='Viridis')
                    fig_wr2.update_layout(template="plotly_dark", height=300, margin=dict(l=0, r=0, t=30, b=0))
                    st.plotly_chart(fig_wr2, use_container_width=True)
                with col_z2:
                    fig_profit2 = px.bar(df_stats_z2, x='symbol', y='profit', title="Total Profit USDT per Symbol", color='profit', color_continuous_scale='RdYlGn')
                    fig_profit2.update_layout(template="plotly_dark", height=300, margin=dict(l=0, r=0, t=30, b=0))
                    st.plotly_chart(fig_profit2, use_container_width=True)

    if refresh_rate > 0:
        time.sleep(refresh_rate)
        st.rerun()

def render_market_scanner():
    st.title("📡 Live Market Scanner")
    st.markdown("Scanne une liste de symboles indépendante avec la stratégie V7 Robust.")
    col_l, col_r = st.columns([1, 3])
    with col_l:
        timeframe = st.selectbox("Timeframe", ["1m", "5m", "15m", "30m", "1h"])
        
        # Charger la liste depuis SCANNER_SYMBOLS, fallback vers SYMBOLS du bot
        _default_scanner_symbols = os.environ.get(
            "SCANNER_SYMBOLS",
            "BTC/USDT:USDT,ETH/USDT:USDT,BNB/USDT:USDT,SOL/USDT:USDT,"
            "XRP/USDT:USDT,DOGE/USDT:USDT,ADA/USDT:USDT,AVAX/USDT:USDT,"
            "LINK/USDT:USDT,DOT/USDT:USDT,TRX/USDT:USDT,MATIC/USDT:USDT,"
            "LTC/USDT:USDT,UNI/USDT:USDT,ATOM/USDT:USDT,FTM/USDT:USDT,"
            "NEAR/USDT:USDT,APT/USDT:USDT,OP/USDT:USDT,ARB/USDT:USDT"
        )
        symbols_text = st.text_area(
            "Symboles à scanner",
            value=_default_scanner_symbols,
            height=200,
            help="Un symbole par ligne ou séparés par des virgules. Ex: BTC/USDT:USDT"
        )
        # Parser les symboles (supporte virgule ou retour à la ligne)
        scan_symbols = [s.strip() for s in symbols_text.replace("\n", ",").split(",") if s.strip()]
        st.caption(f"**{len(scan_symbols)} symboles** dans la liste")
        
        if st.button("🚀 Lancer le scan", type="primary", use_container_width=True):
            st.session_state.run_scan = True
            st.session_state.scan_symbols_list = scan_symbols

    with col_r:
        if st.session_state.get('run_scan'):
            try:
                from strategy_v7_robust import apply_indicators, check_signal
                from config import exchange
                
                # Utiliser la liste sauvegardée lors du clic sur le bouton
                symbols_to_scan = st.session_state.get('scan_symbols_list', ["BTC/USDT:USDT"])
                
                progress = st.progress(0)
                status = st.empty()
                results = []
                
                for i, symbol in enumerate(symbols_to_scan):
                    status.text(f"Scan {symbol} ({i+1}/{len(symbols_to_scan)})...")
                    try:
                        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=250)
                        if not ohlcv or len(ohlcv) < 100:
                            results.append({"Symbole": symbol, "Signal": "⚠️ Pas assez de données", "Score": "–", "Prix": "–", "RSI": "–"})
                            continue
                            
                        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
                        # Sécurité type numérique
                        for col in ["open", "high", "low", "close", "volume"]:
                            df[col] = pd.to_numeric(df[col], errors='coerce')
                            
                        df = apply_indicators(df)
                        signal, score, atr = check_signal(df)
                        
                        last_row = df.iloc[-1]
                        price = last_row['close']
                        rsi = last_row['rsi'] if 'rsi' in df.columns else 0
                        
                        sig_text = "🟢 BUY" if signal == "long" else ("🔴 SELL" if signal == "short" else "⬜ Neutre")
                        results.append({
                            "Symbole": symbol, 
                            "Signal": sig_text, 
                            "Score": f"{score}/5" if signal else ("0/5" if not pd.isna(last_row.get('adx')) else "–"), 
                            "Prix": f"{price:.4f}", 
                            "RSI": f"{rsi:.1f}"
                        })
                    except Exception as e:
                        print(f"Error scanning {symbol}: {e}")
                        results.append({"Symbole": symbol, "Signal": "❌ Erreur", "Score": "–", "Prix": "–", "RSI": "–"})
                    
                    progress.progress((i + 1) / len(symbols_to_scan))
                    time.sleep(0.05) # Un peu plus rapide
                
                status.text("Scan terminé !")
                st.session_state.scan_results = results
                st.session_state.run_scan = False
            except Exception as e:
                st.error(f"Erreur globale scan : {e}")
                st.session_state.run_scan = False

        # Affichage des résultats s'ils existent en session_state
        if "scan_results" in st.session_state and st.session_state.scan_results:
            df_res = pd.DataFrame(st.session_state.scan_results)
            # Trier : Opportunités en premier
            if not df_res.empty:
                # Créer une colonne de tri temporaire
                def sort_rank(sig):
                    if "BUY" in sig or "SELL" in sig: return 0
                    if "Neutre" in sig: return 1
                    return 2
                df_res['rank'] = df_res['Signal'].apply(sort_rank)
                df_res = df_res.sort_values('rank').drop(columns=['rank'])
                
                active = df_res[df_res['Signal'].str.contains("BUY|SELL", na=False)]
                st.success(f"{len(active)} setup(s) potentiel(s) trouvé(s) sur {len(df_res)} symboles.")
                st.dataframe(df_res, use_container_width=True, hide_index=True)
                
                if st.button("🗑️ Effacer les résultats"):
                    st.session_state.scan_results = []
                    st.rerun()

def render_visual_backtester():
    st.title("🧪 Visual Strategy Backtester")
    with st.form("backtest_form"):
        c1, c2, c3 = st.columns(3)
        symbol = c1.text_input("Symbole", value="BTC/USDT")
        tf = c2.selectbox("Timeframe", ["1m", "5m", "15m", "30m", "1h", "4h"], index=1)
        strat = c3.selectbox("Stratégie", ["V6 Aggressive", "V7 Robust"])
        p1, p2, p3 = st.columns(3)
        sl_m = p1.number_input("SL ATR Multiplier", value=1.5, step=0.1)
        tp_m = p2.number_input("TP ATR Multiplier", value=3.0, step=0.1)
        score_th = p3.number_input("Score Threshold", value=3, min_value=1, max_value=5)
        submitted = st.form_submit_button("▶️ Lancer la simulation", type="primary", use_container_width=True)
    if submitted:
        try:
            from config import exchange
            from auto_tuner import AutoTuner
            with st.spinner(f"Récupération données..."):
                tuner = AutoTuner(exchange, None)
                df = tuner.fetch_historical_data(symbol, tf, hours=72)
            if df is not None and not df.empty:
                strat_name = 'v6_aggressive' if strat == "V6 Aggressive" else 'v7_robust'
                p = {'sl_multi': sl_m, 'tp_multi': tp_m, 'threshold': score_th}
                apply_ind, check_sig = tuner.strategies[strat_name]
                df = apply_ind(df)
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                buy_x, buy_y, sell_x, sell_y, capital = [], [], [], [], 1000.0
                equity_curve, time_axis = [capital], [df['timestamp'].iloc[0]]
                start_idx = 200 if strat_name == 'v7_robust' else 25
                for i in range(start_idx, len(df) - 1):
                    slice_df = df.iloc[:i+1]
                    signal, score, atr = check_sig(slice_df)
                    if signal and score >= p['threshold']:
                        outcome = tuner.simulate_trade(df, i, signal, p)
                        if outcome != 0:
                            capital += outcome * atr * (capital * 0.02 / (atr * p['sl_multi']))
                            if signal == 'long': buy_x.append(df['timestamp'].iloc[i]); buy_y.append(df['close'].iloc[i])
                            else: sell_x.append(df['timestamp'].iloc[i]); sell_y.append(df['close'].iloc[i])
                            equity_curve.append(capital)
                            time_axis.append(df['timestamp'].iloc[i])
                st.subheader("📊 Price Action")
                fig = go.Figure(data=[go.Candlestick(x=df['timestamp'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='Prix')])
                if buy_x: fig.add_trace(go.Scatter(x=buy_x, y=buy_y, mode='markers', marker=dict(symbol='triangle-up', size=12, color='#00FF88'), name='BUY'))
                if sell_x: fig.add_trace(go.Scatter(x=sell_x, y=sell_y, mode='markers', marker=dict(symbol='triangle-down', size=12, color='#FF4B4B'), name='SELL'))
                st.plotly_chart(fig, use_container_width=True)
                roi = ((capital / 1000) - 1) * 100
                st.metric("ROI Final", f"{roi:.2f}%", delta=f"{capital-1000:.2f} USDT")
        except Exception as e:
            st.error(f"Erreur simulation : {e}")

# ==========================================================
# MAIN LOOP
# ==========================================================
def main():
    try:
        if not check_auth():
            login_page()
            st.stop()
        st.sidebar.title("🤖 Bots Dash V2")
        page = st.sidebar.radio("Nav", ["Live", "Scanner", "Backtester"])
        if page == "Live":
            rr = st.sidebar.slider("Refresh", 5, 60, 10)
            render_live_monitoring(rr)
        elif page == "Scanner":
            render_market_scanner()
        elif page == "Backtester":
            render_visual_backtester()
    except Exception as e:
        st.error(f"💥 CRITICAL ERROR: {e}")
        if st.button("Reload"): st.rerun()

if __name__ == "__main__":
    main()
