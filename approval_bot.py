import os, json, logging, redis, requests, threading, time
from fastapi import FastAPI
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
app = FastAPI()

# Configuración con valores limpios
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
QUEUE_NAME = "reel:ready_for_approval"

r = redis.from_url(REDIS_URL)

def telegram(text, kb=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    if kb: payload["reply_markup"] = json.dumps(kb)
    try:
        res = requests.post(url, json=payload, timeout=10)
        logger.info(f"Telegram response: {res.status_code}")
    except Exception as e:
        logger.error(f"Error Telegram: {e}")

@app.get("/debug")
async def debug():
    keys = [k.decode('utf-8') for k in r.keys("*")]
    tipo = r.type(QUEUE_NAME).decode('utf-8')
    return {"keys_en_redis": keys, "tipo_cola": tipo, "queue_name": QUEUE_NAME}

@app.get("/")
async def home(): return "Bot de Diagnóstico Activo 🕵️"

def worker():
    logger.info("🕵️ Worker de Diagnóstico iniciado...")
    # Saludo inicial para confirmar que el TOKEN y CHAT_ID están bien
    telegram("🔍 **Worker de Diagnóstico Activo**\nBuscando reels en la base de datos...")

    while True:
        try:
            # 1. Intentar sacar de la lista
            item = r.lpop(QUEUE_NAME)
            
            # 2. Si no hay lista, intentar leer como string
            if not item:
                item = r.get(QUEUE_NAME)
                if item: r.delete(QUEUE_NAME)

            if item:
                data = json.loads(item.decode('utf-8'))
                rid = data.get("reel_id", data.get("id", "sin_id"))
                body = data.get("script", data.get("hook", "Contenido vacío"))
                
                # Guardar para el botón
                r.set(f"reel:{rid}", item, ex=86400)

                kb = {"inline_keyboard": [[{"text": "✅ Aprobar", "url": f"https://reel-machine.onrender.com/approve?reel_id={rid}&action=approve"}]]}
                telegram(f"🎬 **¡REEL ENCONTRADO!**\nID: `{rid}`\n\n{body}", kb)
            
            # 3. Escaneo de seguridad: Si no encuentra nada en la cola, ver si hay llaves sueltas
            else:
                all_keys = r.keys("hook_*") # Buscar si el generador los guarda con otro nombre
                if all_keys:
                    logger.info(f"Ojo: Encontré llaves sueltas: {all_keys}")

            time.sleep(5)
        except Exception as e:
            logger.error(f"Error en worker: {e}")
            time.sleep(5)

threading.Thread(target=worker, daemon=True).start()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
