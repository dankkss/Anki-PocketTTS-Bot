"""
Manipulador de Mensagens e Comandos do Telegram para o Anki-PocketTTS-Bot.
Gerencia preferências dos usuários, roteia comandos e entrega áudios .mp3.
"""
import os
import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional

import httpx
from config import BOT_TOKEN, USER_SETTINGS_FILE, TEMP_AUDIO_DIR, DEFAULT_ENGINE, DEFAULT_EDGE_VOICE, DEFAULT_SPEED
from tts_engine import (
    EDGE_VOICES, SPEED_RATES, POCKET_AVAILABLE,
    synthesize_edge_tts, synthesize_pocket_tts, clone_pocket_voice,
    list_cloned_voices, sanitize_slug
)

logger = logging.getLogger("anki_tts.bot")
TELEGRAM_API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
COLAB_NOTEBOOK_URL = "https://colab.research.google.com/github/dankkss/Anki-PocketTTS-Bot/blob/main/notebooks/Clonador_PocketTTS_Anki.ipynb"

# Persistência leve de configurações do usuário
def load_all_settings() -> Dict[str, Any]:
    if USER_SETTINGS_FILE.exists():
        try:
            with open(USER_SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Falha ao carregar user_settings.json: %s", e)
    return {}

def save_all_settings(settings: Dict[str, Any]):
    try:
        with open(USER_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error("Erro ao salvar user_settings.json: %s", e)

_user_settings_cache = load_all_settings()
_last_audio_cache: Dict[int, Dict[str, Any]] = {}

def get_user_config(chat_id: int) -> Dict[str, Any]:
    cid = str(chat_id)
    if cid not in _user_settings_cache:
        _user_settings_cache[cid] = {
            "engine": DEFAULT_ENGINE,
            "edge_voice": DEFAULT_EDGE_VOICE,
            "pocket_voice": "",
            "speed": DEFAULT_SPEED
        }
        save_all_settings(_user_settings_cache)
    return _user_settings_cache[cid]

def update_user_config(chat_id: int, **kwargs):
    cid = str(chat_id)
    cfg = get_user_config(chat_id)
    cfg.update(kwargs)
    _user_settings_cache[cid] = cfg
    save_all_settings(_user_settings_cache)

# Funções de Comunicação com a Telegram Bot API
async def tg_send_message(chat_id: int, text: str, reply_markup: Optional[dict] = None) -> bool:
    url = f"{TELEGRAM_API_BASE}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                # Se falhar (ex: erro de parse HTML da API do Telegram), tenta sem parse_mode
                payload.pop("parse_mode", None)
                resp = await client.post(url, json=payload)
            return resp.status_code == 200
    except Exception as e:
        logger.error("Falha ao enviar mensagem Telegram: %s", e)
        return False

async def tg_send_audio(chat_id: int, audio_path: str, caption: str, title: str, performer: str) -> bool:
    url = f"{TELEGRAM_API_BASE}/sendAudio"
    data = {
        "chat_id": str(chat_id),
        "caption": caption,
        "parse_mode": "HTML",
        "title": title,
        "performer": performer
    }
    try:
        filename = os.path.basename(audio_path)
        async with httpx.AsyncClient(timeout=60.0) as client:
            with open(audio_path, "rb") as f:
                files = {"audio": (filename, f, "audio/mpeg")}
                resp = await client.post(url, data=data, files=files)
                return resp.status_code == 200
    except Exception as e:
        logger.error("Falha ao enviar áudio Telegram: %s", e)
        return False

async def tg_send_chat_action(chat_id: int, action: str = "record_voice"):
    url = f"{TELEGRAM_API_BASE}/sendChatAction"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json={"chat_id": chat_id, "action": action})
    except Exception:
        pass

async def tg_answer_callback(callback_query_id: str, text: Optional[str] = None):
    url = f"{TELEGRAM_API_BASE}/answerCallbackQuery"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            payload = {"callback_query_id": callback_query_id}
            if text:
                payload["text"] = text
            await client.post(url, json=payload)
    except Exception as e:
        logger.error("Erro ao responder callback query: %s", e)

async def tg_download_file(file_id: str, destination_path: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=40.0) as client:
            info_res = await client.get(f"{TELEGRAM_API_BASE}/getFile?file_id={file_id}")
            if info_res.status_code != 200:
                return False
            file_path = info_res.json().get("result", {}).get("file_path")
            if not file_path:
                return False
            
            download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
            file_res = await client.get(download_url)
            if file_res.status_code == 200:
                with open(destination_path, "wb") as f:
                    f.write(file_res.content)
                return True
    except Exception as e:
        logger.error("Erro no download de arquivo Telegram: %s", e)
    return False

# Roteamento de Comandos e Ações
async def send_colab_cloning_guide(chat_id: int):
    msg = (
        "🎙️ <b>Clonagem de Voz & Geração para o Anki</b>\n\n"
        "O modelo neural de clonagem (Pocket TTS) necessita de <b>1.5 GB de RAM</b>. "
        "No plano gratuito do Render (512 MB), rodar o modelo causou alertas de memória por e-mail e reinício do contêiner.\n\n"
        "⚡ <b>Solução Oficial (Google Colab Gratuito):</b>\n"
        "Configuramos um caderno oficial no <b>Google Colab</b> (12 GB de RAM + GPU T4 Gratuita) onde não há limite de memória:\n\n"
        f"👉 <a href=\"{COLAB_NOTEBOOK_URL}\"><b>Abrir Clonador no Google Colab</b></a>\n\n"
        "<b>Recursos no Colab:</b>\n"
        "• Clona qualquer voz de áudio/microfone em ~5 segundos\n"
        "• Gera áudios individuais ou de teste\n"
        "• <b>Super Lote:</b> Cole 50 ou 100 frases e baixe todos os .mp3 compactados em .zip de uma vez para o Anki!\n\n"
        "💡 <i>Aqui no Telegram, você pode continuar gerando cartões com as mais de 400 vozes de estúdio do /vozes (Edge-TTS), que geram instantaneamente sem nenhum consumo de memória.</i>"
    )
    await tg_send_message(chat_id, msg)

async def handle_start(chat_id: int):
    msg = (
        "👋 <b>Olá! Eu sou o Pocket Anki TTS Bot.</b>\n\n"
        "Gero áudios em <code>.mp3</code> com qualidade de estúdio e tamanho leve para seus cartões do Anki.\n\n"
        "<b>Como usar:</b>\n"
        "1. <b>Texto para Áudio:</b> Envie qualquer palavra ou frase e receba o .mp3 imediatamente.\n"
        "2. <b>Vozes de Estúdio:</b> Mais de 400 vozes neurais da Microsoft (Edge-TTS) em 100+ idiomas e sotaques.\n"
        "3. <b>Clonagem de Voz:</b> Utilize nosso caderno no Google Colab para clonar sua voz e gerar lotes inteiros de cartões.\n\n"
        "<b>Comandos:</b>\n"
        "• /vozes — Escolher voz de estúdio ou abrir o clonador Colab\n"
        "• /velocidade — Ajustar velocidade da fala (0.8x, 1.0x, 1.2x)\n"
        "• /status — Exibir configurações atuais do bot\n"
        "• /clonar — Informações e link direto para o clonador no Google Colab\n"
        "• /ajuda — Ver estas instruções novamente"
    )
    await tg_send_message(chat_id, msg)

async def handle_status(chat_id: int):
    cfg = get_user_config(chat_id)
    voice_info = EDGE_VOICES.get(cfg.get("edge_voice", DEFAULT_EDGE_VOICE), {}).get("name", cfg.get("edge_voice"))

    msg = (
        "<b>Status e Configurações Atuais:</b>\n\n"
        f"• <b>Motor Ativo:</b> <code>Edge-TTS ({voice_info})</code>\n"
        f"• <b>Velocidade:</b> <code>{cfg['speed']}</code>\n"
        "• <b>Servidor Render:</b> <code>Estável (~35 MB RAM, 0% OOM)</code>\n"
        "• <b>Clonagem de Voz:</b> <code>Google Colab (12 GB RAM / GPU)</code>\n\n"
        "Use /vozes ou /velocidade para alterar."
    )
    await tg_send_message(chat_id, msg)

async def handle_velocidade_menu(chat_id: int):
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "🐢 0.8x (Lento para Anki)", "callback_data": "spd:0.8x"},
                {"text": "⚡ 1.0x (Normal)", "callback_data": "spd:1.0x"},
                {"text": "🚀 1.2x (Rápido)", "callback_data": "spd:1.2x"}
            ]
        ]
    }
    await tg_send_message(chat_id, "Selecione a velocidade desejada para a geração dos áudios:", reply_markup=keyboard)

async def handle_vozes_menu(chat_id: int):
    buttons = [
        [{"text": "🎙️ Vozes de Estúdio (Edge-TTS)", "callback_data": "menu:edge"}],
        [{"text": "🧬 Clonagem de Voz (Google Colab)", "callback_data": "menu:colab_info"}]
    ]
    keyboard = {"inline_keyboard": buttons}
    await tg_send_message(chat_id, "Selecione a opção desejada:", reply_markup=keyboard)

async def handle_callback_query(callback_data: str, callback_id: str, chat_id: int):
    await tg_answer_callback(callback_id)
    
    if callback_data.startswith("spd:"):
        speed = callback_data.split(":", 1)[1]
        update_user_config(chat_id, speed=speed)
        await tg_send_message(chat_id, f"Velocidade alterada para: <b>{speed}</b>")
        return

    if callback_data == "menu:edge":
        buttons = []
        for voice_id, meta in EDGE_VOICES.items():
            text = f"{meta['lang']}: {meta['name']}"
            buttons.append([{"text": text, "callback_data": f"vedge:{voice_id}"}])
        keyboard = {"inline_keyboard": buttons}
        await tg_send_message(chat_id, "Escolha a voz de estúdio (Edge-TTS):", reply_markup=keyboard)
        return

    if callback_data == "menu:colab_info":
        await send_colab_cloning_guide(chat_id)
        return

    if callback_data.startswith("vedge:"):
        voice_id = callback_data.split(":", 1)[1]
        update_user_config(chat_id, engine="edge-tts", edge_voice=voice_id)
        name = EDGE_VOICES.get(voice_id, {}).get("name", voice_id)
        await tg_send_message(chat_id, f"Voz ativada: <b>{name}</b> (Edge-TTS)")
        return


async def process_text_synthesis(chat_id: int, text: str):
    clean_text = text.strip()
    if len(clean_text) > 600:
        await tg_send_message(chat_id, "O texto informado é muito longo para um cartão Anki (máximo: 600 caracteres).")
        return

    await tg_send_chat_action(chat_id, "record_voice")
    cfg = get_user_config(chat_id)
    engine = cfg.get("engine", "edge-tts")
    speed = cfg.get("speed", "1.0x")
    slug = sanitize_slug(clean_text)
    timestamp = int(time.time())
    output_filename = f"anki_{slug}_{timestamp}.mp3"
    output_path = str(TEMP_AUDIO_DIR / output_filename)

    success = False
    voice_label = ""

    if engine == "pocket-tts" and POCKET_AVAILABLE:
        pocket_voice = cfg.get("pocket_voice")
        if not pocket_voice or pocket_voice not in list_cloned_voices():
            await tg_send_message(chat_id, "Perfil de voz clonado não encontrado. Revertendo para Edge-TTS.")
            engine = "edge-tts"
        else:
            voice_label = f"Pocket TTS ({pocket_voice})"
            success = await synthesize_pocket_tts(clean_text, pocket_voice, output_path)

    if engine == "edge-tts" or not success:
        edge_voice = cfg.get("edge_voice", DEFAULT_EDGE_VOICE)
        voice_label = EDGE_VOICES.get(edge_voice, {}).get("name", edge_voice)
        success = await synthesize_edge_tts(clean_text, edge_voice, speed, output_path)

    if success and os.path.exists(output_path):
        caption = (
            f"🔊 <b>Áudio para Anki</b>\n"
            f"📝 <i>\"{clean_text}\"</i>\n"
            f"⚙️ <code>{voice_label} • {speed}</code>"
        )
        title = clean_text[:40]
        performer = f"Anki TTS ({voice_label})"
        await tg_send_audio(chat_id, output_path, caption=caption, title=title, performer=performer)
        try:
            os.unlink(output_path)
        except Exception:
            pass
    else:
        await tg_send_message(chat_id, "Ocorreu um erro ao gerar o áudio. Tente novamente.")

async def process_audio_cloning(chat_id: int, file_id: str, profile_name: str):
    await send_colab_cloning_guide(chat_id)

# Ponto de entrada de atualizações do Webhook
async def handle_telegram_update(update: dict):
    try:
        # Tratar cliques em botões inline
        if "callback_query" in update:
            cb = update["callback_query"]
            chat_id = cb["from"]["id"]
            data = cb.get("data", "")
            cb_id = cb["id"]
            await handle_callback_query(data, cb_id, chat_id)
            return

        message = update.get("message")
        if not message:
            return

        chat_id = message["chat"]["id"]
        text = message.get("text", "")
        caption = message.get("caption", "")

        # Comandos de texto
        if text:
            cmd = text.strip().split()[0].lower()
            if cmd in ("/clonar", "/clone"):
                await send_colab_cloning_guide(chat_id)
                return

            elif cmd == "/start":
                await handle_start(chat_id)
            elif cmd == "/ajuda":
                await handle_start(chat_id)
            elif cmd == "/status":
                await handle_status(chat_id)
            elif cmd == "/vozes":
                await handle_vozes_menu(chat_id)
            elif cmd == "/velocidade":
                await handle_velocidade_menu(chat_id)
            else:
                # Síntese direta do texto
                await process_text_synthesis(chat_id, text)
            return

        # Mensagem de áudio ou de voz
        audio_obj = message.get("voice") or message.get("audio") or message.get("document")
        if audio_obj:
            file_id = audio_obj["file_id"]
            _last_audio_cache[chat_id] = {"file_id": file_id, "timestamp": time.time()}

            await send_colab_cloning_guide(chat_id)
            return
    except Exception as e:
        logger.error("Erro ao processar atualização: %s", e)
