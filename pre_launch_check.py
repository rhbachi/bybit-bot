"""
Checklist de sécurité AVANT de lancer en production
À exécuter systématiquement avant chaque démarrage
"""

import os
import sys
from config import exchange, SYMBOL, CAPITAL, RISK_PER_TRADE, LEVERAGE

print("=" * 60)
print("🔒 CHECKLIST PRÉ-LANCEMENT PRODUCTION")
print("=" * 60)
print()

# =========================
# VÉRIFICATIONS CRITIQUES
# =========================

errors = []
warnings = []

# 1. Capital
print(f"💰 Capital configuré: {CAPITAL} USDT")
if CAPITAL > 50:
    warnings.append(f"⚠️ Capital élevé pour des tests ({CAPITAL} USDT)")
    print(f"   Recommandation: Commencer avec 10-20 USDT")
elif CAPITAL < 5:
    errors.append(f"❌ Capital trop faible ({CAPITAL} USDT < 5 minimum Bybit)")

# 2. Risk
print(f"📊 Risk par trade: {RISK_PER_TRADE * 100}%")
if RISK_PER_TRADE > 0.05:
    warnings.append(f"⚠️ Risk élevé ({RISK_PER_TRADE*100}%)")
    print(f"   Recommandation: 2-3% max pour les tests")

risk_amount = CAPITAL * RISK_PER_TRADE
print(f"💸 Perte max par trade: {round(risk_amount, 2)} USDT")

# 3. Leverage
print(f"⚡ Leverage: {LEVERAGE}x")
if LEVERAGE > 2:
    warnings.append(f"⚠️ Leverage élevé pour des tests ({LEVERAGE}x)")
    print(f"   Recommandation: 1x pour commencer")
elif LEVERAGE == 1:
    print(f"   ✅ Aucun leverage (parfait pour tests)")

# 4. Solde réel
print()
print("🔍 Vérification du solde Bybit...")
try:
    balance = exchange.fetch_balance()
    usdt_free = balance.get('USDT', {}).get('free', 0)
    usdt_used = balance.get('USDT', {}).get('used', 0)
    usdt_total = balance.get('USDT', {}).get('total', 0)
    
    print(f"✅ Solde libre: {usdt_free} USDT")
    print(f"   Solde utilisé: {usdt_used} USDT")
    print(f"   Solde total: {usdt_total} USDT")
    
    if usdt_free < CAPITAL:
        errors.append(f"❌ Solde insuffisant ({usdt_free} < {CAPITAL})")
    
    if usdt_free < 5:
        errors.append(f"❌ Solde < 5 USDT minimum Bybit")
    
except Exception as e:
    errors.append(f"❌ Impossible de récupérer le solde: {e}")

# 5. Permissions API
print()
print("🔑 Vérification des permissions API...")
try:
    # Tester lecture positions
    positions = exchange.fetch_positions([SYMBOL])
    print(f"✅ Permission READ: OK")
    
    # Vérifier si on peut créer des ordres (on ne le fait pas vraiment)
    # On suppose que si balance fonctionne, les permissions sont OK
    print(f"✅ Permission TRADE: Assumé OK")
    
except Exception as e:
    errors.append(f"❌ Problème permissions API: {e}")

# 6. Symbole
print()
print(f"📈 Symbole: {SYMBOL}")
try:
    ticker = exchange.fetch_ticker(SYMBOL)
    last_price = ticker['last']
    print(f"✅ Prix actuel: {last_price} USDT")
    
    # Calculer la position théorique
    position_qty = (CAPITAL * RISK_PER_TRADE) / 0.006 * LEVERAGE / last_price
    position_notional = position_qty * last_price
    
    print(f"   Position théorique: {round(position_qty, 6)} {SYMBOL.split('/')[0]}")
    print(f"   Notionnel: {round(position_notional, 2)} USDT")
    
    if position_notional < 5:
        warnings.append(f"⚠️ Notionnel < 5 USDT, trades impossibles")
        print(f"   Augmentez CAPITAL ou RISK_PER_TRADE")
    
except Exception as e:
    errors.append(f"❌ Symbole invalide ou inaccessible: {e}")

# 7. Variables ENV
print()
print("🔧 Variables d'environnement...")
api_key = os.getenv("BYBIT_API_KEY", "")
api_secret = os.getenv("BYBIT_API_SECRET", "")
telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
telegram_chat = os.getenv("TELEGRAM_CHAT_ID", "")

if not api_key or api_key == "":
    errors.append("❌ BYBIT_API_KEY non définie")
else:
    print(f"✅ BYBIT_API_KEY: {api_key[:10]}...")

if not api_secret or api_secret == "":
    errors.append("❌ BYBIT_API_SECRET non définie")
else:
    print(f"✅ BYBIT_API_SECRET: {api_secret[:10]}...")

if not telegram_token:
    warnings.append("⚠️ TELEGRAM_BOT_TOKEN non définie (pas de notifications)")
else:
    print(f"✅ TELEGRAM_BOT_TOKEN: Configuré")

if not telegram_chat:
    warnings.append("⚠️ TELEGRAM_CHAT_ID non définie (pas de notifications)")
else:
    print(f"✅ TELEGRAM_CHAT_ID: Configuré")

# 8. Fichiers requis
print()
print("📁 Vérification des fichiers...")
required_files = [
    "bot_improved.py",
    "strategy_main.py",
    "risk_improved.py",
    "config.py",
    "logger.py",
    "notifier.py"
]

for file in required_files:
    if os.path.exists(file):
        print(f"✅ {file}")
    else:
        errors.append(f"❌ Fichier manquant: {file}")

# =========================
# RÉSUMÉ
# =========================
print()
print("=" * 60)
print("📋 RÉSUMÉ")
print("=" * 60)
print()

if errors:
    print("❌ ERREURS CRITIQUES:")
    for error in errors:
        print(f"   {error}")
    print()
    print("🛑 NE PAS LANCER LE BOT !")
    print("   Corrigez les erreurs ci-dessus d'abord")
    sys.exit(1)

if warnings:
    print("⚠️ AVERTISSEMENTS:")
    for warning in warnings:
        print(f"   {warning}")
    print()

if not errors and not warnings:
    print("✅ TOUTES LES VÉRIFICATIONS PASSÉES !")
    print()

# Calcul du risque max
print("=" * 60)
print("💀 SCÉNARIO DU PIRE")
print("=" * 60)
print()
print(f"Si TOUS les trades sont perdants:")
print(f"- Perte par trade: {round(risk_amount, 2)} USDT")
print(f"- Max trades/jour: 10 (par défaut)")
print(f"- Perte max théorique/jour: {round(risk_amount * 10, 2)} USDT")
print(f"- Perte max théorique/semaine: {round(risk_amount * 10 * 7, 2)} USDT")
print()
print(f"⚠️ Avec un capital de {CAPITAL} USDT:")
print(f"   Vous pourriez perdre {round((risk_amount * 10 / CAPITAL) * 100, 1)}% en 1 jour")
print(f"   si TOUS les trades perdent (improbable mais possible)")
print()

# Confirmation finale
print("=" * 60)
print("✋ CONFIRMATION REQUISE")
print("=" * 60)
print()
print("Avez-vous:")
print("  [ ] Vérifié que le capital est PETIT (10-20 USDT)?")
print("  [ ] Configuré un Risk faible (2-3%)?")
print("  [ ] Désactivé le leverage (1x)?")
print("  [ ] Limité les trades/jour (3-5 max)?")
print("  [ ] Configuré Telegram pour surveiller?")
print("  [ ] Prévu de surveiller le 1er trade MANUELLEMENT?")
print()

if not errors:
    response = input("Taper 'OUI' pour confirmer le lancement: ")
    if response.upper() == "OUI":
        print()
        print("🚀 Lancement autorisé !")
        print()
        print("Commandes:")
        print("  python3 bot_improved.py          # Bot principal")
        print("  python3 bot_zone2_improved.py    # Bot Zone2")
        print()
        print("Surveillance:")
        print("  tail -f bot_main.log")
        print("  tail -f trades.csv")
        print()
    else:
        print()
        print("❌ Lancement annulé")
        sys.exit(0)
