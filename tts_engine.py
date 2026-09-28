"""
Motor de Síntese de Voz (Dual Engine) para Cartões Anki:
1. Edge-TTS (Microsoft): Vozes de estúdio ultrarrápidas (<1s), 100+ idiomas, controle de velocidade.
2. Pocket TTS (Kyutai): Clonagem de voz zero-shot a partir de áudios de 5-10s (.safetensors).
"""
import os
import re
import gc
import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Optional, Tuple, List, Dict

import edge_tts
from config import VOICE_PROFILES_DIR, TEMP_AUDIO_DIR

logger = logging.getLogger("anki_tts.engine")

# Vozes de estúdio recomendadas para estudo de idiomas e cartões Anki
EDGE_VOICES: Dict[str, Dict[str, str]] = {
    "en-US-AriaNeural": {"lang": "Inglês (EUA)", "name": "Aria (EUA - Didática/Clara)"},
    "en-US-JennyNeural": {"lang": "Inglês (EUA)", "name": "Jenny (EUA - Conversação)"},
    "en-US-GuyNeural": {"lang": "Inglês (EUA)", "name": "Guy (EUA - Masculina)"},
    "en-GB-SoniaNeural": {"lang": "Inglês (Reino Unido)", "name": "Sonia (Reino Unido)"},
    "en-GB-RyanNeural": {"lang": "Inglês (Reino Unido)", "name": "Ryan (Reino Unido - Masc)"},
    "es-ES-ElviraNeural": {"lang": "Espanhol (Espanha)", "name": "Elvira (Espanha)"},
    "es-MX-DaliaNeural": {"lang": "Espanhol (México)", "name": "Dalia (México)"},
    "fr-FR-DeniseNeural": {"lang": "Francês (França)", "name": "Denise (França)"},
    "de-DE-KatjaNeural": {"lang": "Alemão (Alemanha)", "name": "Katja (Alemanha)"},
    "it-IT-ElsaNeural": {"lang": "Italiano (Itália)", "name": "Elsa (Itália)"},
    "ja-JP-NanamiNeural": {"lang": "Japonês (Japão)", "name": "Nanami (Japão)"},
    "pt-BR-FranciscaNeural": {"lang": "Português (Brasil)", "name": "Francisca (Brasil)"},
    "pt-BR-AntonioNeural": {"lang": "Português (Brasil)", "name": "Antônio (Brasil - Masc)"},
}

# Mapeamento de velocidades para Edge-TTS
SPEED_RATES = {
    "0.8x": "-20%",
    "1.0x": "+0%",
    "1.2x": "+20%"
}

# Inicialização resiliente do Pocket TTS
try:
    from pocket_tts import TTSModel, export_model_state
    POCKET_AVAILABLE = True
except ImportError:
    POCKET_AVAILABLE = False
    TTSModel = None
    export_model_state = None

_pocket_model_instance = None

def get_pocket_model():
    """Retorna o modelo Pocket TTS em modo singleton."""
    global _pocket_model_instance
    if not POCKET_AVAILABLE:
        return None
    if _pocket_model_instance is None:
        try:
            hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_HUB_TOKEN")
            if hf_token:
                os.environ["HF_TOKEN"] = hf_token
                os.environ["HUGGINGFACE_HUB_TOKEN"] = hf_token
                try:
                    import huggingface_hub
                    huggingface_hub.login(token=hf_token, add_to_git_credential=False)
                except Exception:
                    pass
            logger.info("Carregando modelo Pocket TTS...")
            _pocket_model_instance = TTSModel.load_model()
            logger.info("Modelo Pocket TTS carregado com sucesso.")
        except Exception as e:
            logger.error("Erro ao carregar modelo Pocket TTS: %s", e)
            return None
    return _pocket_model_instance

def sanitize_slug(text: str) -> str:
    """Gera um slug amigável para o nome do arquivo MP3."""
    clean = re.sub(r"[^\w\s-]", "", text.strip().lower())
    slug = re.sub(r"[-\s]+", "_", clean)[:30]
    return slug or "anki_audio"

async def synthesize_edge_tts(text: str, voice: str, speed: str, output_path: str) -> bool:
    """Gera áudio .mp3 via Edge-TTS."""
    try:
        rate = SPEED_RATES.get(speed, "+0%")
        selected_voice = voice if voice in EDGE_VOICES else "en-US-AriaNeural"
        communicate = edge_tts.Communicate(text=text, voice=selected_voice, rate=rate)
        await communicate.save(output_path)
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception as e:
        logger.error("Erro no Edge-TTS: %s", e)
        return False

def _process_pocket_cloning(clean_wav_path: str, safetensors_path: str) -> bool:
    """Extrai o voice_state e exporta para .safetensors (síncrono/CPU)."""
    model = get_pocket_model()
    if not model:
        raise RuntimeError("Pocket TTS não está disponível ou falhou ao inicializar.")
    voice_state = model.get_state_for_audio_prompt(clean_wav_path)
    export_model_state(voice_state, safetensors_path)
    return os.path.exists(safetensors_path)

async def clone_pocket_voice(audio_input_path: str, profile_name: str) -> Tuple[bool, str]:
    """
    Converte áudio recebido para WAV 16kHz mono e salva o perfil de voz (.safetensors).
    """
    if not POCKET_AVAILABLE:
        return False, "O motor de clonagem neural (Pocket TTS) foi delegado para o Google Colab (12 GB RAM) para evitar estouro de memória no Render."

    clean_name = sanitize_slug(profile_name)
    target_safetensors = VOICE_PROFILES_DIR / f"{clean_name}.safetensors"
    clean_wav = TEMP_AUDIO_DIR / f"prep_{clean_name}.wav"

    try:
        # Converter para WAV 16kHz Mono usando ffmpeg
        cmd = [
            "ffmpeg", "-y", "-i", audio_input_path,
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
            str(clean_wav)
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error("Falha ao converter áudio via ffmpeg: %s", stderr.decode())
            return False, "Erro ao converter formato do áudio de entrada."

        # Extrair e salvar perfil via threadpool
        success = await asyncio.to_thread(_process_pocket_cloning, str(clean_wav), str(target_safetensors))
        if success:
            return True, clean_name
        return False, "Falha ao gerar o arquivo de estado da voz clonada."
    except Exception as e:
        logger.error("Erro na clonagem Pocket TTS: %s", e)
        return False, f"Falha na clonagem: {str(e)}"
    finally:
        if clean_wav.exists():
            try:
                clean_wav.unlink()
            except Exception:
                pass
        gc.collect()

def _process_pocket_synthesis(safetensors_path: str, text: str, temp_wav_path: str) -> bool:
    """Sintetiza voz clonada e grava WAV temporário (síncrono/CPU)."""
    import scipy.io.wavfile
    model = get_pocket_model()
    if not model:
        raise RuntimeError("Pocket TTS não está disponível.")
    voice_state = model.get_state_for_audio_prompt(safetensors_path)
    audio = model.generate_audio(voice_state, text)
    scipy.io.wavfile.write(temp_wav_path, model.sample_rate, audio.numpy())
    return os.path.exists(temp_wav_path)

async def synthesize_pocket_tts(text: str, profile_name: str, output_mp3_path: str) -> bool:
    """Gera áudio .mp3 a partir de perfil clonado Pocket TTS."""
    safetensors_path = VOICE_PROFILES_DIR / f"{profile_name}.safetensors"
    if not safetensors_path.exists():
        logger.warning("Perfil %s não encontrado em %s", profile_name, safetensors_path)
        return False

    temp_wav = TEMP_AUDIO_DIR / f"temp_gen_{profile_name}.wav"
    try:
        # Gera WAV
        await asyncio.to_thread(_process_pocket_synthesis, str(safetensors_path), text, str(temp_wav))
        
        # Converte WAV para MP3 192kbps para o Anki
        cmd = [
            "ffmpeg", "-y", "-i", str(temp_wav),
            "-codec:a", "libmp3lame", "-b:a", "192k",
            output_mp3_path
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        return os.path.exists(output_mp3_path) and os.path.getsize(output_mp3_path) > 0
    except Exception as e:
        logger.error("Erro na síntese Pocket TTS: %s", e)
        return False
    finally:
        if temp_wav.exists():
            try:
                temp_wav.unlink()
            except Exception:
                pass
        gc.collect()

def list_cloned_voices() -> List[str]:
    """Lista todos os perfis clonados disponíveis no disco."""
    return [p.stem for p in VOICE_PROFILES_DIR.glob("*.safetensors")]
