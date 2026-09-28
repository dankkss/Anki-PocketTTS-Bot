"""
Motor de Síntese de Voz (TTS) com suporte a Clonagem (Pocket TTS) e Vozes de Estúdio (Edge-TTS).
Otimizado para baixo consumo de memória e execução em CPU.
"""

import os
import gc
import shutil
import asyncio
import subprocess
from pathlib import Path
from typing import Optional, Dict, List

from config import VOICE_PROFILES_DIR, TEMP_DIR

# Catálogo de vozes nativas de estúdio recomendadas para o Anki
NATIVE_VOICES = {
    "en_us_aria": {"name": "Aria (EUA - Didática/Clara)", "voice": "en-US-AriaNeural", "lang": "Inglês (EUA)"},
    "en_us_jenny": {"name": "Jenny (EUA - Conversação)", "voice": "en-US-JennyNeural", "lang": "Inglês (EUA)"},
    "en_us_guy": {"name": "Guy (EUA - Masculina)", "voice": "en-US-GuyNeural", "lang": "Inglês (EUA)"},
    "en_gb_sonia": {"name": "Sonia (Reino Unido)", "voice": "en-GB-SoniaNeural", "lang": "Inglês (UK)"},
    "en_gb_ryan": {"name": "Ryan (Reino Unido - Masc)", "voice": "en-GB-RyanNeural", "lang": "Inglês (UK)"},
    "es_es_elvira": {"name": "Elvira (Espanha)", "voice": "es-ES-ElviraNeural", "lang": "Espanhol"},
    "fr_fr_denise": {"name": "Denise (França)", "voice": "fr-FR-DeniseNeural", "lang": "Francês"},
    "de_de_katja": {"name": "Katja (Alemanha)", "voice": "de-DE-KatjaNeural", "lang": "Alemão"},
    "it_it_elsa": {"name": "Elsa (Itália)", "voice": "it-IT-ElsaNeural", "lang": "Italiano"},
    "ja_jp_nanami": {"name": "Nanami (Japão)", "voice": "ja-JP-NanamiNeural", "lang": "Japonês"},
    "pt_br_francisca": {"name": "Francisca (Brasil)", "voice": "pt-BR-FranciscaNeural", "lang": "Português (BR)"},
    "pt_br_antonio": {"name": "Antônio (Brasil - Masc)", "voice": "pt-BR-AntonioNeural", "lang": "Português (BR)"},
}

# Tenta carregar Pocket TTS sob demanda para economizar RAM inicial
_pocket_model = None


def get_pocket_model():
    """Carrega o modelo Pocket TTS em modo preguiçoso (lazy loading) na CPU."""
    global _pocket_model
    if _pocket_model is None:
        try:
            import torch
            from pocket_tts import TTSModel
            # Força modo inferência e CPU para economizar memória
            torch.set_grad_enabled(False)
            _pocket_model = TTSModel.load_model()
        except ImportError:
            _pocket_model = None
        except Exception as e:
            print(f"[PocketTTS] Erro ao carregar modelo: {e}")
            _pocket_model = None
    return _pocket_model


def convert_audio_to_wav(input_path: Path, output_wav: Path) -> bool:
    """Converte qualquer formato de áudio (OGG/MP3/M4A) para WAV 16kHz mono via ffmpeg."""
    try:
        cmd = [
            "ffmpeg", "-y", "-i", str(input_path),
            "-ar", "16000", "-ac", "1",
            str(output_wav)
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return output_wav.exists()
    except Exception as e:
        print(f"[FFmpeg] Erro na conversão para WAV: {e}")
        return False


def convert_wav_to_mp3(input_wav: Path, output_mp3: Path) -> bool:
    """Converte WAV para MP3 leve com qualidade 192k."""
    try:
        cmd = [
            "ffmpeg", "-y", "-i", str(input_wav),
            "-codec:a", "libmp3lame", "-b:a", "192k",
            str(output_mp3)
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return output_mp3.exists()
    except Exception as e:
        print(f"[FFmpeg] Erro na conversão para MP3: {e}")
        return False


class TTSEngine:
    """Orquestrador unificado de TTS para o Anki."""

    @staticmethod
    def list_cloned_voices() -> List[str]:
        """Retorna a lista de nomes de perfis de voz clonados (.safetensors)."""
        if not VOICE_PROFILES_DIR.exists():
            return []
        return sorted([f.stem for f in VOICE_PROFILES_DIR.glob("*.safetensors")])

    @staticmethod
    def list_native_voices() -> Dict[str, Dict]:
        """Retorna o catálogo de vozes de estúdio pré-configuradas."""
        return NATIVE_VOICES

    @staticmethod
    async def clone_voice_from_audio(input_audio_path: Path, voice_name: str) -> Optional[Path]:
        """
        Extrai o perfil de voz (.safetensors) a partir de uma amostra de áudio (5-10s).
        Salva em data/voice_profiles/<voice_name>.safetensors.
        """
        model = get_pocket_model()
        if model is None:
            raise RuntimeError("Pocket TTS não está instalado ou disponível no ambiente.")

        safe_name = "".join(c for c in voice_name.lower() if c.isalnum() or c in ("_", "-"))
        if not safe_name:
            safe_name = "voz_clonada"

        wav_path = TEMP_DIR / f"{safe_name}_ref.wav"
        out_safetensors = VOICE_PROFILES_DIR / f"{safe_name}.safetensors"

        try:
            # 1. Converte áudio de entrada para WAV 16kHz
            if not convert_audio_to_wav(input_audio_path, wav_path):
                raise RuntimeError("Falha ao converter áudio de referência para WAV 16kHz.")

            # 2. Executa a extração em thread separada para não travar o loop assíncrono
            def _extract():
                from pocket_tts import export_model_state
                state = model.get_state_for_audio_prompt(str(wav_path))
                export_model_state(state, str(out_safetensors))

            await asyncio.to_thread(_extract)
            return out_safetensors if out_safetensors.exists() else None

        finally:
            if wav_path.exists():
                wav_path.unlink(missing_ok=True)
            gc.collect()

    @staticmethod
    async def generate_cloned(text: str, voice_name: str, output_path: Path) -> bool:
        """Gera áudio usando um perfil de voz clonado do Pocket TTS."""
        model = get_pocket_model()
        if model is None:
            raise RuntimeError("Pocket TTS não está disponível no servidor.")

        safetensors_path = VOICE_PROFILES_DIR / f"{voice_name}.safetensors"
        if not safetensors_path.exists():
            raise FileNotFoundError(f"Perfil de voz '{voice_name}' não encontrado.")

        temp_wav = TEMP_DIR / f"{output_path.stem}_temp.wav"

        try:
            def _generate():
                import scipy.io.wavfile
                voice_state = model.get_state_for_audio_prompt(str(safetensors_path))
                audio = model.generate_audio(voice_state, text)
                scipy.io.wavfile.write(str(temp_wav), model.sample_rate, audio.numpy())

            await asyncio.to_thread(_generate)

            if temp_wav.exists():
                # Converte para MP3 final
                ok = convert_wav_to_mp3(temp_wav, output_path)
                return ok
            return False

        finally:
            if temp_wav.exists():
                temp_wav.unlink(missing_ok=True)
            gc.collect()

    @staticmethod
    async def generate_native(text: str, voice_key: str, speed_multiplier: float, output_path: Path) -> bool:
        """Gera áudio instantâneo com Edge-TTS da Microsoft."""
        try:
            import edge_tts
        except ImportError:
            raise RuntimeError("edge-tts não está instalado no ambiente.")

        voice_info = NATIVE_VOICES.get(voice_key, NATIVE_VOICES["en_us_aria"])
        voice_id = voice_info["voice"]

        # Calcula o rate string (ex: -20%, +0%, +20%)
        rate_percent = int(round((speed_multiplier - 1.0) * 100))
        rate_str = f"{rate_percent:+d}%"

        temp_audio = TEMP_DIR / f"{output_path.stem}_native.mp3"

        communicate = edge_tts.Communicate(text, voice_id, rate=rate_str)
        await communicate.save(str(temp_audio))

        if temp_audio.exists():
            shutil.move(str(temp_audio), str(output_path))
            return True
        return False

    @staticmethod
    async def synthesize(text: str, mode: str, voice: str, speed: float, output_path: Path) -> bool:
        """Ponto de entrada unificado para síntese."""
        if mode == "cloned":
            return await TTSEngine.generate_cloned(text, voice, output_path)
        else:
            return await TTSEngine.generate_native(text, voice, speed, output_path)
