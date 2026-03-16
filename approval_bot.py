import os
import json
import logging
import redis
import requests
import threading
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

# 1. CONFIGURACIÓN DE LOGS
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# 2. VARIABLES DE ENTORNO
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# 3. CONEXIÓN A REDIS
try:
    r = redis.from_url(REDIS_URL, decode_responses=True)
    logger.info("✅ Conectado a Redis con éxito")
except Exception as e:
    logger.error(f"❌ Error conectando a Redis: {e}")

def send_telegram_message(text, reply_markup=None):
    """Envía un mensaje a Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    
    try:
        response = requests.post(url, json=payload)
        return response.json()
    except Exception as e:
        logger.error(f"❌ Error enviando a Telegram: {e}")
        return None

# 4. ENDPOINTS DE LA API
@app.get("/", response_class=HTMLResponse)
async def home():
    return "<h1>Approval Bot is Online 🚀</h1><p>Escuchando la cola de Redis...</p>"

@app.get("/approve")
async def approve_reel(reel_id: str, action: str):
    """Maneja la aprobación/rechazo desde los botones de Telegram"""
    reel_data_raw = r.get(f"reel:{reel_id}")
    if not reel_data_raw:
        return HTMLResponse("<h1>Error ❌</h1><p>Reel no encontrado en Redis.</p>")

    reel_data = json.loads(reel_data_raw)
    body_text = reel_data.get('body', 'Sin guion disponible')

    if action == "approve":
        confirmation_text = (
            "✅ **¡REEL APROBADO!**\n\n"
            "📝 **COPIA ESTE GUION:**\n"
            "----------------------------------\n"
            f"{body_text}\n"
            "----------------------------------\n\n"
            "🚀 *Listo para publicar.*"
        )
        send_telegram_message(confirmation_text)
        r.set(f"status:{reel_id}", "APPROVED")
        return HTMLResponse("<h1>Aprobado ✅</h1><p>Mensaje enviado a Telegram.</p>")

    elif action == "reject":
        r.set(f"status:{reel_id}", "REJECTED")
        send_telegram_message(f"❌ Reel `{reel_id}` rechazado.")
        return HTMLResponse("<h1>Rechazado ❌</h1>")

# 5. WORKER DE REDIS (EL "MOTOR" QUE MANDA A TELEGRAM)
def redis_worker():
    """Vigila la cola 'ready_for_approval' constantemente"""
    logger.info("🏃‍♂️ Worker de Redis iniciado y escuchando...")
    # La URL base para los botones
    BASE_URL = "https://reel-machine.onrender.com"
    
    while True:
        try:
            # Espera hasta que haya algo en la cola 'ready_for_approval'
            _, message = r.blpop("ready_for_approval")
            data = json.loads(message)
            reel_id = data.get("reel_id", "unknown")
            body = data.get("body", "Sin contenido")

            # Guardamos el reel en Redis para recuperarlo luego al aprobar
            r.set(f"reel:{reel_id}", json.dumps(data))

            # Creamos los botones
            keyboard = {
                "inline_keyboard": [[
                    {"text": "✅ Aprobar y Copiar", "url": f"{BASE_URL}/approve?reel_id={reel_id}&action=approve"},
                    {"text": "❌ Rechazar", "url": f"{BASE_URL}/approve?reel_id={reel_id}&action=reject"}
                ]]
            }

            msg = f"🎬 **¡Nuevo Reel Listo!**\n\n📎 **ID:** `{reel_id}`\n\n📝 **Guion:**\n{body}"
            send_telegram_message(msg, reply_markup=keyboard)
            logger.info(f"📩 Reel {reel_id} enviado a Telegram")

        except Exception as e:
            logger.error(f"❌ Error en redis_worker: {e}")

# 6. ARRANCAR EL WORKER EN UN HILO SEPARADO
worker_thread = threading.Thread(target=redis_worker, daemon=True)
worker_thread.start()

if __name__ == "__main__":
    import uvicorn
    # Usamos el puerto que Render asigne o 10000 por defecto
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)