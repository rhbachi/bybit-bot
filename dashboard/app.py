"""
Dashboard de monitoring en temps réel avec authentification
"""
from flask import Flask, render_template, jsonify, request, Response
from functools import wraps
import pandas as pd
import json
import os
import sys
import secrets
from datetime import datetime, timedelta

# Ajouter le chemin parent pour les imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analyzers.trade_analyzer import TradeAnalyzer, SignalAnalyzer

app = Flask(__name__)

# =========================
# CONFIGURATION AUTHENTIFICATION
# =========================
app.secret_key = os.getenv('DASHBOARD_SECRET_KEY', secrets.token_hex(32))

# Identifiants depuis variables d'environnement (avec valeurs par défaut sécurisées)
DASHBOARD_USERNAME = os.getenv('DASHBOARD_USERNAME', 'admin')
DASHBOARD_PASSWORD = os.getenv('DASHBOARD_PASSWORD', 'change_me_please')

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
    
    if not os.path.exists('logs/trades_detailed.csv'):
        return jsonify([])
    
    df = pd.read_csv('logs/trades_detailed.csv')
    df = df.tail(limit)
    
    trades = []
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
    
    return jsonify(trades[::-1])  # Inverser pour avoir le plus récent en premier

@app.route('/api/recent_signals')
@requires_auth
def get_recent_signals():
    """API - Signaux récents"""
    limit = int(request.args.get('limit', 20))
    
    if not os.path.exists('logs/signals_log.csv'):
        return jsonify([])
    
    df = pd.read_csv('logs/signals_log.csv')
    df = df.tail(limit)
    
    signals = []
    for _, row in df.iterrows():
        signals.append({
            'timestamp': row['timestamp'],
            'signal': row['signal'],
            'price': row['price'],
            'strength': row['signal_strength'],
            'executed': row['executed'],
            'reason': row['reason_not_executed'] if pd.notna(row['reason_not_executed']) else ''
        })
    
    return jsonify(signals[::-1])

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
        # Lire le fichier des trades pour trouver les positions ouvertes
        # Note: Dans une vraie implémentation, vous devriez avoir un fichier positions.json
        # ou interroger directement le bot via une API
        
        # Pour l'instant, simulons avec des données de test
        import random
        
        # Simuler 0-3 positions ouvertes
        num_positions = random.randint(0, 3)
        positions = []
        
        base_price = 2850  # Prix de base pour ETH
        
        for i in range(num_positions):
            side = random.choice(['long', 'short'])
            entry = base_price + random.uniform(-50, 50)
            current = entry * (1 + random.uniform(-0.02, 0.03))
            pnl = ((current - entry) / entry * 100) if side == 'long' else ((entry - current) / entry * 100)
            
            positions.append({
                'id': i+1,
                'symbol': 'ETH/USDT',
                'side': side,
                'entry_price': round(entry, 2),
                'current_price': round(current, 2),
                'pnl_percent': round(pnl, 2),
                'pnl_usdt': round((current - entry) * 0.01 if side == 'long' else (entry - current) * 0.01, 2),
                'duration': f"{random.randint(10, 120)} min"
            })
        
        return jsonify({
            'positions': positions,
            'total_pnl': round(sum(p['pnl_usdt'] for p in positions), 2),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({'error': str(e), 'positions': []}), 500

# =========================
# LANCEMENT DU SERVEUR
# =========================
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'true').lower() == 'true'
    
    print(f"🚀 Dashboard démarré sur le port {port}")
    print(f"🔐 Authentification requise (utilisateur: {DASHBOARD_USERNAME})")
    print(f"⚠️  Changez le mot de passe dans les variables d'environnement !")
    
    app.run(debug=debug, host='0.0.0.0', port=port)