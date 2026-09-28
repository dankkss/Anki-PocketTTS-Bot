FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# Dependências de sistema (ffmpeg essencial para conversão de áudio MP3/WAV)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir pocket-tts || true

# Copiar código do projeto
COPY . .

# Criar diretórios de perfis e temporários
RUN mkdir -p /app/voice_profiles /tmp/anki_tts_audio

EXPOSE 8000

# Executar FastAPI ouvindo na porta $PORT definida pelo Render
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
