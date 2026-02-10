# 🚀 BOTS TRADING BYBIT - VERSION AMÉLIORÉE V6.0

## 📋 CHANGEMENTS MAJEURS

### ✅ Corrections Implémentées

1. **SL/TP Automatiques** ✔️
   - Placement automatique des ordres Stop Loss et Take Profit
   - Double méthode de placement (API native + ordres conditionnels)
   - Alertes en cas d'échec de placement

2. **Stratégies Complètement Séparées** ✔️
   - `strategy_main.py` → Bot principal (trend following)
   - `strategy_zone2_improved.py` → Bot Zone2 (mean reversion)
   - Variables d'état distinctes (`_zone_1_*` vs `_zone2_*`)

3. **Logs Corrigés** ✔️
   - Capture des prix d'entrée/sortie réels
   - Calcul de la durée des trades
   - Pourcentage de P&L par rapport au capital

4. **Vérification du Solde** ✔️
   - Vérification AVANT chaque trade
   - Ajustement automatique si position trop grande
   - Protection contre le sur-levier

---

## 📁 STRUCTURE DES FICHIERS

### Nouveaux Fichiers
```
bot_improved.py              # Bot principal V6.0
bot_zone2_improved.py        # Bot Zone2 V6.0
strategy_main.py             # Stratégie bot principal (séparée)
strategy_zone2_improved.py   # Stratégie Zone2 (séparée)
risk_improved.py             # Module risk avec validations
```

### Fichiers Inchangés (réutilisables)
```
config.py                    # Configuration (OK)
logger.py                    # Logger CSV (OK)
notifier.py                  # Notifications Telegram (OK)
stats.py                     # Statistiques (OK)
test_api.py                  # Test connexion API (OK)
requirements.txt             # Dépendances (OK)
Dockerfile                   # Docker (OK)
```

---

## 🔧 MIGRATION ÉTAPE PAR ÉTAPE

### 1️⃣ Backup des Anciens Fichiers

Sur votre VPS Hostinger :

```bash
# Se connecter au VPS
ssh votre_user@votre_ip

# Créer un backup
mkdir ~/trading_bot_backup
cp -r ~/votre_projet/* ~/trading_bot_backup/

# Vérifier
ls -la ~/trading_bot_backup/
```

### 2️⃣ Uploader les Nouveaux Fichiers

**Option A : Via SCP (depuis votre machine locale)**
```bash
# Télécharger les fichiers depuis Claude
# Puis uploader vers le VPS
scp bot_improved.py votre_user@votre_ip:~/projet/
scp bot_zone2_improved.py votre_user@votre_ip:~/projet/
scp strategy_main.py votre_user@votre_ip:~/projet/
scp strategy_zone2_improved.py votre_user@votre_ip:~/projet/
scp risk_improved.py votre_user@votre_ip:~/projet/
```

**Option B : Via Git (recommandé)**
```bash
# Sur votre VPS
cd ~/projet/
git pull  # Si vous utilisez Git
```

### 3️⃣ Tester en Mode TESTNET (IMPORTANT!)

Modifier `config.py` temporairement :

```python
# Ajouter avant la création de l'exchange
exchange = ccxt.bybit({
    "apiKey": BYBIT_API_KEY,
    "secret": BYBIT_API_SECRET,
    "enableRateLimit": True,
    "options": {
        "defaultType": "linear",
        "adjustForTimeDifference": True,
    },
    # AJOUTER CETTE LIGNE POUR LE TESTNET
    "urls": {
        "api": {
            "public": "https://api-testnet.bybit.com",
            "private": "https://api-testnet.bybit.com",
        }
    }
})
```

**Créer des clés API Testnet** sur : https://testnet.bybit.com/

### 4️⃣ Lancer les Tests

```bash
# Test bot principal
python3 bot_improved.py

# Dans un autre terminal, test bot Zone2
python3 bot_zone2_improved.py
```

**Que vérifier :**
- ✅ Connexion API OK
- ✅ Solde récupéré correctement
- ✅ Signaux détectés
- ✅ Ordres SL/TP placés
- ✅ Logs CSV créés avec bonnes données
- ✅ Notifications Telegram reçues

### 5️⃣ Passer en Production

Une fois les tests validés sur Testnet :

1. **Arrêter les anciens bots**
```bash
# Sur Coolify ou via systemd
sudo systemctl stop trading_bot
sudo systemctl stop trading_bot_zone2
```

2. **Modifier config.py** → retirer la section testnet

3. **Utiliser les vraies clés API**

4. **Relancer les nouveaux bots**
```bash
sudo systemctl start trading_bot
sudo systemctl start trading_bot_zone2
```

---

## 🐳 DÉPLOIEMENT DOCKER (Coolify)

### Dockerfile Amélioré

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copier requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier TOUS les fichiers
COPY config.py .
COPY logger.py .
COPY notifier.py .
COPY stats.py .
COPY risk_improved.py risk.py
COPY strategy_main.py .
COPY strategy_zone2_improved.py .
COPY bot_improved.py .
COPY bot_zone2_improved.py .

# Variables d'environnement (à définir dans Coolify)
ENV BYBIT_API_KEY=""
ENV BYBIT_API_SECRET=""
ENV TELEGRAM_BOT_TOKEN=""
ENV TELEGRAM_CHAT_ID=""
ENV SYMBOL="ETH/USDT:USDT"
ENV TIMEFRAME="5m"
ENV CAPITAL="30"
ENV RISK_PER_TRADE="0.05"
ENV LEVERAGE="2"

# Point d'entrée
CMD ["python", "-u", "bot_improved.py"]
```

### Configuration Coolify

**Service 1 : Bot Principal**
```yaml
name: trading-bot-main
image: votre_registry/bot-main:v6.0
environment:
  BYBIT_API_KEY: ${BYBIT_API_KEY}
  BYBIT_API_SECRET: ${BYBIT_API_SECRET}
  TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN}
  TELEGRAM_CHAT_ID: ${TELEGRAM_CHAT_ID}
  SYMBOL: "ETH/USDT:USDT"
  TIMEFRAME: "5m"
  CAPITAL: "30"
  RISK_PER_TRADE: "0.05"
  LEVERAGE: "2"
restart: always
```

**Service 2 : Bot Zone2**
```yaml
name: trading-bot-zone2
image: votre_registry/bot-zone2:v6.0
environment:
  # Mêmes variables que le bot principal
restart: always
command: ["python", "-u", "bot_zone2_improved.py"]
```

---

## 🎯 DIFFÉRENCES ENTRE LES 2 BOTS

### Bot Principal (`bot_improved.py`)
- **Stratégie** : Trend Following (trade AVEC la tendance)
- **Logique** : Détecte momentum fort → Entre dans direction du momentum
- **EMA** : 10 périodes (réactif)
- **Max Trades** : 10/jour
- **Cooldown** : 10 minutes
- **R:R** : 1:2.3

### Bot Zone2 (`bot_zone2_improved.py`)
- **Stratégie** : Mean Reversion (trade CONTRE la tendance)
- **Logique** : Détecte rejet → Entre dans direction inverse
- **EMA** : 20 périodes (plus lent)
- **Max Trades** : 8/jour
- **Cooldown** : 15 minutes
- **R:R** : 1:2.0

**⚠️ IMPORTANT** : Les deux bots peuvent trader le même symbole simultanément, mais avec des logiques opposées → Cela peut créer un hedge naturel.

---

## 📊 MONITORING

### Logs CSV Améliorés

Format des logs (`trades.csv`) :
```csv
timestamp,symbol,side,qty,entry_price,exit_price,pnl_usdt,result
2026-02-10T14:30:00,ETH/USDT:USDT,long,0.0234,2450.50,2465.20,0.34,WIN
```

### Notifications Telegram

Vous recevrez désormais :
- ✅ Prix d'entrée/sortie exacts
- ✅ Durée du trade en minutes
- ✅ P&L en USDT + pourcentage
- ✅ Statut SL/TP (placés ou non)
- ✅ Alerte si solde insuffisant

### Dashboard Stats (optionnel)

Créer un script `view_stats.py` :
```python
from stats import compute_stats

stats = compute_stats()
if stats:
    print(f"""
    📊 STATISTIQUES GLOBALES
    
    Total Trades: {stats['total']}
    Wins: {stats['wins']}
    Losses: {stats['losses']}
    Winrate: {stats['winrate']}%
    P&L Total: {stats['pnl']} USDT
    """)
```

---

## 🔒 SÉCURITÉ

### Clés API Bybit

**Permissions minimales requises** :
- ✅ Read (positions, balance)
- ✅ Trade (market orders, conditional orders)
- ❌ Withdraw (JAMAIS activer)

### Variables d'Environnement

**Ne JAMAIS hardcoder les clés dans le code !**

Utiliser `.env` :
```bash
BYBIT_API_KEY=votre_cle
BYBIT_API_SECRET=votre_secret
TELEGRAM_BOT_TOKEN=votre_token
TELEGRAM_CHAT_ID=votre_chat_id
```

Puis dans `config.py` :
```python
from dotenv import load_dotenv
load_dotenv()
```

---

## 🐛 TROUBLESHOOTING

### Problème : "Markets NOT loaded"

**Solution** :
```python
# Dans config.py, ajouter retry
import time

for attempt in range(3):
    try:
        exchange.load_markets()
        print("✅ Markets loaded")
        break
    except Exception as e:
        print(f"Tentative {attempt+1}/3 failed: {e}")
        time.sleep(5)
```

### Problème : "SL/TP non placés"

**Vérifier** :
- Permissions API (Trade + Conditional Orders)
- Format des paramètres Bybit V5
- Logs d'erreur détaillés

**Fallback manuel** : Si les SL/TP échouent, vous recevez une alerte Telegram → Placer manuellement sur Bybit.

### Problème : "Position trop grande"

**Cause** : `calculate_position_size()` retourne une quantité > capital disponible

**Solution automatique** : Le code ajuste automatiquement à 95% du capital

---

## 📈 BACKTESTING (Recommandé avant production)

**Option 1 : Backtrader**
```python
import backtrader as bt
from strategy_main import check_signal

# Créer une stratégie Backtrader
class MyStrategy(bt.Strategy):
    def next(self):
        df = self.get_dataframe()
        signal = check_signal(df)
        # ...
```

**Option 2 : Données historiques manuelles**
```python
# Télécharger data Bybit
ohlcv = exchange.fetch_ohlcv("ETH/USDT:USDT", "5m", limit=10000)

# Tester la stratégie
for i in range(100, len(ohlcv)):
    df = pd.DataFrame(ohlcv[i-100:i])
    df = apply_indicators(df)
    signal = check_signal(df)
    # Simuler trades...
```

---

## 🎓 AMÉLIORATIONS FUTURES

### Court Terme
- [ ] Ajouter trailing stop dynamique
- [ ] Implémenter break-even automatique
- [ ] Ajouter filtre de volatilité (ATR)

### Moyen Terme
- [ ] Dashboard web temps réel
- [ ] Alertes Discord en plus de Telegram
- [ ] Auto-ajustement du leverage selon volatilité

### Long Terme
- [ ] ML pour optimiser les paramètres
- [ ] Multi-symboles (BTC, SOL, etc.)
- [ ] Grid trading hybride

---

## 📞 SUPPORT

En cas de problème :

1. **Vérifier les logs** : `cat trades.csv`
2. **Vérifier Telegram** : Notifications d'erreur
3. **Tester en Testnet** : Avant de toucher la prod
4. **Consulter docs Bybit** : https://bybit-exchange.github.io/docs/v5/intro

---

## ⚠️ DISCLAIMER

**Ce code est fourni à titre éducatif.**

- ❌ Pas de garantie de profit
- ❌ Trading = Risque de perte totale
- ✅ Toujours tester sur Testnet
- ✅ Ne trader que ce que vous pouvez perdre
- ✅ Faire vos propres recherches (DYOR)

---

**Version** : 6.0  
**Date** : Février 2026  
**Auteur** : Claude (Anthropic)

---

## 🚀 QUICK START

```bash
# 1. Cloner/télécharger les fichiers
# 2. Installer dépendances
pip install -r requirements.txt

# 3. Configurer .env
nano .env

# 4. Tester en Testnet
python3 bot_improved.py

# 5. Si OK, passer en prod
# (changer les clés API dans .env)

# 6. Lancer en background
nohup python3 bot_improved.py > bot_main.log 2>&1 &
nohup python3 bot_zone2_improved.py > bot_zone2.log 2>&1 &

# 7. Vérifier les processus
ps aux | grep bot

# 8. Voir les logs en temps réel
tail -f bot_main.log
tail -f bot_zone2.log
```

**Bonne chance ! 🍀**
