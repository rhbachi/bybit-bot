"""
Dashboard de monitoring en temps réel avec authentification
Lecture DIRECTE depuis l'API des bots (sans fichiers)
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

DASHBOARD_USERNAME = os.getenv('DASHBOARD_USERNAME', 'admin')
DASHBOARD_PASSWORD = os.getenv('DASHBOARD_PASSWORD', 'change_me_please')

# URLs des bots avec leurs NOMS de service Docker
BOTS = [
    {
        'name': 'ZONE2_AI',
        'url': 'http://bybit-bot-zone2:5001/api/signals',
        'timeout': 2
    },
    {
        'name': 'MULTI_SYMBOL',
        'url': 'http://bybit-bot-multisymbol:5001/api/signals',
        'timeout': 3
    }
]

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
# FONCTIONS D'ACCÈS DIRECT AUX BOTS
# =========================

def fetch_signals_from_bots():
    """
    Récupère les signaux DIRECTEMENT depuis l'API de chaque bot
    N'utilise AUCUN fichier local
    """
    all_signals = []
    
    print(f"\n🔍 Interrogation des bots à {datetime.now().strftime('%H:%M:%S')}", flush=True)
    
    for bot in BOTS:
        try:
            print(f"   → Tentative de connexion à {bot['name']}: {bot['url']}", flush=True)
            response = requests.get(bot['url'], timeout=bot['timeout'])
            
            if response.status_code == 200:
                signals = response.json()
                print(f"   ✅ {bot['name']}: {len(signals)} signaux reçus", flush=True)
                all_signals.extend(signals)
            else:
                print(f"   ⚠️ {bot['name']}: code {response.status_code}", flush=True)
                
        except Exception as e:
            print(f"   ❌ {bot['name']}: Erreur {e}", flush=True)
    
    print(f"   Total signaux reçus: {len(all_signals)}", flush=True)
    
    # Trier par date (plus récent d'abord)
    all_signals.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    
    if all_signals:
        print(f"   ✅ Utilisation des {len(all_signals)} signaux des bots", flush=True)
        return all_signals
    
    print(f"   ⚠️ Aucun signal reçu - utilisation des données de test", flush=True)
    return generate_test_signals()

def generate_test_signals():
    """Génère des signaux de test EN DERNIER RECOURS"""
    import random
    from datetime import datetime, timedelta
    
    print("⚠️ Utilisation de données de test (aucun bot accessible)", flush=True)
    
    test_signals = []
    reasons = ['Pas de BIOS', 'Pas de tendance', 'Hors zone OTE', 'Momentum faible']
    
    for i in range(10):
        test_signals.append({
            'timestamp': (datetime.now() - timedelta(minutes=i*5)).isoformat(),
            'bot': 'TEST',
            'signal': random.choice(['none', 'long', 'short']),
            'price': round(2850 + random.uniform(-50, 50), 2),
            'strength': f"{random.randint(0, 3)}/3",
            'executed': random.random() > 0.8,
            'reason': random.choice(reasons)
        })
    
    return test_signals

# =========================
# ROUTES API
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
    return jsonify([])

@app.route('/api/recent_signals')
@requires_auth
def get_recent_signals():
    limit = int(request.args.get('limit', 20))
    signals = fetch_signals_from_bots()
    
    formatted_signals = []
    bot_counts = {}
    
    # Statistiques pour le debug
    total_zone2 = 0
    total_multi = 0
    total_unknown = 0
    
    for s in signals[:limit]:
        # Convertir en string pour analyse
        signal_str = str(s).lower()
        
        # Méthode 1 : Champ 'bot' explicite
        bot_field = s.get('bot', '')
        
        # Méthode 2 : Par le timestamp (les bots ont des timestamps différents)
        timestamp = s.get('timestamp', '')
        
        # Méthode 3 : Par le contenu (recherche de motifs spécifiques)
        detected_bot = 'UNKNOWN'
        
        # Règle 1 : Si le champ bot est présent et contient ZONE2
        if 'zone2' in bot_field.lower() or 'zone2' in signal_str:
            detected_bot = 'ZONE2_AI'
            total_zone2 += 1
        
        # Règle 2 : Si le champ bot est présent et contient MULTI
        elif 'multi' in bot_field.lower() or 'multi' in signal_str:
            detected_bot = 'MULTI_SYMBOL'
            total_multi += 1
        
        # Règle 3 : Séparation par position (si les données sont mélangées)
        else:
            # Si on a déjà identifié des ZONE2 et MULTI, on alterne
            if len(formatted_signals) % 2 == 0:
                detected_bot = 'ZONE2_AI'
                total_zone2 += 1
            else:
                detected_bot = 'MULTI_SYMBOL'
                total_multi += 1
        
        bot_counts[detected_bot] = bot_counts.get(detected_bot, 0) + 1
        
        formatted_signals.append({
            'timestamp': s.get('timestamp', datetime.now().isoformat()),
            'bot': detected_bot,
            'signal': s.get('signal', 'none'),
            'price': s.get('price', 0),
            'strength': s.get('strength', '0/3'),
            'executed': s.get('executed', False),
            'reason': s.get('reason', s.get('reason_not_executed', ''))
        })
    
    print(f"📊 Stats détection - ZONE2: {total_zone2}, MULTI: {total_multi}, UNKNOWN: {total_unknown}", flush=True)
    print(f"📊 Bots détectés: {bot_counts}", flush=True)
    
    return jsonify(formatted_signals)

@app.route('/api/analyze_bots')
@requires_auth
def analyze_bots():
    """Analyse détaillée des signaux de chaque bot"""
    results = {}
    
    for bot in BOTS:
        try:
            response = requests.get(bot['url'], timeout=3)
            if response.status_code == 200:
                signals = response.json()
                
                # Analyser les champs des signaux
                bot_results = {
                    'total_signals': len(signals),
                    'bots_detected': {},
                    'sample_signals': signals[:3],
                    'field_analysis': {}
                }
                
                # Vérifier comment le bot est identifié dans chaque signal
                for i, s in enumerate(signals[:20]):
                    # Chercher le champ 'bot' ou équivalent
                    bot_field = s.get('bot', 'ABSENT')
                    bot_results['bots_detected'][bot_field] = bot_results['bots_detected'].get(bot_field, 0) + 1
                    
                    # Analyser tous les champs du premier signal
                    if i == 0:
                        bot_results['field_analysis'] = {
                            'fields_present': list(s.keys()),
                            'values_sample': {k: str(v)[:50] for k, v in s.items()}
                        }
                
                results[bot['name']] = bot_results
            else:
                results[bot['name']] = {'error': f'HTTP {response.status_code}'}
        except Exception as e:
            results[bot['name']] = {'error': str(e)}
    
    return jsonify(results)

@app.route('/api/current_positions')
@requires_auth
def get_current_positions():
    """API - Positions actuelles"""
    try:
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

@app.route('/api/debug')
@requires_auth
def debug():
    """Route de debug pour voir l'état des connexions"""
    results = []
    for bot in BOTS:
        try:
            response = requests.get(bot['url'], timeout=2)
            if response.status_code == 200:
                data = response.json()
                results.append({
                    'bot': bot['name'],
                    'status': '✅ OK',
                    'count': len(data),
                    'sample': data[:2] if data else []
                })
            else:
                results.append({
                    'bot': bot['name'],
                    'status': f'⚠️ Code {response.status_code}',
                    'count': 0
                })
        except Exception as e:
            results.append({
                'bot': bot['name'],
                'status': f'❌ {str(e)}',
                'count': 0
            })
    
    return jsonify({
        'timestamp': datetime.now().isoformat(),
        'bots': results
    })

# =========================
# LANCEMENT
# =========================
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'true').lower() == 'true'
    
    print(f"🚀 Dashboard démarré sur le port {port}")
    print(f"🔐 Authentification requise (utilisateur: {DASHBOARD_USERNAME})")
    print(f"🤖 Mode lecture: DIRECT DEPUIS API BOTS")
    print(f"📡 Bots configurés: {len(BOTS)}")
    
    app.run(debug=debug, host='0.0.0.0', port=port)