"""
Configuração do Anki Pocket TTS Bot.
Carrega configurações de variáveis de ambiente ou arquivo externo de credenciais.
Em conformidade estrita com a Regra 1 (Zero-Secrets & Zero-PII).
"""

import os
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
VOICE_PROFILES_DIR = DATA_DIR / "voice_profiles"
TEMP_DIR = BASE_DIR / "temp"

# Garante diretórios essenciais
VOICE_PROFILES_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Tenta carregar credenciais externas locais (se existirem fora do git)
EXTERNAL_CONFIG_PATH = Path("/root/.config/anki-tts-bot/config.json")
_ext_config = {}
if EXTERNAL_CONFIG_PATH.exists():
    try:
        with open(EXTERNAL_CONFIG_PATH, "r", encoding="utf-8") as f:
            _ext_config = json.load(f)
    except Exception:
        pass

# Credenciais e parâmetros de execução
BOT_TOKEN = os.getenv("BOT_TOKEN", _ext_config.get("bot_token", ""))
BOT_USERNAME = os.getenv("BOT_USERNAME", _ext_config.get("bot_username", "dankkss_ankitts_bot"))
BOT_NAME = os.getenv("BOT_NAME", _ext_config.get("bot_name", "Pocket Anki TTS"))
PORT = int(os.getenv("PORT", "10000"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")  # Ex: https://anki-pocket-tts.onrender.com

# Banco de dados de configurações dos usuários
DB_PATH = DATA_DIR / "bot_settings.db"
