import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta

# Import the strategies
import strategy_v6 as strat_v6
import strategy_v7_robust as strat_v7
import strategy_scalping_5m as strat_scalp5m

class AutoTuner:
    def __init__(self, exchange_client, logger_instance):
        self.exchange = exchange_client
        self.logger = logger_instance
        self.strategies = {
            'scalping_5m':   (strat_scalp5m.apply_indicators, strat_scalp5m.check_signal),
            'v6_aggressive': (strat_v6.apply_indicators,      strat_v6.check_signal),
            'v7_robust':     (strat_v7.apply_indicators,      strat_v7.check_signal),
        }
        # Timeframe required by each strategy (used when fetching backtest data)
        self.strategy_timeframe = {
            'scalping_5m':   '5m',
            'v6_aggressive': None,   # uses bot default timeframe
            'v7_robust':     None,
        }
        
        # Define parameter grids to test
        # Note: SL capped at 1.5x max to limit per-trade risk
        self.param_grid = [
            {'sl_multi': 1.2, 'tp_multi': 2.4, 'threshold': 4},
            {'sl_multi': 1.5, 'tp_multi': 3.0, 'threshold': 4},
            {'sl_multi': 1.2, 'tp_multi': 2.4, 'threshold': 3},
        ]

    def fetch_historical_data(self, symbol, timeframe, hours=48):
        """Fetch historical OHLCV data for backtesting."""
        try:
            tf_minutes = {'1m': 1, '5m': 5, '15m': 15, '1h': 60, '4h': 240}
            mins = tf_minutes.get(timeframe, 1)
            limit = min(int(hours * 60 / mins), 1000)

            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
            return df
        except Exception as e:
            self.logger.log_error(f"AutoTuner fetch error for {symbol}", e)
            return pd.DataFrame()

    def simulate_trade(self, df, start_index, signal, params):
        """Simulate a trade from a given index with specific parameters."""
        entry_price = df['close'].iloc[start_index]
        atr = df['atr'].iloc[start_index]
        
        sl_dist = atr * params['sl_multi']
        tp_dist = atr * params['tp_multi']
        
        if signal == 'long':
            sl_price = entry_price - sl_dist
            tp_price = entry_price + tp_dist
        else:
            sl_price = entry_price + sl_dist
            tp_price = entry_price - tp_dist
            
        # Scan forward — max 50 candles (realistic trade horizon)
        max_lookahead = 50
        end_index = min(start_index + 1 + max_lookahead, len(df))
        for i in range(start_index + 1, end_index):
            current = df.iloc[i]

            if signal == 'long':
                if current['low'] <= sl_price:
                    return -params['sl_multi'] # Lost SL multiples of ATR
                elif current['high'] >= tp_price:
                    return params['tp_multi'] # Won TP multiples of ATR
            else:
                if current['high'] >= sl_price:
                    return -params['sl_multi']
                elif current['low'] <= tp_price:
                    return params['tp_multi']

        return 0 # Trade not closed within the window

    def backtest_strategy(self, df, strat_name, params):
        """Run a quick backtest for a specific strategy and parameter set."""
        apply_ind, check_sig = self.strategies[strat_name]
        df_ind = apply_ind(df.copy())

        pnl_atr = 0
        trades_count = 0
        wins = 0

        # Warm-up bars needed per strategy
        warmup = {'v7_robust': 200, 'scalping_5m': 110}
        start_idx = warmup.get(strat_name, 25)
        
        if len(df_ind) <= start_idx:
            return -999, 0 # Not enough data
            
        for i in range(start_idx, len(df_ind) - 1):
            slice_df = df_ind.iloc[:i+1] # Simulate real-time up to index i
            signal, score, atr = check_sig(slice_df)
            
            if signal and score >= params['threshold']:
                # Found a signal, simulate the trade outcome
                outcome = self.simulate_trade(df_ind, i, signal, params)
                if outcome != 0:
                    trades_count += 1
                    pnl_atr += outcome
                    if outcome > 0:
                        wins += 1
                        
        win_rate = (wins / trades_count) * 100 if trades_count > 0 else 0
        # Require minimum 5 trades for a valid backtest result
        if trades_count < 5:
            return -999, 0
        return pnl_atr, win_rate

    def get_best_configuration(self, symbols, default_timeframe):
        """Determine the best strategy and parameters based on recent data.
        Backtests on up to 3 symbols and averages results to avoid overfitting.
        Returns None if no config beats the quality threshold — caller keeps
        the current strategy in that case."""
        test_symbols = symbols[:3] if isinstance(symbols, list) else [symbols]

        best_pnl = -float('inf')
        best_config = None
        results_log = []

        for strat_name in self.strategies.keys():
            # Each strategy is tested on its own required timeframe
            tf = self.strategy_timeframe.get(strat_name) or default_timeframe

            for params in self.param_grid:
                total_pnl = 0.0
                total_wr = 0.0
                valid_count = 0

                for sym in test_symbols:
                    df = self.fetch_historical_data(sym, tf, hours=48)
                    if df.empty or len(df) < 110:
                        continue
                    pnl, win_rate = self.backtest_strategy(df, strat_name, params)
                    if pnl == -999:
                        continue
                    total_pnl += pnl
                    total_wr += win_rate
                    valid_count += 1

                if valid_count == 0:
                    continue

                avg_pnl = total_pnl / valid_count
                avg_wr = total_wr / valid_count

                results_log.append(
                    f"{strat_name} [{tf}] {params}: PnL={avg_pnl:.2f} ATR, WR={avg_wr:.1f}% (n={valid_count})"
                )

                # Require win rate >= 40% AND positive PnL
                if avg_wr < 40.0 or avg_pnl <= 0:
                    continue
                if avg_pnl > best_pnl:
                    best_pnl = avg_pnl
                    best_config = {
                        'strategy': strat_name,
                        'params': params,
                        'expected_pnl': avg_pnl,
                        'expected_wr': avg_wr
                    }

        # Log results for debugging
        for res in results_log:
            print(f"🔍 Tuner check: {res}")

        if best_config:
            return best_config

        # Nothing qualifies — return None so the bot keeps its current strategy
        print("🔍 Tuner: aucune config qualifiée, stratégie actuelle conservée.")
        return None
