import os
import json
import logging
import redis
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
import requests

# CONFIGURACIÓN DE LOGS
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# CONFIGURACIÓN DE VARIABLES (Hardcoded para evitar errores de entorno)
BASE_URL = "https://reel-machine.onrender.com"
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# CONEXIÓN A REDIS
try:
    r = redis.from_url(REDIS_URL, decode_responses=True)
    logger.info("✅ Conectado a Redis con éxito")
except Exception as e:
    logger.error(f"❌ Error conectando a Redis: {e}")

def send_telegram_message(chat_id, text, reply_markup=None):
    """Envía un mensaje a Telegram con soporte para botones"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    
    response = requests.post(url, json=payload)
    return response.json()

@app.get("/", response_class=HTMLResponse)
async def home():
    return "<h1>Approval Bot is Online 🚀</h1><p>Esperando webhooks...</p>"

@app.get("/approve")
async def approve_reel(reel_id: str, action: str, token: str = None):
    """Maneja la acción de los botones de Telegram"""
    
    # Intentamos obtener los datos del reel de Redis
    reel_data_raw = r.get(f"reel:{reel_id}")
    if not reel_data_raw:
        return {"status": "error", "message": "Reel no encontrado en la base de datos"}

    reel_data = json.loads(reel_data_raw)
    body_text = reel_data.get('body', 'Sin guion disponible')

    if action == "approve":
        # MENSAJE DE ÉXITO Y COPIADO MANUAL
        confirmation_text = (
            "✅ **¡REEL APROBADO CON ÉXITO!**\n\n"
            "Aquí tienes tu contenido listo para publicar:\n\n"
            "📝 **GUION / CAPTION:**\n"
            "----------------------------------\n"
            f"{body_text}\n"
            "----------------------------------\n\n"
            "🏷️ **HASHTAGS:**\n"
            "#CustomerService #AIAutomation #ReelsPanama #Automation\n\n"
            "🚀 *Copia el texto arriba y súbelo a tus redes.*"
        )
        
        send_telegram_message(TELEGRAM_CHAT_ID, confirmation_text)
        r.set(f"status:{reel_id}", "COMPLETED")
        
        return HTMLResponse(content=f"<h1>Aprobado ✅</h1><p>Reel {reel_id} listo para publicar.</p>")

    elif action == "reject":
        r.set(f"status:{reel_id}", "REJECTED")
        send_telegram_message(TELEGRAM_CHAT_ID, f"❌ Reel `{reel_id}` ha sido descartado.")
        return HTMLResponse(content=f"<h1>Rechazado ❌</h1><p>Reel {reel_id} eliminado.</p>")

@app.post("/webhook/new_reel")
async def handle_new_reel(request: Request):
    """Recibe nuevos reels del generador y envía la alerta a Telegram"""
    data = await request.json()
    reel_id = data.get("reel_id")
    body = data.get("body", "Nuevo reel generado")

    # Guardar en Redis
    r.set(f"reel:{reel_id}", json.dumps(data))

    # Crear botones para Telegram con URL absoluta corregida
    keyboard = {
        "inline_keyboard": [[
            {
                "text": "✅ Approve & Copy",
                "url": f"{BASE_URL}/approve?reel_id={reel_id}&action=approve"
            },
            {
                "text": "❌ Reject",
                "url": f"{BASE_URL}/approve?reel_id={reel_id}&action=reject"
            }
        ]]
    }

    message = (
        f"🎬 **New Reel Ready!**\n\n"
        f"📎 **ID:** `{reel_id}`\n"
        f"📝 **Guion:**\n{body}\n\n"
        f"👇 ¿Qué deseas hacer?"
    )

    send_telegram_message(TELEGRAM_CHAT_ID, message, reply_markup=keyboard)
    return {"status": "success", "message": "Alert sent to Telegram"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)