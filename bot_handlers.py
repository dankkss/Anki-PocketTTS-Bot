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
async def handle_start(chat_id: int):
    msg = (
        "<b>Pocket Anki TTS Bot</b>\n\n"
        "Gere arquivos .mp3 limpos e rápidos para os seus cartões do Anki.\n\n"
        "<b>Como usar:</b>\n"
        "1. <b>Texto para Áudio:</b> Envie qualquer palavra ou frase e receba o .mp3 imediatamente.\n"
        "2. <b>Clonagem de Voz:</b>\n"
        "• Grave ou envie um áudio (5 a 10s de fala clara).\n"
        "• Em seguida, responda ao áudio com: <code>/clonar nome_da_voz</code> (ou simplesmente envie o comando logo após o áudio).\n\n"
        "<b>Comandos:</b>\n"
        "• /vozes — Alternar entre vozes de estúdio (Edge-TTS) e vozes clonadas (Pocket TTS)\n"
        "• /velocidade — Ajustar velocidade da fala (0.8x, 1.0x, 1.2x)\n"
        "• /status — Exibir configurações atuais do bot\n"
        "• /ajuda — Ver estas instruções novamente"
    )
    await tg_send_message(chat_id, msg)

async def handle_status(chat_id: int):
    cfg = get_user_config(chat_id)
    cloned = list_cloned_voices()
    engine = cfg["engine"]
    
    if engine == "edge-tts":
        voice_info = EDGE_VOICES.get(cfg["edge_voice"], {}).get("name", cfg["edge_voice"])
        active_desc = f"Edge-TTS ({voice_info})"
    else:
        active_desc = f"Pocket TTS (Perfil: {cfg.get('pocket_voice') or 'Nenhum'})"

    msg = (
        "<b>Status e Configurações Atuais:</b>\n\n"
        f"• <b>Motor Ativo:</b> <code>{active_desc}</code>\n"
        f"• <b>Velocidade:</b> <code>{cfg['speed']}</code>\n"
        f"• <b>Perfis Clonados:</b> <code>{len(cloned)} salvos</code>\n"
        f"• <b>Pocket TTS:</b> <code>{'Ativo' if POCKET_AVAILABLE else 'Indisponível no host'}</code>\n\n"
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
        [{"text": "🎙️ Vozes de Estúdio (Edge-TTS)", "callback_data": "menu:edge"}]
    ]
    if POCKET_AVAILABLE:
        buttons.append([{"text": "🧬 Vozes Clonadas (Pocket TTS)", "callback_data": "menu:pocket"}])
        
    keyboard = {"inline_keyboard": buttons}
    await tg_send_message(chat_id, "Selecione o catálogo de vozes:", reply_markup=keyboard)

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

    if callback_data.startswith("vedge:"):
        voice_id = callback_data.split(":", 1)[1]
        update_user_config(chat_id, engine="edge-tts", edge_voice=voice_id)
        name = EDGE_VOICES.get(voice_id, {}).get("name", voice_id)
        await tg_send_message(chat_id, f"Voz ativada: <b>{name}</b> (Edge-TTS)")
        return

    if callback_data == "menu:pocket":
        cloned = list_cloned_voices()
        if not cloned:
            await tg_send_message(
                chat_id,
                "Nenhum perfil de voz clonado ainda.\n\n"
                "Para clonar, envie um áudio com a legenda:\n<code>/clonar meu_nome</code>"
            )
            return
        buttons = []
        for profile in cloned:
            buttons.append([{"text": f"🧬 {profile}", "callback_data": f"vpocket:{profile}"}])
        keyboard = {"inline_keyboard": buttons}
        await tg_send_message(chat_id, "Escolha a voz clonada (Pocket TTS):", reply_markup=keyboard)
        return

    if callback_data.startswith("vpocket:"):
        profile = callback_data.split(":", 1)[1]
        update_user_config(chat_id, engine="pocket-tts", pocket_voice=profile)
        await tg_send_message(chat_id, f"Perfil clonado ativado: <b>{profile}</b> (Pocket TTS)")
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
    if not POCKET_AVAILABLE:
        await tg_send_message(chat_id, "O motor Pocket TTS não está habilitado neste servidor.")
        return

    clean_profile = sanitize_slug(profile_name)
    if not clean_profile:
        await tg_send_message(chat_id, "Nome de perfil inválido. Exemplo: <code>/clonar professor</code>")
        return

    await tg_send_message(chat_id, f"Processando clonagem de voz para o perfil: <b>{clean_profile}</b>...")
    temp_input = str(TEMP_AUDIO_DIR / f"raw_clone_{chat_id}_{int(time.time())}.ogg")

    downloaded = await tg_download_file(file_id, temp_input)
    if not downloaded:
        await tg_send_message(chat_id, "Falha ao baixar o áudio do Telegram. Envie novamente.")
        return

    ok, result = await clone_pocket_voice(temp_input, clean_profile)
    if os.path.exists(temp_input):
        try:
            os.unlink(temp_input)
        except Exception:
            pass

    if ok:
        update_user_config(chat_id, engine="pocket-tts", pocket_voice=result)
        await tg_send_message(
            chat_id,
            f"✅ <b>Voz clonada com sucesso!</b>\n\n"
            f"Perfil <code>{result}</code> salvo e ativado como sua voz atual no Pocket TTS.\n"
            f"Envie qualquer texto agora para testar sua voz no Anki!"
        )
    else:
        await tg_send_message(chat_id, f"Falha na clonagem: {result}")

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
                parts = text.strip().split()
                if len(parts) < 2:
                    await tg_send_message(
                        chat_id,
                        "Por favor, especifique o nome para a voz clonada.\n"
                        "<b>Exemplo:</b> <code>/clonar professor</code>"
                    )
                    return

                profile_name = parts[1]
                target_file_id = None

                # 1. Verifica se é uma resposta (reply) a uma mensagem de voz ou áudio
                reply = message.get("reply_to_message")
                if reply:
                    reply_audio = reply.get("voice") or reply.get("audio") or reply.get("document")
                    if reply_audio:
                        target_file_id = reply_audio.get("file_id")

                # 2. Se não foi resposta direta, verifica o último áudio enviado recentemente pelo usuário
                if not target_file_id and chat_id in _last_audio_cache:
                    cached = _last_audio_cache[chat_id]
                    # Aceita áudio enviado nos últimos 20 minutos (1200s)
                    if time.time() - cached.get("timestamp", 0) < 1200:
                        target_file_id = cached.get("file_id")

                if target_file_id:
                    await process_audio_cloning(chat_id, target_file_id, profile_name)
                else:
                    await tg_send_message(
                        chat_id,
                        "⚠️ <b>Nenhum áudio encontrado para clonar.</b>\n\n"
                        "<b>Como fazer:</b>\n"
                        "1. Grave ou envie um áudio de 5 a 10s no chat.\n"
                        f"2. Em seguida, responda ao áudio com: <code>/clonar {profile_name}</code>\n"
                        f"<i>(ou envie <code>/clonar {profile_name}</code> logo após gravar).</i>"
                    )
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
            # Salva no cache recente para permitir comando /clonar logo em seguida
            _last_audio_cache[chat_id] = {"file_id": file_id, "timestamp": time.time()}

            # Verificar se veio com legenda solicitando clonagem
            if caption and (caption.startswith("/clonar") or caption.startswith("/clone")):
                parts = caption.strip().split()
                if len(parts) >= 2:
                    profile_name = parts[1]
                    await process_audio_cloning(chat_id, file_id, profile_name)
                    return
                else:
                    await tg_send_message(chat_id, "Por favor, especifique o nome. Exemplo: <code>/clonar professor</code>")
                    return
            else:
                await tg_send_message(
                    chat_id,
                    "🎙️ <b>Áudio de voz recebido!</b>\n\n"
                    "Para clonar esta voz para seus cartões Anki:\n"
                    "• <b>Responda a este áudio</b> com: <code>/clonar nome_da_voz</code>\n"
                    "• <i>Ou apenas envie <code>/clonar nome_da_voz</code> logo em seguida.</i>\n\n"
                    "<i>Exemplo: <code>/clonar professor</code></i>"
                )
    except Exception as e:
        logger.error("Erro ao processar atualização: %s", e)
