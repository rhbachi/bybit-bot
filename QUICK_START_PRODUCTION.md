# ⚡ DÉMARRAGE RAPIDE - PRODUCTION AVEC PETIT CAPITAL

## 🎯 OBJECTIF
Tester les bots en production avec **10 USDT** de capital et configuration ultra-sécurisée.

---

## 📋 CHECKLIST PRÉ-DÉPLOIEMENT (15 min)

### ✅ Étape 1: Préparer l'environnement (5 min)

```bash
# Sur votre VPS Hostinger
cd ~/votre_projet

# Backup de l'ancienne version
mkdir backup_old_version
cp *.py backup_old_version/

# Télécharger les nouveaux fichiers depuis Claude
# (uploader via SCP, SFTP, ou copier-coller)

# Vérifier que tous les fichiers sont présents
ls -la
```

**Fichiers requis:**
- ✅ bot_improved.py
- ✅ bot_zone2_improved.py
- ✅ strategy_main.py
- ✅ strategy_zone2_improved.py
- ✅ risk_improved.py
- ✅ pre_launch_check.py
- ✅ test_improvements.py
- ✅ config.py (ancien, à garder)
- ✅ logger.py (ancien, à garder)
- ✅ notifier.py (ancien, à garder)
- ✅ requirements.txt (ancien, à garder)

---

### ✅ Étape 2: Configuration (5 min)

**Option A: Fichier .env (recommandé)**
```bash
# Créer le fichier .env
nano .env

# Copier-coller:
BYBIT_API_KEY=VOTRE_CLE_ICI
BYBIT_API_SECRET=VOTRE_SECRET_ICI
TELEGRAM_BOT_TOKEN=VOTRE_TOKEN_ICI
TELEGRAM_CHAT_ID=VOTRE_CHAT_ID_ICI
CAPITAL=10
RISK_PER_TRADE=0.02
LEVERAGE=1
SYMBOL=ETH/USDT:USDT
TIMEFRAME=5m

# Sauvegarder: Ctrl+O, Enter, Ctrl+X
```

**Option B: Variables Coolify**
```
Si vous utilisez Coolify, définir dans l'interface:
Environment Variables → Add Variable
```

**⚠️ PERMISSIONS API BYBIT:**
1. Aller sur https://www.bybit.com/app/user/api-management
2. Créer nouvelle clé API
3. **Permissions requises:**
   - ✅ Read
   - ✅ Trade
   - ❌ Withdraw (JAMAIS activer!)
4. **IP Whitelist:** Ajouter l'IP de votre VPS (recommandé)

---

### ✅ Étape 3: Test de connexion (3 min)

```bash
# Test basique
python3 test_improvements.py

# Doit afficher:
# ✅ Imports OK
# ✅ Connexion API OK
# ✅ Solde: X USDT
# ... etc
```

**Si erreur "ModuleNotFoundError":**
```bash
pip install --upgrade ccxt pandas python-dotenv requests
```

---

### ✅ Étape 4: Checklist sécurité (2 min)

```bash
python3 pre_launch_check.py

# Le script va:
# - Vérifier votre solde
# - Calculer le risque max
# - Valider la configuration
# - Demander confirmation

# Répondre 'OUI' seulement si TOUT est OK
```

**Si le script détecte des erreurs:**
- ❌ Les corriger AVANT de continuer
- ❌ Ne PAS lancer le bot tant qu'il y a des erreurs

---

## 🚀 LANCEMENT (1 min)

### Méthode 1: Terminal Direct (pour surveiller)

```bash
# Lancer le bot principal
python3 bot_improved.py

# Vous devriez voir:
# 🤖 Bot Bybit V6.0 IMPROVED démarré
# ✅ SL/TP automatiques activés
# ⚙️ Leverage configuré: 1x
# ⏳ Analyse marché...
```

**Laisser tourner** et surveiller les logs.

---

### Méthode 2: Background avec nohup

```bash
# Lancer en arrière-plan
nohup python3 bot_improved.py > bot_main.log 2>&1 &

# Vérifier le processus
ps aux | grep bot_improved

# Voir les logs en temps réel
tail -f bot_main.log
```

---

### Méthode 3: Systemd Service (recommandé)

```bash
# Créer le service
sudo nano /etc/systemd/system/trading_bot.service

# Copier-coller:
[Unit]
Description=Trading Bot Bybit V6.0
After=network.target

[Service]
Type=simple
User=votre_user
WorkingDirectory=/home/votre_user/projet
Environment="PATH=/usr/bin:/usr/local/bin"
EnvironmentFile=/home/votre_user/projet/.env
ExecStart=/usr/bin/python3 /home/votre_user/projet/bot_improved.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target

# Sauvegarder et activer
sudo systemctl daemon-reload
sudo systemctl enable trading_bot
sudo systemctl start trading_bot

# Voir les logs
sudo journalctl -u trading_bot -f
```

---

## 👀 SURVEILLANCE DU PREMIER TRADE (CRITIQUE!)

### Dans le Terminal
```bash
# Logs en temps réel
tail -f bot_main.log

# Attendre un signal (peut prendre 5-30 min)
# Vous verrez:
# 🎯 Signal détecté...
# 💰 Solde disponible: X USDT
# 📊 Ouverture LONG | Qty=X
```

### Sur Telegram
Vous recevrez une notification:
```
🚀 TRADE OUVERT
Direction: LONG
Prix: 2500.50 USDT
Quantité: 0.0234
SL: 2487.99 (-0.5%)
TP: 2529.35 (+1.15%)
Risk/Reward: 1:2.3
SL/TP: ✅  ← VÉRIFIER CETTE LIGNE!
```

**🚨 SI "SL/TP: ❌":**
1. **ARRÊTER LE BOT IMMÉDIATEMENT** (Ctrl+C)
2. Aller sur Bybit → Positions
3. Placer SL et TP **MANUELLEMENT**
4. Vérifier les logs d'erreur
5. Ne relancer qu'après correction

---

### Sur Bybit (Interface Web)

**1. Vérifier Position:**
```
https://www.bybit.com/trade/usdt/ETHUSDT
→ Onglet "Positions" (en bas)

Devrait afficher:
- Direction: Long/Short
- Qty: Correspond à Telegram
- Prix entrée: Proche du prix annoncé
- Leverage: 1x
- PnL: Temps réel
```

**2. Vérifier Ordres SL/TP:**
```
→ Onglet "Orders" (Conditional)

Devrait afficher 2 ordres:
1. Stop Loss
   - Type: Stop Market
   - Trigger: Prix SL
   - Reduce Only: Yes

2. Take Profit
   - Type: Take Profit Market
   - Trigger: Prix TP
   - Reduce Only: Yes
```

**🚨 SI ORDRES ABSENTS:**
1. **Ne pas paniquer**
2. Cliquer sur la position → "Add TP/SL"
3. Saisir manuellement:
   - SL: -0.5% du prix d'entrée
   - TP: +1.15% du prix d'entrée
4. Confirmer
5. Arrêter le bot et investiguer

---

## 📊 APRÈS LE PREMIER TRADE

### Trade Gagnant ✅
```
Telegram:
🟢 WIN - TRADE FERMÉ
Direction: LONG
Entrée: 2500.50
Sortie: 2529.35
PnL: 0.68 USDT (6.8%)
Durée: 37 min

CSV (trades.csv):
2026-02-10T14:30:00,ETH/USDT:USDT,long,0.0234,2500.50,2529.35,0.68,WIN
```

**Actions:**
- ✅ Analyser le trade dans trades.csv
- ✅ Vérifier que le SL/TP ont bien fonctionné
- ✅ Laisser continuer si tout est OK

---

### Trade Perdant ❌
```
Telegram:
🔴 LOSS - TRADE FERMÉ
Direction: LONG
Entrée: 2500.50
Sortie: 2487.99
PnL: -0.29 USDT (-2.9%)
Durée: 12 min
```

**C'est NORMAL!**
- ✅ Le SL a protégé votre capital
- ✅ Perte limitée à ~0.20 USDT (2% du capital)
- ✅ C'est exactement le comportement attendu

**Actions:**
- ✅ Vérifier que la perte correspond au risque prévu
- ✅ Continuer à surveiller les prochains trades
- ❌ NE PAS arrêter après 1 seul trade perdant

---

## 🛑 QUAND ARRÊTER LE BOT

### Arrêt IMMÉDIAT si:
- ❌ SL/TP jamais placés (3+ fois)
- ❌ Position > 50% du capital
- ❌ 5+ erreurs API consécutives
- ❌ Drawdown > 30% du capital
- ❌ Comportement bizarre (trades en boucle)

### Arrêt PLANIFIÉ si:
- ⚠️ Win rate < 30% après 10 trades
- ⚠️ P&L < -20% du capital
- ⚠️ Tous les trades perdent (problème stratégie)

### Comment arrêter:
```bash
# Méthode 1: Terminal direct
Ctrl+C

# Méthode 2: Background process
ps aux | grep bot_improved
kill [PID]

# Méthode 3: Systemd
sudo systemctl stop trading_bot

# Vérifier positions sur Bybit
# Fermer manuellement si nécessaire
```

---

## 📈 APRÈS 24H - ANALYSE

```bash
# Voir toutes les stats
python3 stats_analysis.py

# Ou manuellement:
cat trades.csv
```

**Métriques à vérifier:**
- Total trades: ≥ 3
- Win rate: > 40% (idéal > 50%)
- P&L total: > 0 (ou proche)
- Avg trade duration: 15-60 min

**Si stats OK → Continuer**
**Si stats mauvaises → Analyser et ajuster**

---

## 🔄 MONTÉE EN PUISSANCE (Optionnel)

**Après 3-5 jours de tests réussis:**

```bash
# Jour 5: Augmenter capital
CAPITAL=15  # au lieu de 10

# Jour 7: Augmenter risk (si winrate > 50%)
RISK_PER_TRADE=0.03  # au lieu de 0.02

# Jour 10: Ajouter leverage (optionnel)
LEVERAGE=2  # au lieu de 1

# Jour 14: Lancer 2ème bot
python3 bot_zone2_improved.py
```

**❌ NE JAMAIS:**
- Augmenter après une perte (revenge trading)
- Passer directement à 100+ USDT
- Activer leverage > 3x sans expérience
- Lancer les 2 bots dès le début

---

## 📞 SUPPORT / DEBUGGING

### Logs importants:
```bash
# Logs du bot
tail -f bot_main.log

# Trades CSV
cat trades.csv

# Logs système (si systemd)
sudo journalctl -u trading_bot -f
```

### Problèmes courants:

**"Insufficient balance"**
```
→ Vérifier: echo $CAPITAL
→ Vérifier: Solde Bybit
→ Réduire CAPITAL ou RISK_PER_TRADE
```

**"Min notional not met"**
```
→ Augmenter CAPITAL à 15-20 USDT
→ Ou augmenter RISK_PER_TRADE à 0.03
```

**Aucun trade après 1h**
```
→ Normal! Stratégie attend les bonnes conditions
→ Vérifier logs: "⏳ Analyse marché..."
→ Patience, peut prendre 2-3h parfois
```

---

## ✅ RÉSUMÉ - COMMANDES ESSENTIELLES

```bash
# 1. Lancer
python3 bot_improved.py

# 2. Surveiller
tail -f bot_main.log

# 3. Stats
cat trades.csv

# 4. Arrêter
Ctrl+C

# 5. Vérifier processus
ps aux | grep bot

# 6. Test connexion
python3 test_improvements.py
```

---

**🎯 RAPPEL FINAL:**
- ✅ Commencer avec 10 USDT
- ✅ 1 seul bot au début
- ✅ Surveiller le 1er trade MANUELLEMENT
- ✅ Vérifier SL/TP sur Bybit
- ✅ Ne pas paniquer si 1 trade perd

**Bonne chance! 🚀**
