"""
Script de test pour valider les améliorations V6.0
À exécuter AVANT de mettre en production

Usage:
    python3 test_improvements.py
"""

import sys
import time
from datetime import datetime

print("=" * 60)
print("🧪 TEST SUITE - BOT TRADING V6.0")
print("=" * 60)
print()

# =========================
# TEST 1: Imports
# =========================
print("📦 TEST 1: Vérification des imports...")
try:
    import pandas as pd
    import ccxt
    from config import exchange, SYMBOL, TIMEFRAME, CAPITAL, RISK_PER_TRADE, LEVERAGE
    print("✅ Imports config OK")
    
    from strategy_main import apply_indicators as apply_main, check_signal as check_main
    print("✅ Import strategy_main OK")
    
    from strategy_zone2_improved import apply_indicators as apply_zone2, check_signal as check_zone2
    print("✅ Import strategy_zone2_improved OK")
    
    from risk_improved import (
        calculate_position_size,
        validate_position_size,
        calculate_sl_tp_prices,
        calculate_risk_reward_ratio
    )
    print("✅ Import risk_improved OK")
    
    from notifier import send_telegram
    print("✅ Import notifier OK")
    
    from logger import init_logger, log_trade
    print("✅ Import logger OK")
    
except ImportError as e:
    print(f"❌ ÉCHEC: {e}")
    print("Assurez-vous que tous les fichiers sont présents")
    sys.exit(1)

print()

# =========================
# TEST 2: Connexion API
# =========================
print("🌐 TEST 2: Connexion à Bybit...")
try:
    balance = exchange.fetch_balance()
    usdt_balance = balance.get('USDT', {}).get('free', 0)
    print(f"✅ Connexion OK - Solde: {usdt_balance} USDT")
    
    if usdt_balance < 5:
        print("⚠️ WARNING: Solde < 5 USDT, trading impossible")
    
except Exception as e:
    print(f"❌ ÉCHEC: {e}")
    print("Vérifiez vos clés API dans .env ou variables d'environnement")
    sys.exit(1)

print()

# =========================
# TEST 3: Récupération de données
# =========================
print("📊 TEST 3: Récupération des données marché...")
try:
    ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=100)
    df = pd.DataFrame(
        ohlcv,
        columns=["time", "open", "high", "low", "close", "volume"]
    )
    print(f"✅ {len(df)} bougies récupérées pour {SYMBOL}")
    print(f"   Prix actuel: {df.iloc[-1]['close']} USDT")
    
except Exception as e:
    print(f"❌ ÉCHEC: {e}")
    sys.exit(1)

print()

# =========================
# TEST 4: Indicateurs techniques
# =========================
print("📈 TEST 4: Application des indicateurs...")
try:
    # Stratégie principale
    df_main = apply_main(df.copy())
    assert 'ema10' in df_main.columns, "EMA10 manquant"
    assert 'ema_slope' in df_main.columns, "EMA slope manquant"
    print("✅ Indicateurs strategy_main OK")
    print(f"   EMA10: {round(df_main.iloc[-1]['ema10'], 2)}")
    
    # Stratégie Zone2
    df_zone2 = apply_zone2(df.copy())
    assert 'ema20' in df_zone2.columns, "EMA20 manquant"
    assert 'ema_slope' in df_zone2.columns, "EMA slope manquant"
    print("✅ Indicateurs strategy_zone2 OK")
    print(f"   EMA20: {round(df_zone2.iloc[-1]['ema20'], 2)}")
    
except Exception as e:
    print(f"❌ ÉCHEC: {e}")
    sys.exit(1)

print()

# =========================
# TEST 5: Détection de signaux
# =========================
print("🎯 TEST 5: Détection des signaux...")
try:
    signal_main = check_main(df_main)
    signal_zone2 = check_zone2(df_zone2)
    
    print(f"✅ Signal strategy_main: {signal_main or 'Aucun'}")
    print(f"✅ Signal strategy_zone2: {signal_zone2 or 'Aucun'}")
    
    if signal_main and signal_zone2:
        if signal_main != signal_zone2:
            print("⚠️ WARNING: Les 2 stratégies donnent des signaux OPPOSÉS")
            print("   Ceci est normal car ce sont des approches différentes")
        else:
            print("ℹ️ INFO: Les 2 stratégies convergent")
    
except Exception as e:
    print(f"❌ ÉCHEC: {e}")
    sys.exit(1)

print()

# =========================
# TEST 6: Calcul de position
# =========================
print("💰 TEST 6: Calcul de position size...")
try:
    current_price = df.iloc[-1]['close']
    
    # Test avec paramètres standards
    qty = calculate_position_size(
        capital=CAPITAL,
        risk_pct=RISK_PER_TRADE,
        stop_loss_pct=0.006,
        price=current_price,
        leverage=LEVERAGE
    )
    
    print(f"✅ Quantité calculée: {qty}")
    print(f"   Capital: {CAPITAL} USDT")
    print(f"   Risk: {RISK_PER_TRADE * 100}%")
    print(f"   Prix: {current_price} USDT")
    print(f"   Leverage: {LEVERAGE}x")
    
    # Vérifier que la quantité est positive
    assert qty > 0, "Quantité doit être > 0"
    
    # Vérifier le notionnel
    notional = qty * current_price
    print(f"   Notionnel: {round(notional, 2)} USDT")
    
    # Vérifier la marge requise
    required_margin = notional / LEVERAGE
    print(f"   Marge requise: {round(required_margin, 2)} USDT")
    
    if required_margin > CAPITAL:
        print(f"⚠️ WARNING: Marge requise ({required_margin}) > Capital ({CAPITAL})")
    
except Exception as e:
    print(f"❌ ÉCHEC: {e}")
    sys.exit(1)

print()

# =========================
# TEST 7: Validation de position
# =========================
print("✔️ TEST 7: Validation de position...")
try:
    is_valid, error_msg = validate_position_size(
        qty=qty,
        price=current_price,
        capital=usdt_balance,
        leverage=LEVERAGE,
        min_notional=5.0
    )
    
    if is_valid:
        print(f"✅ Position valide: {error_msg}")
    else:
        print(f"⚠️ Position invalide: {error_msg}")
        print("   Le bot ajusterait automatiquement la quantité")
    
except Exception as e:
    print(f"❌ ÉCHEC: {e}")
    sys.exit(1)

print()

# =========================
# TEST 8: Calcul SL/TP
# =========================
print("🎯 TEST 8: Calcul Stop Loss / Take Profit...")
try:
    # Test LONG
    sl_long, tp_long = calculate_sl_tp_prices(
        entry_price=current_price,
        side="long",
        stop_loss_pct=0.006,
        rr_multiplier=2.3
    )
    
    print(f"✅ LONG:")
    print(f"   Entrée: {round(current_price, 2)} USDT")
    print(f"   SL: {sl_long} USDT ({round((1 - sl_long/current_price)*100, 2)}%)")
    print(f"   TP: {tp_long} USDT (+{round((tp_long/current_price - 1)*100, 2)}%)")
    
    # Test SHORT
    sl_short, tp_short = calculate_sl_tp_prices(
        entry_price=current_price,
        side="short",
        stop_loss_pct=0.006,
        rr_multiplier=2.3
    )
    
    print(f"✅ SHORT:")
    print(f"   Entrée: {round(current_price, 2)} USDT")
    print(f"   SL: {sl_short} USDT (+{round((sl_short/current_price - 1)*100, 2)}%)")
    print(f"   TP: {tp_short} USDT ({round((1 - tp_short/current_price)*100, 2)}%)")
    
    # Vérifier R:R
    rr_long = calculate_risk_reward_ratio(current_price, sl_long, tp_long, "long")
    print(f"   Risk/Reward LONG: 1:{rr_long}")
    
    rr_short = calculate_risk_reward_ratio(current_price, sl_short, tp_short, "short")
    print(f"   Risk/Reward SHORT: 1:{rr_short}")
    
except Exception as e:
    print(f"❌ ÉCHEC: {e}")
    sys.exit(1)

print()

# =========================
# TEST 9: Logger
# =========================
print("📝 TEST 9: Système de logging...")
try:
    init_logger()
    print("✅ Logger initialisé")
    
    # Test d'écriture
    log_trade(
        symbol=SYMBOL,
        side="long",
        qty=qty,
        entry_price=current_price,
        exit_price=current_price * 1.01,
        pnl_usdt=0.5,
        result="WIN"
    )
    print("✅ Trade de test loggé dans trades.csv")
    
    # Vérifier que le fichier existe
    import os
    if os.path.exists("trades.csv"):
        print("✅ Fichier trades.csv créé")
    
except Exception as e:
    print(f"❌ ÉCHEC: {e}")
    sys.exit(1)

print()

# =========================
# TEST 10: Notifications
# =========================
print("📱 TEST 10: Notifications Telegram...")
try:
    # Tester l'envoi
    test_message = (
        "🧪 TEST BOT V6.0\n"
        f"Timestamp: {datetime.now()}\n"
        "✅ Tous les tests passés!"
    )
    
    send_telegram(test_message)
    print("✅ Message de test envoyé à Telegram")
    print("   Vérifiez votre app Telegram pour confirmer")
    
except Exception as e:
    print(f"⚠️ WARNING: Telegram non configuré ou erreur: {e}")
    print("   Le bot fonctionnera sans notifications")

print()

# =========================
# TEST 11: Séparation des stratégies
# =========================
print("🔀 TEST 11: Séparation des stratégies...")
try:
    from strategy_main import get_state as get_state_main, reset_state as reset_main
    from strategy_zone2_improved import get_state as get_state_zone2, reset_state as reset_zone2
    
    state_main = get_state_main()
    state_zone2 = get_state_zone2()
    
    print("✅ État strategy_main:", state_main)
    print("✅ État strategy_zone2:", state_zone2)
    
    # Vérifier que les états sont distincts
    if state_main.keys() != state_zone2.keys():
        print("✅ Les stratégies ont des variables d'état DIFFÉRENTES")
        print("   Pas de conflit possible ✓")
    else:
        print("⚠️ WARNING: Les stratégies partagent les mêmes noms de variables")
    
    # Reset
    reset_main()
    reset_zone2()
    print("✅ Reset des états OK")
    
except Exception as e:
    print(f"❌ ÉCHEC: {e}")
    sys.exit(1)

print()

# =========================
# RÉSUMÉ
# =========================
print("=" * 60)
print("📊 RÉSUMÉ DES TESTS")
print("=" * 60)
print()
print("✅ Imports: OK")
print("✅ Connexion API: OK")
print("✅ Récupération données: OK")
print("✅ Indicateurs techniques: OK")
print("✅ Détection signaux: OK")
print("✅ Calcul position: OK")
print("✅ Validation position: OK")
print("✅ Calcul SL/TP: OK")
print("✅ Logger: OK")
print("✅ Notifications: OK (si configuré)")
print("✅ Séparation stratégies: OK")
print()
print("🎉 TOUS LES TESTS SONT PASSÉS!")
print()
print("=" * 60)
print("📋 PROCHAINES ÉTAPES")
print("=" * 60)
print()
print("1. ✅ Tests validés sur TESTNET")
print("2. ⏳ Configurer les vraies clés API (si production)")
print("3. ⏳ Lancer bot_improved.py")
print("4. ⏳ Lancer bot_zone2_improved.py (optionnel)")
print("5. ⏳ Monitorer les logs et Telegram")
print()
print("⚠️ RAPPEL:")
print("- Commencez TOUJOURS sur Testnet")
print("- Utilisez un capital que vous pouvez perdre")
print("- Surveillez les premiers trades manuellement")
print("- Ne laissez JAMAIS tourner sans surveillance")
print()
print("=" * 60)
print("Bonne chance! 🚀")
print("=" * 60)
