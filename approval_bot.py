import os
import json
import logging
import redis
import requests
import threading
import time
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

# 1. CONFIGURACIÓN DE LOGS
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
    r.ping()
    logger.info("✅ REDIS: Conexión verificada")
except Exception as e:
    logger.error(f"❌ REDIS: Error de conexión: {e}")

def send_telegram_message(text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"❌ Error Telegram: {e}")
        return None

# 4. ENDPOINTS
@app.get("/", response_class=HTMLResponse)
async def home():
    return "<h1>Bot Híbrido: ONLINE 🚀</h1><p>Vigilando Listas y Strings en Redis...</p>"

@app.get("/approve")
async def approve_reel(reel_id: str, action: str):
    reel_data_raw = r.get(f"reel:{reel_id}")
    if not reel_data_raw:
        return HTMLResponse("<h1>Error ❌</h1><p>Reel no encontrado.</p>")
    
    reel_data = json.loads(reel_data_raw)
    if action == "approve":
        send_telegram_message(f"✅ **GUION APROBADO:**\n\n{reel_data.get('body')}")
        return HTMLResponse("<h1>Aprobado ✅</h1>")
    return HTMLResponse("<h1>Rechazado</h1>")

# 5. LÓGICA DE PROCESAMIENTO
def procesar_y_enviar(message):
    """Extrae los datos del JSON y envía el formato con botones a Telegram"""
    try:
        data = json.loads(message)
        reel_id = data.get("reel_id", "unknown")
        body = data.get("body", "Sin contenido")
        
        # Guardamos en Redis para que el botón de aprobación funcione
        r.set(f"reel:{reel_id}", json.dumps(data), ex=86400)

        keyboard = {
            "inline_keyboard": [[
                {"text": "✅ Aprobar y Copiar", "url": f"https://reel-machine.onrender.com/approve?reel_id={reel_id}&action=approve"}
            ]]
        }

        msg = f"🎬 **¡REEL DETECTADO!**\n\n📎 **ID:** `{reel_id}`\n\n📝 **Guion:**\n{body}"
        send_telegram_message(msg, reply_markup=keyboard)
        logger.info(f"✅ Reel {reel_id} enviado a Telegram exitosamente")
    except Exception as e:
        logger.error(f"❌ Error procesando mensaje: {e}")

# 6. WORKER HÍBRIDO (El corazón del sistema)
def redis_worker():
    logger.info("🏃‍♂️ Worker iniciado en modo Híbrido...")
    time.sleep(8) # Espera a que el generador termine su primer ciclo
    send_telegram_message("🤖 **Bot en modo Híbrido:** Buscando en Listas y Strings...")

    while True:
        try:
            # Opción A: Buscar en LISTA (usando blpop)
            item = r.blpop("ready_for_approval", timeout=5)
            if item:
                _, message = item
                logger.info("📥 Detectado en LISTA (blpop)")
                procesar_y_enviar(message)
                continue

            # Opción B: Buscar como STRING (usando get)
            data_raw = r.get("ready_for_approval")
            if data_raw:
                logger.info("📥 Detectado como STRING (get)")
                procesar_y_enviar(data_raw)
                r.delete("ready_for_approval") # Importante: limpiar para no repetir
            
        except Exception as e:
            logger.error(f"❌ Error en ciclo Worker: {e}")
            time.sleep(5)

# 7. LANZAR HILO
threading.Thread(target=redis_worker, daemon=True).start()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))