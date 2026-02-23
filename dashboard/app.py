"""
Dashboard de monitoring en temps réel avec authentification
et lecture directe des logs du bot
"""
from flask import Flask, render_template, jsonify, request, Response
from functools import wraps
import pandas as pd
import json
import os
import sys
import secrets
import requests
from datetime import datetime, timedelta

# Ajouter le chemin parent pour les imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analyzers.trade_analyzer import TradeAnalyzer, SignalAnalyzer

app = Flask(__name__)

# =========================
# CONFIGURATION AUTHENTIFICATION
# =========================
app.secret_key = os.getenv('DASHBOARD_SECRET_KEY', secrets.token_hex(32))

# Identifiants depuis variables d'environnement
DASHBOARD_USERNAME = os.getenv('DASHBOARD_USERNAME', 'admin')
DASHBOARD_PASSWORD = os.getenv('DASHBOARD_PASSWORD', 'change_me_please')

# Configuration du bot (pour lire ses logs)
BOT_API_URL = os.getenv('BOT_API_URL', 'http://bybit-bot-zone2:5001')  # URL interne du bot
BOT_LOGS_PATH = os.getenv('BOT_LOGS_PATH', '/app/logs/signals_log.csv')

def check_auth(username, password):
    """Vérifie les identifiants"""
    return username == DASHBOARD_USERNAME and password == DASHBOARD_PASSWORD

def authenticate():
    """Renvoie une réponse d'authentification"""
    return Response(
        'Authentification requise pour accéder au dashboard',
        401,
        {'WWW-Authenticate': 'Basic realm="Dashboard Trading Bot"'}
    )

def requires_auth(f):
    """Décorateur pour protéger les routes"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# =========================
# CHARGEMENT DES ANALYSEURS
# =========================
trade_analyzer = TradeAnalyzer()
signal_analyzer = SignalAnalyzer()

# =========================
# FONCTIONS D'ACCÈS AUX LOGS
# =========================

def read_signals_from_bot():
    """
    Tente de lire les signaux depuis le conteneur du bot
    Fallback sur le fichier local si échec
    """
    signals = []
    
    # Méthode 1 : Lire depuis le fichier partagé (si monté)
    try:
        if os.path.exists('/app/logs/signals_log.csv'):
            df = pd.read_csv('/app/logs/signals_log.csv')
            if not df.empty:
                print("✅ Signaux lus depuis volume partagé", flush=True)
                return df.tail(50).to_dict('records')
    except Exception as e:
        print(f"⚠️ Erreur lecture volume partagé: {e}", flush=True)
    
    # Méthode 2 : Lire depuis le fichier local du dashboard
    try:
        local_path = 'logs/signals_log.csv'
        if os.path.exists(local_path):
            df = pd.read_csv(local_path)
            if not df.empty:
                print("✅ Signaux lus depuis logs local", flush=True)
                return df.tail(50).to_dict('records')
    except Exception as e:
        print(f"⚠️ Erreur lecture locale: {e}", flush=True)
    
    # Méthode 3 : Appeler l'API du bot (si disponible)
    try:
        response = requests.get(f"{BOT_API_URL}/api/signals", timeout=2)
        if response.status_code == 200:
            print("✅ Signaux lus depuis API bot", flush=True)
            return response.json()
    except:
        print("⚠️ API bot non disponible", flush=True)
    
    # Méthode 4 : Générer des données de test en dernier recours
    print("⚠️ Utilisation de données de test", flush=True)
    return generate_test_signals()

def generate_test_signals(limit=20):
    """Génère des signaux de test pour le dashboard"""
    import random
    from datetime import datetime, timedelta
    
    test_signals = []
    reasons = ['Pas de BIOS', 'Pas de tendance', 'Hors zone OTE', 'Momentum faible', 'Signal exécuté']
    
    for i in range(min(limit, 20)):
        is_executed = random.random() > 0.8  # 20% de chances d'être exécuté
        signal_type = random.choice(['long', 'short', 'none']) if not is_executed else random.choice(['long', 'short'])
        
        test_signals.append({
            'timestamp': (datetime.now() - timedelta(minutes=i*5)).isoformat(),
            'signal': signal_type,
            'price': round(2850 + random.uniform(-100, 100), 2),
            'strength': random.randint(0, 3),
            'executed': is_executed,
            'reason': '' if is_executed else random.choice(reasons)
        })
    
    return test_signals

# =========================
# ROUTES PROTÉGÉES
# =========================

@app.route('/')
@requires_auth
def index():
    """Page principale du dashboard"""
    return render_template('index.html')

@app.route('/api/overview')
@requires_auth
def get_overview():
    """API - Vue d'ensemble"""
    risk_metrics = trade_analyzer.get_risk_metrics()
    signal_stats = signal_analyzer.get_signal_stats()
    
    return jsonify({
        'risk_metrics': risk_metrics,
        'signal_stats': signal_stats,
        'last_update': datetime.now().isoformat()
    })

@app.route('/api/daily_stats')
@requires_auth
def get_daily_stats():
    """API - Stats journalières"""
    days = int(request.args.get('days', 30))
    daily = trade_analyzer.get_daily_stats(days)
    
    # Formater pour les graphiques
    dates = []
    pnls = []
    trades = []
    winrates = []
    
    for date, stats in daily.items():
        dates.append(str(date))
        pnls.append(stats['pnl'])
        trades.append(stats['trades'])
        winrates.append(stats['winrate'])
    
    return jsonify({
        'dates': dates,
        'pnls': pnls,
        'trades': trades,
        'winrates': winrates
    })

@app.route('/api/hourly')
@requires_auth
def get_hourly():
    """API - Performance horaire"""
    hourly = trade_analyzer.get_hourly_performance()
    
    hours = list(range(24))
    pnls = [hourly.get(h, {'pnl': 0})['pnl'] for h in hours]
    winrates = [hourly.get(h, {'winrate': 0})['winrate'] for h in hours]
    
    return jsonify({
        'hours': hours,
        'pnls': pnls,
        'winrates': winrates
    })

@app.route('/api/parameters')
@requires_auth
def get_parameters():
    """API - Analyse des paramètres"""
    return jsonify(trade_analyzer.get_best_parameters())

@app.route('/api/recent_trades')
@requires_auth
def get_recent_trades():
    """API - Trades récents"""
    limit = int(request.args.get('limit', 20))
    
    # Essayer de lire depuis le fichier partagé d'abord
    trades = []
    
    try:
        if os.path.exists('logs/trades_detailed.csv'):
            df = pd.read_csv('logs/trades_detailed.csv')
            df = df.tail(limit)
            for _, row in df.iterrows():
                trades.append({
                    'timestamp': row['timestamp'],
                    'side': row['side'],
                    'entry': row['entry_price'],
                    'exit': row['exit_price'],
                    'pnl': row['pnl_percent'],
                    'result': row['result'],
                    'exit_reason': row['exit_reason']
                })
    except Exception as e:
        print(f"⚠️ Erreur lecture trades: {e}", flush=True)
    
    return jsonify(trades[::-1])

@app.route('/api/recent_signals')
@requires_auth
def get_recent_signals():
    """API - Signaux récents (avec fallback automatique)"""
    signals = read_signals_from_bot()
    
    # Formater pour le dashboard
    formatted_signals = []
    for s in signals[:20]:  # Limiter à 20
        formatted_signals.append({
            'timestamp': s.get('timestamp', datetime.now().isoformat()),
            'signal': s.get('signal', 'none'),
            'price': s.get('price', 0),
            'strength': s.get('strength', s.get('signal_strength', 0)),
            'executed': s.get('executed', False),
            'reason': s.get('reason', s.get('reason_not_executed', ''))
        })
    
    return jsonify(formatted_signals)

@app.route('/api/best_trades')
@requires_auth
def get_best_trades():
    """API - Meilleurs trades"""
    return jsonify(trade_analyzer.get_best_trades(5))

@app.route('/api/worst_trades')
@requires_auth
def get_worst_trades():
    """API - Pires trades"""
    return jsonify(trade_analyzer.get_worst_trades(5))

@app.route('/api/current_positions')
@requires_auth
def get_current_positions():
    """API - Positions actuelles"""
    try:
        positions_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'current_positions.json')
        
        if os.path.exists(positions_file):
            with open(positions_file, 'r') as f:
                data = json.load(f)
            return jsonify(data)
        else:
            return jsonify({
                'positions': [],
                'total_pnl': 0,
                'timestamp': datetime.now().isoformat()
            })
            
    except Exception as e:
        return jsonify({
            'positions': [],
            'total_pnl': 0,
            'timestamp': datetime.now().isoformat(),
            'error': str(e)
        })

@app.route('/api/force_test_signals')
@requires_auth
def force_test_signals():
    """Force l'affichage de signaux de test (pour debug)"""
    return jsonify(generate_test_signals(20))

# =========================
# LANCEMENT DU SERVEUR
# =========================
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'true').lower() == 'true'
    
    print(f"🚀 Dashboard démarré sur le port {port}")
    print(f"🔐 Authentification requise (utilisateur: {DASHBOARD_USERNAME})")
    print(f"📊 Mode lecture signaux: Auto (fallback sur données test si nécessaire)")
    
    app.run(debug=debug, host='0.0.0.0', port=port)