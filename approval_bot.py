#!/usr/bin/env python3
"""
🍽️ REEL APPROVAL BOT  [REDIS EDITION]

Listens to Redis queue `reel:ready_for_approval`.
For each job:
  - Sends video + AI caption to Telegram + WhatsApp
  - User taps ✅ → posts to Instagram + TikTok + Facebook
  - User taps ❌ → skips, logs rejection
  - Auto-timeout after APPROVAL_TIMEOUT seconds

Also starts an HTTP server on port 8080 for approve/reject webhooks.
"""

import os
import json
import time
import logging
import secrets
import threading
import requests
import redis
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from multi_platform_publisher import post_to_platforms

log = logging.getLogger(__name__)

# ── ENV VARS ────────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN  = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_WA_FROM     = os.environ.get("TWILIO_WA_FROM", "")
TWILIO_WA_TO       = os.environ.get("TWILIO_WA_TO", "")
BASE_URL           = "https://reel-machine.onrender.com"
APPROVAL_TIMEOUT   = int(os.environ.get("APPROVAL_TIMEOUT", "3600"))
REDIS_URL          = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

TELEGRAM_MAX_VIDEO_BYTES = 50 * 1024 * 1024  # 50 MB

# ── THREAD-SAFE PENDING STORE ───────────────────────────────────────────────────
_lock      = threading.Lock()
_pending   = {}   # { reel_id: { ...job data..., token } }
_completed = {}   # { reel_id: final_status }  — survives deletion from _pending


def _get(reel_id):
    with _lock:
        return _pending.get(reel_id)

def _set(reel_id, data):
    with _lock:
        _pending[reel_id] = data

def _delete(reel_id):
    with _lock:
        return _pending.pop(reel_id, None)

def _exists(reel_id):
    with _lock:
        return reel_id in _pending

def _complete(reel_id, status):
    with _lock:
        _completed[reel_id] = status

def _pop_complete(reel_id):
    with _lock:
        return _completed.pop(reel_id, None)


# ── REDIS ───────────────────────────────────────────────────────────────────────

def get_redis() -> redis.Redis:
    return redis.from_url(REDIS_URL, decode_responses=True)


def redis_update_status(r: redis.Redis, reel_id: str, status: str, **extra):
    """Update job status in Redis hash."""
    try:
        mapping = {"status": status, "updated_at": datetime.now().isoformat(), **extra}
        r.hset(f"reel:status:{reel_id}", mapping=mapping)
    except redis.RedisError as e:
        log.warning(f"Redis status update failed: {e}")


# ── TELEGRAM ────────────────────────────────────────────────────────────────────

def telegram_send_reel(job: dict, token: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram not configured — skipping")
        return False

    reel_id     = job.get("reel_id", "unknown_id")
    body_id     = job.get("body_id", job.get("script", "N/A"))
    caption     = job.get("caption", "")
    video_path  = job.get("video_path", "/tmp/dummy.mp4")

    approve_url = f"{BASE_URL}/approve?reel_id={reel_id}&action=approve&token={token}"
    reject_url  = f"{BASE_URL}/approve?reel_id={reel_id}&action=reject&token={token}"

    keyboard = {"inline_keyboard": [[
        {"text": "✅ Approve & Post to ALL 3", "url": approve_url},
        {"text": "❌ Reject",                  "url": reject_url},
    ]]}

    text = (
        f"🎬 *New Reel Ready — 3 Platforms*\n\n"
        f"📎 ID: `{reel_id}`\n"
        f"📎 Body: `{body_id}`\n"
        f"📝 {caption[:120]}\n\n"
        f"▶ Will post to: Instagram + TikTok + Facebook\n"
        f"⏳ Auto-skips in {APPROVAL_TIMEOUT // 60} minutes."
    )

    resp = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": text,
              "parse_mode": "Markdown", "reply_markup": keyboard},
        timeout=10
    )
    if resp.status_code != 200:
        log.error(f"Telegram message failed: {resp.text}")
        return False

    # Send video preview if under 50 MB
    file_size = os.path.getsize(video_path) if os.path.exists(video_path) else 0
    if 0 < file_size <= TELEGRAM_MAX_VIDEO_BYTES:
        with open(video_path, "rb") as vf:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo",
                data={"chat_id": TELEGRAM_CHAT_ID,
                      "caption": f"Preview — `{reel_id}`", "parse_mode": "Markdown"},
                files={"video": vf},
                timeout=120
            )
    elif file_size > TELEGRAM_MAX_VIDEO_BYTES:
        size_mb = file_size / 1024 / 1024
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID,
                  "text": f"⚠️ Video too large to preview ({size_mb:.1f} MB). Use buttons above."},
            timeout=10
        )

    log.info(f"✅ Sent to Telegram — reel_id={reel_id}")
    return True


# ── WHATSAPP ────────────────────────────────────────────────────────────────────

def whatsapp_send_reel(job: dict, token: str) -> bool:
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        log.warning("Twilio not configured — skipping WhatsApp")
        return False

    reel_id = job.get("reel_id", "unknown_id")
    caption = job.get("caption", "")
    body_id = job.get("body_id", job.get("script", "N/A"))

    approve_url = f"{BASE_URL}/approve?reel_id={reel_id}&action=approve&token={token}"
    reject_url  = f"{BASE_URL}/approve?reel_id={reel_id}&action=reject&token={token}"

    body = (
        f"🍽️ New Reel Ready!\n\n"
        f"ID: {reel_id}\nBody: {body_id}\n"
        f"Caption: {caption[:80]}...\n\n"
        f"✅ APPROVE (IG+TT+FB):\n{approve_url}\n\n"
        f"❌ REJECT:\n{reject_url}\n\n"
        f"⏳ Auto-skips in {APPROVAL_TIMEOUT // 60} minutes."
    )

    resp = requests.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json",
        auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
        data={"From": TWILIO_WA_FROM, "To": TWILIO_WA_TO, "Body": body},
        timeout=15
    )
    if resp.status_code not in (200, 201):
        log.error(f"WhatsApp send failed: {resp.text}")
        return False

    log.info(f"✅ Sent to WhatsApp — reel_id={reel_id}")
    return True


def telegram_notify(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"},
            timeout=10
        )
    except Exception as e:
        log.warning(f"telegram_notify failed: {e}")


# ── HTTP APPROVAL SERVER ────────────────────────────────────────────────────────

class ApprovalHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)

        # Health check
        if parsed.path == "/health":
            self._respond(200, "✅ Approval bot running")
            return

        # Status page
        if parsed.path == "/":
            with _lock:
                count = len(_pending)
            self._respond(200, f"🍽️ Reel Machine<br>Pending approvals: {count}")
            return

        # Queue stats
        if parsed.path == "/queue/stats":
            try:
                r = get_redis()
                needs_caption = r.llen("reel:needs_caption")
                ready         = r.llen("reel:ready_for_approval")
            except Exception:
                needs_caption = ready = "?"
            with _lock:
                pending_count = len(_pending)
            stats = {
                "needs_caption":       needs_caption,
                "ready_for_approval":  ready,
                "waiting_approval":    pending_count,
            }
            self._respond(200, json.dumps(stats, indent=2), content_type="application/json")
            return

        # Approve / Reject
        params  = parse_qs(parsed.query)
        reel_id = params.get("reel_id", [None])[0]
        action  = params.get("action",  [None])[0]
        token   = params.get("token",   [None])[0]

        if not reel_id or action not in ("approve", "reject"):
            self._respond(400, "❌ Invalid request")
            return

        job = _get(reel_id)
        if not job:
            self._respond(404, "⚠️ Reel not found or already processed")
            return

        if token != job.get("token"):
            self._respond(403, "❌ Invalid token")
            return

        if action == "approve":
            log.info(f"✅ APPROVED — reel_id={reel_id}")
            results = post_to_platforms(
                video_path=job.get("video_path", "/tmp/dummy.mp4"),
                caption=job.get("caption", ""),
                platforms=["instagram", "tiktok", "facebook"],
            )
            success = any(v is not None for v in results.values())
            platform_summary = " | ".join(
                f"{p.upper()}: {'✅' if pid else '❌'}"
                for p, pid in results.items()
            )
            final_status = "posted" if success else "error_post"
            _delete(reel_id)
            _complete(reel_id, final_status)

            try:
                r = get_redis()
                redis_update_status(r, reel_id, final_status,
                                    platform_summary=platform_summary)
            except Exception:
                pass

            if success:
                self._respond(200, f"🎉 Posted!<br><small>{platform_summary}</small>")
                telegram_notify(f"✅ Reel `{reel_id}` posted!\n{platform_summary}")
            else:
                self._respond(500, "❌ All platforms failed. Check logs.")
                telegram_notify(f"❌ Reel `{reel_id}` failed on all platforms.")

        else:  # reject
            log.info(f"❌ REJECTED — reel_id={reel_id}")
            _delete(reel_id)
            _complete(reel_id, "rejected")

            try:
                r = get_redis()
                redis_update_status(r, reel_id, "rejected")
            except Exception:
                pass

            self._respond(200, "👍 Rejected. Next combo queued.")
            telegram_notify(f"❌ Reel `{reel_id}` rejected.")

        # Clean up video file
        try:
            if "video_path" in job:
                os.remove(job["video_path"])
        except FileNotFoundError:
            pass

    def _respond(self, code, msg, content_type="text/html"):
        if content_type == "application/json":
            body = msg.encode()
        else:
            body = f"""<html><body style="font-family:sans-serif;text-align:center;
            padding:60px;font-size:22px;">{msg}</body></html>""".encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def start_approval_server(port: int = 8080):
    server = HTTPServer(("0.0.0.0", port), ApprovalHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    log.info(f"🌐 Approval server running on port {port}")
    return server


# ── REDIS QUEUE LISTENER ────────────────────────────────────────────────────────

def queue_listener():
    """
    Background thread: watches `reel:ready_for_approval` in Redis.
    When a job arrives, registers it in _pending and sends notifications.
    """
    log.info("👂 Queue listener started — watching reel:ready_for_approval")
    while True:
        try:
            r = get_redis()
            result = r.brpop("reel:ready_for_approval", timeout=10)
            if not result:
                continue

            _, raw = result
            job     = json.loads(raw)
            reel_id = job["reel_id"]
            token   = secrets.token_urlsafe(12)

            job["token"] = token
            _set(reel_id, job)
            log.info(f"📥 New job from Redis — reel_id={reel_id}")

            # Send to Telegram + WhatsApp
            telegram_send_reel(job, token)
            whatsapp_send_reel(job, token)

            # Spawn timeout watcher
            threading.Thread(
                target=_timeout_watcher,
                args=(reel_id,),
                daemon=True
            ).start()

        except redis.RedisError as e:
            log.error(f"Redis error in queue listener: {e} — retrying in 10s")
            time.sleep(10)
        except Exception as e:
            log.error(f"Queue listener error: {e}")
            time.sleep(5)


def _timeout_watcher(reel_id: str):
    """Auto-reject a job if not approved within APPROVAL_TIMEOUT seconds."""
    time.sleep(APPROVAL_TIMEOUT)
    job = _delete(reel_id)
    if job:
        try:
            if "video_path" in job:
                os.remove(job["video_path"])
        except FileNotFoundError:
            pass
        try:
            r = get_redis()
            redis_update_status(r, reel_id, "timeout")
        except Exception:
            pass
        telegram_notify(f"⏰ Reel `{reel_id}` timed out — skipped automatically.")
        log.warning(f"⏰ Approval timeout — reel_id={reel_id}")


# ── ENTRY POINT ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler("/tmp/reel_machine/approval_bot.log"),
            logging.StreamHandler()
        ]
    )

    os.makedirs("/tmp/reel_machine", exist_ok=True)

    # Start HTTP server
    port = int(os.environ.get("PORT", "8080"))
    start_approval_server(port=port)

    # Start Redis queue listener in background
    t = threading.Thread(target=queue_listener, daemon=True)
    t.start()

    log.info("✅ Approval bot ready — watching Redis + serving HTTP on :8080")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Shutting down.")
