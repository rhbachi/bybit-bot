FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy all project files
COPY . .

# Create data folder
RUN mkdir -p /app/data /app/logs

# Default environment variables
ENV BYBIT_API_KEY=""
ENV BYBIT_API_SECRET=""
ENV TELEGRAM_BOT_TOKEN=""
ENV TELEGRAM_CHAT_ID=""

# Expose Streamlit port
EXPOSE 8501

# Start Streamlit dashboard
CMD ["python", "-m", "streamlit", "run", "dashboard_v2/app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
