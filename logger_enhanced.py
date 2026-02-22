"""
Logger amélioré avec logs détaillés pour analyse
"""
import csv
import json
import os
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

# Créer les dossiers nécessaires
Path("logs").mkdir(exist_ok=True)
Path("analyzers").mkdir(exist_ok=True)

class EnhancedLogger:
    def __init__(self, bot_name):
        self.bot_name = bot_name
        self.trades_file = "logs/trades_detailed.csv"
        self.signals_file = "logs/signals_log.csv"
        self.performance_file = "logs/performance.json"
        self.errors_file = "logs/errors.log"
        
        # Initialiser les fichiers
        self._init_trades_file()
        self._init_signals_file()
        
    def _init_trades_file(self):
        """Initialise le fichier des trades détaillés"""
        if not os.path.exists(self.trades_file):
            with open(self.trades_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp',
                    'bot_name',
                    'symbol',
                    'side',
                    'entry_price',
                    'exit_price',
                    'quantity',
                    'pnl_usdt',
                    'pnl_percent',
                    'result',
                    'duration_seconds',
                    'exit_reason',
                    'entry_signal_strength',
                    'entry_rsi',
                    'entry_macd',
                    'entry_stoch_k',
                    'entry_stoch_d',
                    'entry_bb_position',
                    'entry_atr_percent',
                    'entry_ema_trend',
                    'exit_rsi',
                    'exit_macd',
                    'max_favorable_price',
                    'max_adverse_price',
                    'trailing_activated',
                    'commission_paid',
                    'slippage_bps'
                ])
    
    def _init_signals_file(self):
        """Initialise le fichier des signaux"""
        if not os.path.exists(self.signals_file):
            with open(self.signals_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp',
                    'bot_name',
                    'symbol',
                    'signal',
                    'price',
                    'trend',
                    'rsi',
                    'macd',
                    'stoch_k',
                    'stoch_d',
                    'bb_position',
                    'ote_zone',
                    'bios_detected',
                    'signal_strength',
                    'executed',
                    'reason_not_executed'
                ])
    
    def log_signal(self, signal_data):
        """
        Log un signal (même non executé)
        """
        try:
            with open(self.signals_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    datetime.now().isoformat(),
                    self.bot_name,
                    signal_data.get('symbol', 'UNKNOWN'),
                    signal_data.get('signal', 'none'),
                    signal_data.get('price', 0),
                    signal_data.get('trend', 'unknown'),
                    signal_data.get('rsi', 0),
                    signal_data.get('macd', 0),
                    signal_data.get('stoch_k', 0),
                    signal_data.get('stoch_d', 0),
                    signal_data.get('bb_position', 0),
                    signal_data.get('ote_zone', False),
                    signal_data.get('bios_detected', False),
                    signal_data.get('signal_strength', 0),
                    signal_data.get('executed', False),
                    signal_data.get('reason_not_executed', '')
                ])
        except Exception as e:
            self.log_error(f"Erreur log_signal: {e}")
    
    def log_trade_detailed(self, trade_data):
        """
        Log un trade avec toutes les métriques
        """
        try:
            with open(self.trades_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    trade_data.get('timestamp', datetime.now().isoformat()),
                    trade_data.get('bot_name', self.bot_name),
                    trade_data.get('symbol', 'UNKNOWN'),
                    trade_data.get('side', 'unknown'),
                    trade_data.get('entry_price', 0),
                    trade_data.get('exit_price', 0),
                    trade_data.get('quantity', 0),
                    trade_data.get('pnl_usdt', 0),
                    trade_data.get('pnl_percent', 0),
                    trade_data.get('result', 'unknown'),
                    trade_data.get('duration_seconds', 0),
                    trade_data.get('exit_reason', 'unknown'),
                    trade_data.get('entry_signal_strength', 0),
                    trade_data.get('entry_rsi', 0),
                    trade_data.get('entry_macd', 0),
                    trade_data.get('entry_stoch_k', 0),
                    trade_data.get('entry_stoch_d', 0),
                    trade_data.get('entry_bb_position', 0),
                    trade_data.get('entry_atr_percent', 0),
                    trade_data.get('entry_ema_trend', ''),
                    trade_data.get('exit_rsi', 0),
                    trade_data.get('exit_macd', 0),
                    trade_data.get('max_favorable_price', 0),
                    trade_data.get('max_adverse_price', 0),
                    trade_data.get('trailing_activated', False),
                    trade_data.get('commission_paid', 0),
                    trade_data.get('slippage_bps', 0)
                ])
        except Exception as e:
            self.log_error(f"Erreur log_trade_detailed: {e}")
    
    def update_performance_metrics(self, metrics):
        """
        Met à jour les métriques de performance en temps réel
        """
        try:
            # Lire les métriques existantes
            if os.path.exists(self.performance_file):
                with open(self.performance_file, 'r', encoding='utf-8') as f:
                    perf = json.load(f)
            else:
                perf = {}
            
            # Mettre à jour
            perf[self.bot_name] = {
                **perf.get(self.bot_name, {}),
                **metrics,
                'last_update': datetime.now().isoformat()
            }
            
            # Sauvegarder
            with open(self.performance_file, 'w', encoding='utf-8') as f:
                json.dump(perf, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            self.log_error(f"Erreur update_performance: {e}")
    
    def log_error(self, error_msg, exception=None):
        """
        Log une erreur avec détails
        """
        timestamp = datetime.now().isoformat()
        with open(self.errors_file, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] {self.bot_name} - {error_msg}\n")
            if exception:
                f.write(f"Exception: {exception}\n")
                import traceback
                traceback.print_exc(file=f)
            f.write("-" * 50 + "\n")
    
    def get_recent_trades(self, limit=100):
        """Récupère les derniers trades pour le dashboard"""
        if not os.path.exists(self.trades_file):
            return []
        
        df = pd.read_csv(self.trades_file)
        df = df.tail(limit)
        return df.to_dict('records')
    
    def get_recent_signals(self, limit=50):
        """Récupère les derniers signaux pour le dashboard"""
        if not os.path.exists(self.signals_file):
            return []
        
        df = pd.read_csv(self.signals_file)
        df = df.tail(limit)
        return df.to_dict('records')

# Instance globale pour chaque bot
loggers = {}

def get_logger(bot_name):
    """Factory pour obtenir un logger par bot"""
    if bot_name not in loggers:
        loggers[bot_name] = EnhancedLogger(bot_name)
    return loggers[bot_name]