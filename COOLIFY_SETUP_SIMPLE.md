# 🚀 CONFIGURATION COOLIFY - BOT TRADING V6.0 (Sans Docker Compose)

## 📋 CONFIGURATION SIMPLE DANS COOLIFY

### ✅ **Option 1 : Bot Principal uniquement (RECOMMANDÉ pour débuter)**

#### 1️⃣ Application dans Coolify

**General Settings :**
- Repository : `https://github.com/rhbachi/bybit-bot.git`
- Branch : `main`
- Name : `bybit-bot-main`
- Build Pack : `Dockerfile` (détecté automatiquement)

#### 2️⃣ Variables d'environnement

Cliquer **Environment Variables** → **+ Add** :

```bash
# ========================================
# API BYBIT (OBLIGATOIRE)
# ========================================
BYBIT_API_KEY=votre_cle_api_ici
BYBIT_API_SECRET=votre_secret_api_ici

# ========================================
# TELEGRAM (RECOMMANDÉ)
# ========================================
TELEGRAM_BOT_TOKEN=123456789:ABC-DEF1234ghIkl
TELEGRAM_CHAT_ID=123456789

# ========================================
# CONFIGURATION TRADING (TESTS)
# ========================================
SYMBOL=ETH/USDT:USDT
TIMEFRAME=5m
CAPITAL=10
RISK_PER_TRADE=0.02
LEVERAGE=1

# ========================================
# BOT À LANCER (OPTIONNEL)
# ========================================
# Par défaut : bot_improved.py (bot principal V6)
# Pour changer, décommenter et modifier :
# START_CMD=python -u bot_improved.py
```

#### 3️⃣ Volumes (pour persistance des trades)

**Storage** → **+ Add Volume** :
- **Source Path** : `/app/trades.csv`
- **Destination Path** : `/app/trades.csv`
- **Type** : File

#### 4️⃣ Déployer

Cliquer **Deploy** → Coolify va :
1. Cloner le repo GitHub
2. Builder l'image Docker
3. Lancer le bot principal V6.0

#### 5️⃣ Vérifier les logs

**Logs** → Vous devriez voir :
```
🤖 Bot Bybit V6.0 IMPROVED démarré
✅ SL/TP automatiques activés
⚙️ Leverage configuré: 1x
💰 Solde disponible: 10 USDT
⏳ Analyse marché...
```

---

## 🔄 **Option 2 : Lancer le Bot Zone2 à la place**

Si vous voulez lancer le **bot Zone2** (mean reversion) au lieu du bot principal :

Dans **Environment Variables**, ajouter :
```bash
START_CMD=python -u bot_zone2_improved.py
```

Puis **Redeploy**.

---

## 🎯 **Option 3 : Lancer les 2 bots simultanément**

Pour lancer les 2 bots en même temps, **créer 2 applications séparées** :

### Application 1 : Bot Principal
- Name : `bybit-bot-main`
- Variables ENV : (voir ci-dessus)
- START_CMD : `python -u bot_improved.py` (ou laisser par défaut)

### Application 2 : Bot Zone2
- Name : `bybit-bot-zone2`
- Repository : `https://github.com/rhbachi/bybit-bot.git`
- Branch : `main`
- Variables ENV : **Mêmes variables** que Application 1
- **Ajouter** : `START_CMD=python -u bot_zone2_improved.py`
- Volume différent : `/app/trades_zone2.csv`

---

## 📊 **Monitoring dans Coolify**

### Voir les logs en temps réel
**Application** → **Logs** → Défilement automatique

### Shell interactif (debugging)
**Application** → **Shell** → Accès terminal

Commandes utiles :
```bash
# Vérifier la connexion API
python test_improvements.py

# Checklist de sécurité
python pre_launch_check.py

# Voir les trades
cat trades.csv

# Stats
python -c "from stats import compute_stats; print(compute_stats())"
```

---

## 🔄 **Mettre à jour après un commit GitHub**

### Méthode automatique
Activer **Auto Deploy** dans Coolify :
- Chaque `git push` déclenchera un redéploiement

### Méthode manuelle
1. Faire vos modifications localement
2. `git push origin main`
3. Dans Coolify → Application → **Redeploy**

---

## 🛑 **Arrêter / Redémarrer**

**Stop** : Coolify → Application → **Stop**
- ⚠️ Vérifier sur Bybit que les positions sont fermées

**Restart** : Coolify → Application → **Restart**
- Redémarre le container sans rebuild

**Redeploy** : Coolify → Application → **Redeploy**
- Pull GitHub + Rebuild + Restart

---

## 🐛 **Troubleshooting**

### Bot crash au démarrage
**Vérifier :**
1. Variables ENV définies (API keys)
2. Logs : `fatal: not found` → Fichier manquant
3. Logs : `Insufficient balance` → Réduire CAPITAL

**Solution :**
- Application → Environment Variables
- Vérifier que `BYBIT_API_KEY` et `BYBIT_API_SECRET` sont remplies

### SL/TP non placés
**Vérifier :**
- Permissions API Bybit : Read ✅ Trade ✅ Conditional Orders ✅
- Logs pour voir l'erreur exacte

**Action :**
- Placer manuellement sur Bybit en attendant la correction

### Aucun trade après 1h
**C'est normal !**
- La stratégie attend les bonnes conditions
- Peut prendre 2-3h avant le 1er signal
- Vérifier logs : "⏳ Analyse marché..." = bot actif

### "ModuleNotFoundError"
**Vérifier :**
- `requirements.txt` contient toutes les dépendances
- Redeploy pour forcer rebuild

---

## 📝 **Workflow de développement**

```bash
# Sur Windows

# 1. Modifier le code
# 2. Commit et push
git add .
git commit -m "Fix: amélioration XYZ"
git push origin main

# 3. Dans Coolify → Redeploy
# 4. Surveiller les logs
```

---

## ✅ **Checklist avant Deploy**

- [ ] Variables ENV définies dans Coolify
- [ ] CAPITAL = 10 (pour tests)
- [ ] RISK_PER_TRADE = 0.02 (2%)
- [ ] LEVERAGE = 1 (pas de leverage)
- [ ] Telegram configuré
- [ ] GitHub à jour avec Dockerfile V6
- [ ] 1 seul bot au début (bot_improved.py)

---

## 🎓 **Commandes START_CMD utiles**

```bash
# Bot principal V6 (par défaut)
START_CMD=python -u bot_improved.py

# Bot Zone2 V6
START_CMD=python -u bot_zone2_improved.py

# Ancien bot (si besoin de revenir en arrière)
START_CMD=python -u bot.py

# Test de connexion seulement
START_CMD=python -u test_improvements.py

# Checklist de sécurité
START_CMD=python -u pre_launch_check.py
```

---

## 🚨 **IMPORTANT - Premier déploiement**

1. ✅ Commencer avec **10 USDT** seulement
2. ✅ Lancer **1 seul bot** (bot_improved.py)
3. ✅ Surveiller les **logs Coolify** en temps réel
4. ✅ Vérifier le **premier trade** :
   - Notification Telegram reçue
   - SL/TP affichés : `SL/TP: ✅`
   - Vérifier sur **Bybit** que les ordres sont placés
5. ✅ Si tout OK après 24h → Envisager bot Zone2

---

## 📞 **Support**

**Logs** : Coolify → Application → Logs
**Shell** : Coolify → Application → Shell
**Restart** : Coolify → Application → Restart

**En cas de problème grave :**
1. Stop le bot dans Coolify
2. Vérifier Bybit → Fermer positions manuellement si nécessaire
3. Analyser les logs
4. Corriger et redéployer

---

**Prêt ? 🚀**

1. Remplacer le Dockerfile sur GitHub
2. Créer l'application dans Coolify
3. Définir les variables ENV
4. Deploy !
