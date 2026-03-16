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
QUEUE_NAME = "ready_for_approval"

# 3. CONEXIÓN A REDIS (Manejo manual de bytes para máxima estabilidad)
try:
    r = redis.from_url(REDIS_URL)
    r.ping()
    logger.info("✅ REDIS: Conexión verificada")
except Exception as e:
    logger.error(f"❌ REDIS: Error crítico: {e}")

def send_telegram_message(text, reply_markup=None):
    """Envía notificaciones formateadas a Telegram"""
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
        logger.error(f"❌ Error enviando a Telegram: {e}")
        return None

# 4. ENDPOINTS (API de Aprobación)
@app.get("/", response_class=HTMLResponse)
async def home():
    return "<h1>Food Reel Machine: Status Online 🚀</h1><p>Esperando guiones de alta calidad...</p>"

@app.get("/approve")
async def approve_reel(reel_id: str, action: str):
    # Buscamos el reel en la persistencia de Redis
    raw_data = r.get(f"reel:{reel_id}")
    
    if not raw_data:
        return HTMLResponse("<h1>Error ❌</h1><p>El Reel ya no existe en la memoria temporal.</p>")

    reel_data = json.loads(raw_data.decode('utf-8'))
    
    if action == "approve":
        # Aquí es donde en el futuro conectaremos la API de Instagram
        msg = f"✅ **¡REEL APROBADO PARA PUBLICAR!**\n\n🆔 ID: `{reel_id}`\n📝 Guion: {reel_data.get('body')}"
        send_telegram_message(msg)
        return HTMLResponse("<h1>Aprobado ✅</h1><p>El contenido se ha marcado para publicación.</p>")
    
    elif action == "reject":
        r.delete(f"reel:{reel_id}")
        return HTMLResponse("<h1>Rechazado ❌</h1><p>El reel ha sido eliminado de la cola.</p>")

# 5. WORKER BLINDADO (El corazón que consume la cola)
def redis_worker():
    logger.info(f"🏃‍♂️ Worker iniciado. Monitoreando cola: {QUEUE_NAME}")
    # Pequeño saludo al iniciar
    send_telegram_message(f"🤖 **Food Reel Machine Online**\nEsperando contenido gastronómico en `{QUEUE_NAME}`...")

    while True:
        try:
            # BRPOP: Espera activa eficiente. Devuelve (key, value)
            item = r.brpop(QUEUE_NAME, timeout=10)
            
            if not item:
                continue

            _, data_bytes = item
            logger.info(f"📥 Nuevo Reel detectado en Redis")

            # Decodificación y limpieza
            data_str = data_bytes.decode('utf-8')
            data_json = json.loads(data_str)

            reel_id = data_json.get("reel_id", f"reel_{int(time.time())}")
            topic = data_json.get("topic", "Gastronomía").replace("_", " ").upper()
            
            # Priorizamos el script de IA sobre el body genérico
            script = data_json.get("script") or data_json.get("body") or "Sin guion generado"
            caption = data_json.get("caption", "Sin caption")
            hashtags = " ".join(data_json.get("hashtags", ["#food", "#viral"]))

            # Guardamos en Redis (1 día de vida) para que el botón de aprobación funcione
            r.set(f"reel:{reel_id}", data_bytes, ex=86400)

            # Formateo del mensaje para decisión humana
            mensaje_telegram = (
                f"🎬 **NUEVA PROPUESTA DE REEL**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🎯 **TEMA:** #{topic}\n"
                f"🆔 **ID:** `{reel_id}`\n\n"
                f"📝 **GUION ESTRATÉGICO:**\n"
                f"{script}\n\n"
                f"📱 **CAPTION SUGERIDO:**\n"
                f"{caption}\n\n"
                f"🏷️ **HASHTAGS:**\n"
                f"_{hashtags}_"
            )

            keyboard = {
                "inline_keyboard": [[
                    {"text": "✅ APROBAR", "url": f"https://reel-machine.onrender.com/approve?reel_id={reel_id}&action=approve"},
                    {"text": "❌ RECHAZAR", "url": f"https://reel-machine.onrender.com/approve?reel_id={reel_id}&action=reject"}
                ]]
            }

            send_telegram_message(mensaje_telegram, reply_markup=keyboard)
            logger.info(f"✅ Notificación enviada para Reel ID: {reel_id}")

        except Exception as e:
            logger.error(f"❌ Error en el ciclo del Worker: {e}")
            time.sleep(5)

# 6. INICIO DEL HILO DEL WORKER
worker_thread = threading.Thread(target=redis_worker, daemon=True)
worker_thread.start()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)