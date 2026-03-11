
import pandas as pd
import numpy as np
import sys
import os

# Mock the indicators to see if they fail on empty or weird data
from strategy_v7_robust import apply_indicators, check_signal

def test_scanner():
    print("Testing scanner logic...")
    # Mock some data
    data = []
    for i in range(250):
        data.append([
            1600000000 + i*60,
            100 + np.random.normal(0, 1),
            101 + np.random.normal(0, 1),
            99 + np.random.normal(0, 1),
            100 + np.random.normal(0, 1),
            1000 + np.random.normal(0, 100)
        ])
    
    df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume"])
    print("DataFrame head:")
    print(df.head())
    
    try:
        df_proc = apply_indicators(df)
        print("Indicators applied successfully.")
        print("Columns:", df_proc.columns.tolist())
        
        signal, score, atr = check_signal(df_proc)
        print(f"Signal: {signal}, Score: {score}, ATR: {atr}")
        
    except Exception as e:
        print(f"Error in strategy logic: {e}")

if __name__ == "__main__":
    test_scanner()
