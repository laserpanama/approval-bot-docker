import os
import json
import logging
import redis
import requests
import threading
import time
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

# 1. CONFIGURACIÓN DE LOGS (Más detallada)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()

# 2. VARIABLES DE ENTORNO
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# 3. CONEXIÓN A REDIS
try:
    r = redis.from_url(REDIS_URL, decode_responses=True)
    r.ping() # Prueba real de conexión
    logger.info("✅ REDIS: Conexión verificada con PING")
except Exception as e:
    logger.error(f"❌ REDIS: Error crítico de conexión: {e}")

def send_telegram_message(text, reply_markup=None):
    """Envía un mensaje a Telegram con LOGS de respuesta"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    
    try:
        logger.info(f"📤 Intentando enviar mensaje a Telegram (Chat ID: {TELEGRAM_CHAT_ID})...")
        response = requests.post(url, json=payload, timeout=10)
        result = response.json()
        if result.get("ok"):
            logger.info("✅ TELEGRAM: Mensaje enviado con éxito")
        else:
            logger.error(f"❌ TELEGRAM: Error de API: {result.get('description')}")
        return result
    except Exception as e:
        logger.error(f"❌ TELEGRAM: Fallo total en la petición: {e}")
        return None

# 4. ENDPOINTS
@app.get("/", response_class=HTMLResponse)
async def home():
    return "<h1>Approval Bot is Online 🚀</h1><p>Vigilando la cola de Redis...</p>"

@app.get("/approve")
async def approve_reel(reel_id: str, action: str):
    reel_data_raw = r.get(f"reel:{reel_id}")
    if not reel_data_raw:
        return HTMLResponse("<h1>Error ❌</h1><p>Reel no encontrado.</p>")

    reel_data = json.loads(reel_data_raw)
    body_text = reel_data.get('body', 'Sin guion')

    if action == "approve":
        msg = f"✅ **¡APROBADO!**\n\n📝 **COPIA EL GUION:**\n\n{body_text}"
        send_telegram_message(msg)
        return HTMLResponse("<h1>Aprobado ✅</h1>")
    
    return HTMLResponse("<h1>Acción procesada</h1>")

# 5. WORKER DE REDIS
def redis_worker():
    logger.info("🏃‍♂️ WORKER: Iniciando escucha de cola 'ready_for_approval'...")
    BASE_URL = "https://reel-machine.onrender.com"
    
    # PRUEBA DE ARRANQUE
    send_telegram_message("🚀 **Sistema Iniciado:** Buscando Reels pendientes...")

    while True:
        try:
            # Esperamos 5 segundos por algo en la cola
            item = r.blpop("ready_for_approval", timeout=5)
            
            if item:
                _, message = item
                logger.info(f"📥 WORKER: Reel detectado en Redis: {message[:50]}...")
                data = json.loads(message)
                reel_id = data.get("reel_id", "unknown")
                body = data.get("body", "Sin contenido")

                r.set(f"reel:{reel_id}", json.dumps(data), ex=86400) # Expira en 24h

                keyboard = {
                    "inline_keyboard": [[
                        {"text": "✅ Aprobar y Copiar", "url": f"{BASE_URL}/approve?reel_id={reel_id}&action=approve"},
                        {"text": "❌ Rechazar", "url": f"{BASE_URL}/approve?reel_id={reel_id}&action=reject"}
                    ]]
                }

                msg = f"🎬 **¡Nuevo Reel Listo!**\n\n📎 **ID:** `{reel_id}`\n\n📝 **Guion:**\n{body}"
                send_telegram_message(msg, reply_markup=keyboard)
            else:
                # Log silencioso cada 5 segundos si no hay nada
                pass

        except Exception as e:
            logger.error(f"❌ WORKER: Error en ciclo: {e}")
            time.sleep(5)

# 6. HILO
threading.Thread(target=redis_worker, daemon=True).start()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)