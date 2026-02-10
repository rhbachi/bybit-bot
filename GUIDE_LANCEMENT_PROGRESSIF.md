# 🎯 GUIDE DE LANCEMENT PROGRESSIF - PRODUCTION

## 📋 PHASE 1: Configuration Minimale (Jour 1-2)

### Étape 1.1: Variables d'environnement
```bash
# .env ou variables Coolify
CAPITAL=10
RISK_PER_TRADE=0.02
LEVERAGE=1
SYMBOL=ETH/USDT:USDT
TIMEFRAME=5m
```

### Étape 1.2: Lancer SEULEMENT le bot principal
```bash
# Ne lancez qu'UN SEUL bot pour commencer
python3 bot_improved.py

# ❌ NE PAS lancer bot_zone2 encore
```

**Pourquoi ?**
- Simplifier le debugging
- Observer le comportement d'une seule stratégie
- Éviter les trades opposés simultanés

---

## 📊 PHASE 2: Surveillance Active (Premier Trade)

### Que surveiller ?

**Terminal/Logs:**
```bash
# Ouvrir 2 terminaux

# Terminal 1: Logs en direct
tail -f bot_main.log

# Terminal 2: Trades CSV
watch -n 5 "tail trades.csv"
```

**Telegram:**
- Vous devriez recevoir chaque notification
- Vérifier que SL/TP sont bien placés (✅)

**Bybit Interface:**
1. Aller sur https://bybit.com/trade/usdt/ETHUSDT
2. Onglet "Positions" → Vérifier position ouverte
3. Onglet "Orders" → Vérifier ordres SL/TP actifs
4. Vérifier manuellement que:
   - Le SL est bien placé
   - Le TP est bien placé
   - Les prix correspondent aux notifications

---

## ⚠️ PHASE 3: Premier Trade - Checklist

### Dès qu'un trade s'ouvre:

**1. Vérifier Position**
```
Interface Bybit → Positions:
- Direction: Long ou Short ✓
- Quantité: Correspond à la notification ✓
- Prix d'entrée: Proche du prix annoncé ✓
- Leverage: 1x ✓
```

**2. Vérifier Ordres SL/TP**
```
Interface Bybit → Orders:
- [ ] Ordre Stop Loss présent
- [ ] Prix SL correspond (-0.5% environ)
- [ ] Ordre Take Profit présent
- [ ] Prix TP correspond (+1.15% environ avec R:R 2.3)
- [ ] Type: "Conditional" ou "Stop Market"
```

**3. Si SL/TP ABSENTS:**
```bash
🚨 ACTION IMMÉDIATE:
1. Arrêter le bot: Ctrl+C
2. Placer SL/TP manuellement sur Bybit
3. Vérifier les logs pour l'erreur
4. Corriger avant de relancer
```

---

## 🛑 PHASE 4: Arrêt d'Urgence

### Conditions d'arrêt IMMÉDIAT:

1. **SL/TP non placés** → Risque max
2. **Position trop grande** (> 50% du capital)
3. **Erreurs API répétées**
4. **Comportement anormal** (trades en boucle)

### Arrêter proprement:
```bash
# Méthode 1: Ctrl+C dans le terminal
Ctrl+C

# Méthode 2: Kill le processus
ps aux | grep bot_improved
kill -9 [PID]

# Méthode 3: Via systemd
sudo systemctl stop trading_bot
```

### Après l'arrêt:
```bash
# 1. Vérifier Bybit
# - Fermer manuellement les positions ouvertes si nécessaire
# - Annuler les ordres SL/TP restants

# 2. Analyser les logs
cat bot_main.log | grep "ERROR"
cat trades.csv
```

---

## 📈 PHASE 5: Montée en Puissance (Après 3-5 jours)

### Si tout se passe bien:

**Jour 3-5:**
```bash
# Augmenter légèrement le capital
CAPITAL=15  # au lieu de 10
```

**Semaine 2:**
```bash
# Augmenter le risk (si winrate > 50%)
RISK_PER_TRADE=0.03  # au lieu de 0.02
```

**Semaine 3:**
```bash
# Ajouter du leverage (optionnel)
LEVERAGE=2  # au lieu de 1
```

**Semaine 4:**
```bash
# Lancer le 2ème bot
python3 bot_zone2_improved.py  # En parallèle
```

---

## 📊 MÉTRIQUES À SURVEILLER

### Quotidiennes:
- Nombre de trades
- Win rate (devrait être > 40%)
- P&L total
- Max drawdown

### Hebdomadaires:
- Sharpe ratio
- Temps moyen par trade
- Meilleurs/pires jours

### Script d'analyse:
```python
# stats_analysis.py
from stats import compute_stats

stats = compute_stats()
print(f"""
📊 STATS (7 derniers jours)

Trades: {stats['total']}
Wins: {stats['wins']} ({stats['winrate']}%)
Losses: {stats['losses']}
P&L: {stats['pnl']} USDT

{'✅ Performance OK' if stats['winrate'] > 40 else '⚠️ Revoir stratégie'}
""")
```

---

## 🚨 SIGNAUX D'ALERTE

### 🔴 Arrêter IMMÉDIATEMENT si:
- Drawdown > 30% du capital
- 5+ trades perdants consécutifs
- Erreurs API répétées
- SL/TP jamais placés

### 🟡 Surveiller ATTENTIVEMENT si:
- Win rate < 35%
- P&L négatif après 10 trades
- Trades trop fréquents (> 5/heure)
- Messages d'erreur sporadiques

### 🟢 Continuer si:
- Win rate > 40%
- SL/TP toujours placés
- P&L positif ou neutre
- Pas d'erreur critique

---

## 💡 CONSEILS PRATIQUES

### 1. Heures de Trading
```bash
# Éviter les heures creuses (faible liquidité)
# Meilleurs moments (UTC):
- 08:00-12:00 (Europe)
- 13:00-17:00 (US ouverture)
- 21:00-01:00 (Asie)

# Éviter:
- Week-ends (faible volume)
- Jours fériés US
- 02:00-06:00 UTC (très faible activité)
```

### 2. Gestion Manuelle
```bash
# Même avec le bot, surveillez:
- News crypto majeures
- Annonces Fed/BCE
- Listings/Delistings
- Hacks/Exploits

# En cas de news majeure → Arrêter le bot
```

### 3. Backup Quotidien
```bash
# Sauvegarder trades.csv
cp trades.csv trades_backup_$(date +%Y%m%d).csv

# Garder 30 jours d'historique
find . -name "trades_backup_*" -mtime +30 -delete
```

---

## 📱 NOTIFICATIONS PERSONNALISÉES

### Modifier notifier.py pour urgences:
```python
def send_urgent_alert(message):
    """Envoie une alerte avec son"""
    send_telegram(f"🚨🚨🚨 URGENT 🚨🚨🚨\n{message}")
    
# Appeler dans bot_improved.py si:
# - SL/TP non placés
# - Drawdown > 20%
# - 3+ erreurs API consécutives
```

---

## 🎓 RÈGLES D'OR

1. **Jamais 100% du capital** → Garder toujours une marge
2. **1 bot à la fois** au début
3. **Surveiller le 1er trade** manuellement
4. **Vérifier SL/TP** sur Bybit systématiquement
5. **Arrêter si comportement anormal**
6. **Analyser TOUS les trades** (gagnants ET perdants)
7. **Ne jamais augmenter capital** après une perte (revenge trading)
8. **Tester chaque modif** sur petit capital d'abord

---

## 📞 TROUBLESHOOTING RAPIDE

### "Insufficient balance"
→ Vérifier CAPITAL dans .env
→ Vérifier solde réel sur Bybit
→ Réduire CAPITAL ou RISK_PER_TRADE

### "SL/TP not placed"
→ Vérifier permissions API (Trade + Conditional Orders)
→ Vérifier logs pour erreur détaillée
→ Placer manuellement sur Bybit en attendant

### "Min notional not met"
→ Augmenter CAPITAL ou RISK_PER_TRADE
→ Le notionnel doit être > 5 USDT

### Trades trop fréquents
→ Augmenter COOLDOWN_SECONDS
→ Réduire MAX_TRADES_PER_DAY
→ Vérifier que les 2 bots ne tournent pas ensemble

---

**Bonne chance et soyez prudent ! 🍀**

**Rappel:** Vous pouvez tout perdre. Ne tradez que ce que vous pouvez perdre.
