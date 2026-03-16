import os
import json
import logging
import redis
import requests
import threading
import time
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

try:
    r = redis.from_url(REDIS_URL, decode_responses=True)
    r.ping()
    logger.info("✅ REDIS: Conexión OK")
except Exception as e:
    logger.error(f"❌ REDIS: Error: {e}")

def send_telegram_message(text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"❌ Error enviando a Telegram: {e}")
        return None

@app.get("/", response_class=HTMLResponse)
async def home():
    return "<h1>Machine Status: ACTIVE 🚀</h1>"

@app.get("/approve")
async def approve_reel(reel_id: str, action: str):
    reel_data_raw = r.get(f"reel:{reel_id}")
    if not reel_data_raw:
        return HTMLResponse("<h1>Error ❌</h1><p>Reel no encontrado.</p>")
    reel_data = json.loads(reel_data_raw)
    if action == "approve":
        send_telegram_message(f"✅ **APROBADO**\n\n{reel_data.get('body')}")
        return HTMLResponse("<h1>Aprobado ✅</h1>")
    return HTMLResponse("<h1>Rechazado</h1>")

def redis_worker():
    logger.info("🏃‍♂️ Worker escuchando...")
    # Pequeña pausa para dejar que el generador cree el primer reel del reinicio
    time.sleep(10) 
    send_telegram_message("🤖 **Bot listo y vigilando la cola...**")

    while True:
        try:
            # 🔍 RADAR: Ver si hay algo en la cola sin sacarlo todavía
            queue_size = r.llen("ready_for_approval")
            if queue_size > 0:
                logger.info(f"📦 Hay {queue_size} reels esperando en la cola.")
            
            # Sacar el elemento
            item = r.blpop("ready_for_approval", timeout=2)
            if item:
                _, message = item
                data = json.loads(message)
                reel_id = data.get("reel_id", "unknown")
                body = data.get("body", "Sin guion")
                
                # Guardar para el botón de aprobación
                r.set(f"reel:{reel_id}", json.dumps(data), ex=86400)

                keyboard = {
                    "inline_keyboard": [[
                        {"text": "✅ Aprobar", "url": f"https://reel-machine.onrender.com/approve?reel_id={reel_id}&action=approve"},
                        {"text": "❌ Rechazar", "url": f"https://reel-machine.onrender.com/approve?reel_id={reel_id}&action=reject"}
                    ]]
                }
                send_telegram_message(f"🎬 **Nuevo Reel:** `{reel_id}`\n\n{body}", reply_markup=keyboard)
                logger.info(f"✅ Reel {reel_id} enviado a Telegram")
        except Exception as e:
            logger.error(f"❌ Error en Worker: {e}")
            time.sleep(5)

threading.Thread(target=redis_worker, daemon=True).start()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))