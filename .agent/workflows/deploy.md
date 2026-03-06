---
description: Déploiement des mises à jour du bot
---

1. Pousser les changements sur Git :
```powershell
git add .
git commit -m "Update bots and dashboard API"
git push origin main
```

2. Sur le serveur Coolify :
- Cliquer sur **Redeploy** ou **Force Rebuild**.

3. Vérification :
- Accéder au dashboard
- Vérifier que le statut des bots est en vert (✅ OK)
