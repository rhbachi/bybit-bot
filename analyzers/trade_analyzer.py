"""
Analyseur de performance avancé
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import os

class TradeAnalyzer:
    def __init__(self, trades_file="logs/trades_detailed.csv"):
        self.trades_file = trades_file
        self.df = None
        self.load_data()
    
    def load_data(self):
        """Charge les données de trades"""
        if os.path.exists(self.trades_file):
            self.df = pd.read_csv(self.trades_file)
            self.df['timestamp'] = pd.to_datetime(self.df['timestamp'])
            self.df = self.df.sort_values('timestamp')
        else:
            self.df = pd.DataFrame()
    
    def get_daily_stats(self, days=30):
        """Stats journalières"""
        if self.df.empty:
            return {}
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        recent = self.df[self.df['timestamp'] >= start_date]
        
        if recent.empty:
            return {}
        
        # Grouper par jour
        recent['date'] = recent['timestamp'].dt.date
        daily = recent.groupby('date').agg({
            'pnl_usdt': ['sum', 'count'],
            'result': lambda x: (x == 'WIN').sum()
        }).round(2)
        
        daily.columns = ['pnl', 'trades', 'wins']
        daily['winrate'] = (daily['wins'] / daily['trades'] * 100).round(1)
        
        return daily.to_dict('index')
    
    def get_hourly_performance(self):
        """Performance par heure de la journée"""
        if self.df.empty:
            return {}
        
        self.df['hour'] = self.df['timestamp'].dt.hour
        hourly = self.df.groupby('hour').agg({
            'pnl_usdt': 'sum',
            'result': lambda x: (x == 'WIN').mean() * 100
        }).round(2)
        
        hourly.columns = ['pnl', 'winrate']
        return hourly.to_dict('index')
    
    def get_best_parameters(self):
        """Analyse quels paramètres donnent les meilleurs résultats"""
        if self.df.empty:
            return {}
        
        # Analyse par signal strength
        strength_analysis = self.df.groupby('entry_signal_strength').agg({
            'pnl_usdt': 'mean',
            'result': lambda x: (x == 'WIN').mean() * 100,
            'pnl_usdt': 'count'
        }).round(2)
        
        strength_analysis.columns = ['avg_pnl', 'winrate', 'count']
        
        # Analyse par RSI à l'entrée
        self.df['rsi_bucket'] = pd.cut(self.df['entry_rsi'], bins=10)
        rsi_analysis = self.df.groupby('rsi_bucket').agg({
            'pnl_usdt': 'mean',
            'result': lambda x: (x == 'WIN').mean() * 100
        }).round(2)
        
        rsi_analysis.columns = ['avg_pnl', 'winrate']
        
        return {
            'by_signal_strength': strength_analysis.to_dict('index'),
            'by_rsi': rsi_analysis.to_dict('index')
        }
    
    def get_risk_metrics(self):
        """Métriques de risque avancées"""
        if self.df.empty or len(self.df) < 20:
            return {}
        
        # Calculs
        wins = self.df[self.df['result'] == 'WIN']
        losses = self.df[self.df['result'] == 'LOSS']
        
        win_rate = len(wins) / len(self.df) * 100
        avg_win = wins['pnl_usdt'].mean() if not wins.empty else 0
        avg_loss = abs(losses['pnl_usdt'].mean()) if not losses.empty else 0
        
        profit_factor = abs(wins['pnl_usdt'].sum() / losses['pnl_usdt'].sum()) if not losses.empty else float('inf')
        
        # Sharpe ratio simplifié
        returns = self.df['pnl_usdt'].values
        sharpe = (returns.mean() / returns.std()) * np.sqrt(365) if returns.std() > 0 else 0
        
        # Maximum drawdown
        cumulative = self.df['pnl_usdt'].cumsum()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max * 100
        max_drawdown = drawdown.min()
        
        return {
            'win_rate': round(win_rate, 2),
            'avg_win_usdt': round(avg_win, 2),
            'avg_loss_usdt': round(avg_loss, 2),
            'profit_factor': round(profit_factor, 2),
            'sharpe_ratio': round(sharpe, 2),
            'max_drawdown_pct': round(max_drawdown, 2),
            'total_trades': len(self.df),
            'total_pnl_usdt': round(self.df['pnl_usdt'].sum(), 2)
        }
    
    def get_best_trades(self, n=5):
        """Meilleurs trades"""
        if self.df.empty:
            return []
        
        return self.df.nlargest(n, 'pnl_usdt')[['timestamp', 'side', 'pnl_percent', 'entry_signal_strength']].to_dict('records')
    
    def get_worst_trades(self, n=5):
        """Pires trades"""
        if self.df.empty:
            return []
        
        return self.df.nsmallest(n, 'pnl_usdt')[['timestamp', 'side', 'pnl_percent', 'entry_signal_strength']].to_dict('records')


class SignalAnalyzer:
    def __init__(self, signals_file="logs/signals_log.csv"):
        self.signals_file = signals_file
        self.df = None
        self.load_data()
    
    def load_data(self):
        """Charge les données de signaux"""
        if os.path.exists(self.signals_file):
            self.df = pd.read_csv(self.signals_file)
            self.df['timestamp'] = pd.to_datetime(self.df['timestamp'])
        else:
            self.df = pd.DataFrame()
    
    def get_signal_stats(self):
        """Stats sur les signaux"""
        if self.df.empty:
            return {}
        
        total_signals = len(self.df)
        executed = self.df[self.df['executed'] == True]
        not_executed = self.df[self.df['executed'] == False]
        
        # Analyse par force de signal
        strength_analysis = self.df.groupby('signal_strength').agg({
            'executed': 'sum',
            'signal': 'count'
        })
        
        strength_analysis['execution_rate'] = (strength_analysis['executed'] / strength_analysis['signal'] * 100).round(1)
        
        # Raisons de non-exécution
        reasons = not_executed['reason_not_executed'].value_counts().to_dict()
        
        return {
            'total_signals': total_signals,
            'executed_signals': len(executed),
            'execution_rate': round(len(executed) / total_signals * 100, 2) if total_signals > 0 else 0,
            'by_strength': strength_analysis.to_dict('index'),
            'reasons_not_executed': reasons
        }