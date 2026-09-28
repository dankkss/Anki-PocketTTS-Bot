"""
Servidor Web FastAPI para Anki-PocketTTS-Bot (Compatível com Render Web Service).
Fornece endpoints de monitoramento (/health, /ping) e receptor assíncrono de webhook Telegram.
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Header, HTTPException, Query
from fastapi.responses import JSONResponse
import httpx

from config import BOT_TOKEN, WEBHOOK_URL, PORT, SECRET_TOKEN, DEFAULT_ENGINE
from bot_handlers import handle_telegram_update
from tts_engine import POCKET_AVAILABLE, list_cloned_voices

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("anki_tts.app")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Pocket Anki TTS Bot iniciando na porta %s...", PORT)
    logger.info("Motor padrão: %s | Pocket TTS disponível: %s", DEFAULT_ENGINE, POCKET_AVAILABLE)
    yield
    logger.info("Encerrando Pocket Anki TTS Bot...")

app = FastAPI(
    title="Pocket Anki TTS Bot",
    description="Microserviço de geração de áudios para cartões do Anki via Telegram",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/")
async def root():
    return {
        "service": "Pocket Anki TTS Bot",
        "status": "online",
        "engines": {
            "edge_tts": "enabled",
            "pocket_tts": "available" if POCKET_AVAILABLE else "offline"
        },
        "cloned_profiles_count": len(list_cloned_voices()),
        "endpoints": {
            "health": "/health",
            "ping": "/ping",
            "webhook": "/webhook",
            "set_webhook": "/set_webhook"
        }
    }

@app.get("/health")
async def health():
    return {"status": "ok", "service": "anki-pocket-tts-bot"}

@app.get("/ping")
async def ping():
    return {"status": "pong"}

@app.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(None)
):
    # Validação do token de segurança do webhook (se configurado)
    if SECRET_TOKEN and x_telegram_bot_api_secret_token:
        if x_telegram_bot_api_secret_token != SECRET_TOKEN:
            logger.warning("Tentativa de webhook com secret token inválido!")
            raise HTTPException(status_code=403, detail="Forbidden")

    try:
        update_data = await request.json()
    except Exception as e:
        logger.error("Payload JSON inválido no webhook: %s", e)
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Processamento assíncrono da atualização
    try:
        await handle_telegram_update(update_data)
    except Exception as e:
        logger.error("Erro no processamento da atualização: %s", e)

    return {"ok": True}

@app.post("/set_webhook")
async def set_webhook(url: str = Query(None)):
    target_url = url or WEBHOOK_URL
    if not target_url:
        raise HTTPException(
            status_code=400,
            detail="Informe a URL do webhook (ex: https://anki-pocket-tts-bot.onrender.com) via parâmetro ?url= ou configure WEBHOOK_URL."
        )

    endpoint = f"{target_url.rstrip('/')}/webhook"
    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
    
    payload = {
        "url": endpoint,
        "allowed_updates": ["message", "callback_query"],
        "drop_pending_updates": True
    }
    if SECRET_TOKEN:
        payload["secret_token"] = SECRET_TOKEN

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(api_url, json=payload)
        data = resp.json()

    return {
        "status": "success" if data.get("ok") else "error",
        "configured_url": endpoint,
        "telegram_response": data
    }

@app.get("/webhook_info")
async def get_webhook_info():
    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(api_url)
        return resp.json()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=PORT, reload=False)
