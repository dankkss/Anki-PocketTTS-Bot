"""
Gerenciador SQLite leve de preferências de usuários para o Anki TTS Bot.
"""

import sqlite3
from typing import Dict, Any
from config import DB_PATH


def init_db():
    """Inicializa as tabelas do banco de dados SQLite."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            mode TEXT DEFAULT 'native',
            active_voice TEXT DEFAULT 'en_us_aria',
            speed REAL DEFAULT 1.0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def get_user_settings(user_id: int) -> Dict[str, Any]:
    """Retorna as configurações do usuário ou os valores padrão."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT mode, active_voice, speed FROM user_settings WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if row:
        return {"mode": row[0], "active_voice": row[1], "speed": float(row[2])}

    # Valores padrão iniciais
    default_settings = {"mode": "native", "active_voice": "en_us_aria", "speed": 1.0}
    set_user_settings(user_id, **default_settings)
    return default_settings


def set_user_settings(user_id: int, mode: str = None, active_voice: str = None, speed: float = None):
    """Atualiza as configurações do usuário."""
    current = get_user_settings(user_id) if mode is None or active_voice is None or speed is None else {}
    final_mode = mode if mode is not None else current.get("mode", "native")
    final_voice = active_voice if active_voice is not None else current.get("active_voice", "en_us_aria")
    final_speed = speed if speed is not None else current.get("speed", 1.0)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_settings (user_id, mode, active_voice, speed, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id) DO UPDATE SET
            mode = excluded.mode,
            active_voice = excluded.active_voice,
            speed = excluded.speed,
            updated_at = CURRENT_TIMESTAMP
    """, (user_id, final_mode, final_voice, final_speed))
    conn.commit()
    conn.close()


# Inicializa o banco no import
init_db()
