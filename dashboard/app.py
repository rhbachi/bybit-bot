"""
Dashboard de monitoring en temps réel
"""
from flask import Flask, render_template, jsonify, request
import pandas as pd
import json
import os
import sys
from datetime import datetime, timedelta

# Ajouter le chemin parent pour les imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analyzers.trade_analyzer import TradeAnalyzer, SignalAnalyzer

app = Flask(__name__)

# Charger les analyseurs
trade_analyzer = TradeAnalyzer()
signal_analyzer = SignalAnalyzer()

@app.route('/')
def index():
    """Page principale du dashboard"""
    # Récupérer le symbole depuis la config ou utiliser une valeur par défaut
    from config import SYMBOL
    # Nettoyer le symbole pour TradingView (enlever /USDT:USDT)
    tv_symbol = SYMBOL.replace('/USDT:USDT', 'USDT').replace('/', '')
    if 'BTC' in tv_symbol:
        tv_symbol = f"BINANCE:{tv_symbol}"
    else:
        tv_symbol = f"BINANCE:{tv_symbol}"
    
    return render_template('index.html', symbol=tv_symbol)
@app.route('/api/overview')
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
def get_parameters():
    """API - Analyse des paramètres"""
    return jsonify(trade_analyzer.get_best_parameters())

@app.route('/api/recent_trades')
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
def get_best_trades():
    """API - Meilleurs trades"""
    return jsonify(trade_analyzer.get_best_trades(5))

@app.route('/api/worst_trades')
def get_worst_trades():
    """API - Pires trades"""
    return jsonify(trade_analyzer.get_worst_trades(5))
@app.route('/api/current_positions')
def get_current_positions():
    """API - Positions actuelles"""
    try:
        # Lire le fichier des trades pour trouver les positions ouvertes
        # Note: Dans une vraie implémentation, vous devriez avoir un fichier positions.json
        # ou interroger directement le bot via une API
        
        # Pour l'instant, simulons avec des données de test
        import random
        from datetime import datetime, timedelta
        
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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)