"""
Configuração do Anki-PocketTTS-Bot.
Isolamento Estrito de Segredos (Regra 1 - Zero-Leak):
Credenciais reais são carregadas estritamente de variáveis de ambiente
ou do arquivo externo /root/.config/anki-tts-bot/config.json.
Nenhum token real é exposto no repositório Git.
"""
import os
import json
import logging
from pathlib import Path

logger = logging.getLogger("anki_tts.config")

# Diretórios base
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
VOICE_PROFILES_DIR = DATA_DIR / "voice_profiles"
TEMP_DIR = BASE_DIR / "temp"
TEMP_AUDIO_DIR = TEMP_DIR
USER_SETTINGS_FILE = DATA_DIR / "user_settings.json"

# Garantir existência de pastas locais
DATA_DIR.mkdir(parents=True, exist_ok=True)
VOICE_PROFILES_DIR.mkdir(parents=True, exist_ok=True)
TEMP_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# Leitura segura de configuração externa (fora do git)
EXTERNAL_CONFIG_PATH = Path("/root/.config/anki-tts-bot/config.json")

def load_external_config() -> dict:
    if EXTERNAL_CONFIG_PATH.exists():
        try:
            with open(EXTERNAL_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Aviso: Falha ao ler config externa em %s: %s", EXTERNAL_CONFIG_PATH, e)
    return {}

_ext_cfg = load_external_config()

# Credenciais e URLs (Precedência: Env Var > Config Externa > Placeholder Seguro)
BOT_TOKEN = os.getenv("BOT_TOKEN") or _ext_cfg.get("bot_token", "")
BOT_USERNAME = os.getenv("BOT_USERNAME") or _ext_cfg.get("bot_username", "dankkss_ankitts_bot")
BOT_NAME = os.getenv("BOT_NAME") or _ext_cfg.get("bot_name", "Pocket Anki TTS")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").rstrip("/")
PORT = int(os.getenv("PORT", "10000"))
SECRET_TOKEN = os.getenv("SECRET_TOKEN", "anki_tts_secret_token_render")

# Parâmetros padrão de síntese
DEFAULT_ENGINE = os.getenv("DEFAULT_ENGINE", "edge-tts")
DEFAULT_EDGE_VOICE = os.getenv("DEFAULT_EDGE_VOICE", "pt-BR-FranciscaNeural")
DEFAULT_SPEED = os.getenv("DEFAULT_SPEED", "1.0x")
DB_PATH = DATA_DIR / "bot_settings.db"
