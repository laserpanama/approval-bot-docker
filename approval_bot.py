import os, json, logging, redis, requests, threading, time
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
app = FastAPI()

r = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
QUEUE_NAME = "ready_for_approval"

# --- NUEVO ENDPOINT DE DEBUG ---
@app.get("/debug")
async def debug_redis():
    """Permite ver qué hay en la cola desde el navegador"""
    try:
        tipo = r.type(QUEUE_NAME).decode('utf-8')
        contenido = "Vacío"
        if tipo == "list":
            contenido = r.lrange(QUEUE_NAME, 0, -1)
        elif tipo == "string":
            contenido = r.get(QUEUE_NAME)
        
        return {
            "queue_name": QUEUE_NAME,
            "data_type": tipo,
            "content_preview": contenido,
            "keys_in_redis": r.keys("*")[:10] # Ver las primeras 10 llaves
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/")
async def home(): return "<h1>Bot Detector Online 🕵️‍♂️</h1><p>Prueba /debug para ver la cola.</p>"

@app.get("/approve")
async def approve_reel(reel_id: str, action: str):
    raw = r.get(f"reel:{reel_id}")
    if raw:
        data = json.loads(raw.decode('utf-8'))
        if action == "approve":
            requests.post(f"https://api.telegram.org/bot{os.environ.get('TELEGRAM_BOT_TOKEN')}/sendMessage", 
                          json={"chat_id": os.environ.get("TELEGRAM_CHAT_ID"), "text": f"✅ Publicando: {reel_id}"})
    return "OK"

def redis_worker():
    logger.info(f"🚀 Worker buscando en '{QUEUE_NAME}'...")
    while True:
        try:
            # 1. Intentar como LISTA (RPUSH/LPOP o BRPOP)
            item = r.lpop(QUEUE_NAME)
            
            # 2. Si no hay lista, intentar como STRING (SET/GET)
            if not item:
                item = r.get(QUEUE_NAME)
                if item: r.delete(QUEUE_NAME) # Limpiar si era un string

            if item:
                logger.info("📥 ¡REEL CAPTURADO!")
                data = json.loads(item.decode('utf-8'))
                reel_id = data.get("reel_id", f"gen_{int(time.time())}")
                
                # Guardar para el botón
                r.set(f"reel:{reel_id}", item, ex=86400)

                msg = f"🎬 **¡NUEVO REEL!**\nID: `{reel_id}`\n\n{data.get('body', data.get('script', 'Sin guion'))}"
                kb = {"inline_keyboard": [[{"text": "✅ Aprobar", "url": f"https://reel-machine.onrender.com/approve?reel_id={reel_id}&action=approve"}]]}
                
                requests.post(f"https://api.telegram.org/bot{os.environ.get('TELEGRAM_BOT_TOKEN')}/sendMessage", 
                              json={"chat_id": os.environ.get("TELEGRAM_CHAT_ID"), "text": msg, "parse_mode": "Markdown", "reply_markup": kb})
            
            time.sleep(5)
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            time.sleep(5)

threading.Thread(target=redis_worker, daemon=True).start()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))