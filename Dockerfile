FROM python:3.11-slim

# Variables Python pour logs en temps réel
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Copier et installer les dépendances
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copier tous les fichiers
COPY . .

# Créer dossier pour données
RUN mkdir -p /app/data

# Variables d'environnement par défaut
ENV BYBIT_API_KEY=""
ENV BYBIT_API_SECRET=""
ENV TELEGRAM_BOT_TOKEN=""
ENV TELEGRAM_CHAT_ID=""
ENV SYMBOL="ETH/USDT:USDT"
ENV TIMEFRAME="5m"
ENV CAPITAL="10"
ENV RISK_PER_TRADE="0.02"
ENV LEVERAGE="1"

# Healthcheck
HEALTHCHECK --interval=5m --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Commande de démarrage flexible
# Par défaut : bot_improved.py
CMD ["sh", "-c", "${START_CMD:-python -u bot_improved.py}"]
