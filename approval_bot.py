import os, json, logging, redis, requests, threading, time
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

# Configuración de Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()

# Configuración de Variables
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
QUEUE_NAME = "ready_for_approval"

# Conexión Redis
r = redis.from_url(REDIS_URL, decode_responses=True)

def send_telegram_message(text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    if reply_markup: payload["reply_markup"] = json.dumps(reply_markup)
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.json()
    except Exception as e:
        logger.error(f"❌ Error Telegram: {e}")

@app.get("/")
async def home():
    return {"status": "online", "monitoring_queue": QUEUE_NAME}

@app.get("/approve")
async def approve_reel(reel_id: str, action: str):
    raw_data = r.get(f"reel:{reel_id}")
    if raw_data and action == "approve":
        data = json.loads(raw_data)
        send_telegram_message(f"✅ **GUION APROBADO:**\n\n{data.get('body')}")
        return HTMLResponse("<h1>Aprobado y enviado ✅</h1>")
    return HTMLResponse("<h1>Acción procesada</h1>")

def redis_worker():
    logger.info(f"🕵️ Worker iniciado. Escuchando cola: {QUEUE_NAME}")
    send_telegram_message(f"🚀 **Bot Online:** Esperando reels en `{QUEUE_NAME}`...")

    while True:
        try:
            # 1. BLOQUEO: Espera activa en la lista (Modo eficiente)
            # Retorna una tupla (nombre_cola, valor)
            item = r.brpop(QUEUE_NAME, timeout=10)
            
            data_str = None
            if item:
                _, data_str = item
                logger.info("📥 Reel recibido desde LISTA (BRPOP)")
            else:
                # 2. FALLBACK: Verificar si hay un String (Modo híbrido)
                data_str = r.get(QUEUE_NAME)
                if data_str:
                    logger.info("📥 Reel recibido desde STRING (GET)")
                    r.delete(QUEUE_NAME)

            if data_str:
                data = json.loads(data_str)
                reel_id = data.get("reel_id", f"gen_{int(time.time())}")
                body = data.get("body", "Sin contenido")

                # Guardar para el botón de aprobación
                r.set(f"reel:{reel_id}", json.dumps(data), ex=86400)

                kb = {
                    "inline_keyboard": [[
                        {"text": "✅ Aprobar", "url": f"https://reel-machine.onrender.com/approve?reel_id={reel_id}&action=approve"}
                    ]]
                }
                
                send_telegram_message(f"🎬 **¡NUEVO REEL DETECTADO!**\nID: `{reel_id}`\n\n{body}", reply_markup=kb)
                logger.info(f"✅ Mensaje enviado a Telegram para Reel: {reel_id}")

        except Exception as e:
            logger.error(f"❌ Error en el ciclo del Worker: {e}")
            time.sleep(5)

# Lanzar Worker en segundo plano
threading.Thread(target=redis_worker, daemon=True).start()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))