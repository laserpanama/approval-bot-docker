#!/usr/bin/env python3
"""
🍽️ FOOD BUSINESS — Automated Instagram Reels Machine  [REDIS EDITION]

Flow:
  1. Cron triggers at 9am / 2pm / 7pm Panama time
  2. Pick unused hook + body combo from Google Drive via rclone
  3. Stitch into 1080×1920 reel with FFmpeg
  4. Push job to Redis queue → content-creator picks it up and generates caption
  5. approval_bot sends reel + caption to Telegram/WhatsApp for approval
  6. On approve → multi_platform_publisher posts to Instagram + TikTok + Facebook
  7. Log result to CSV / Google Sheets
"""

import os
import json
import subprocess
import random
import csv
import logging
import requests
import redis
from datetime import datetime

# ─── CONFIG ────────────────────────────────────────────────────────────────────
RCLONE_REMOTE       = "gdrive"
DRIVE_ROOT          = "Instagram Reels Pipeline"
HOOKS_FOLDER        = f"{DRIVE_ROOT}/hooks"
BODIES_FOLDER       = f"{DRIVE_ROOT}/bodies"
LOCAL_TEMP_DIR      = "/tmp/reel_machine"

METRICOOL_TOKEN     = os.environ.get("METRICOOL_TOKEN", "")
METRICOOL_USER_ID   = os.environ.get("METRICOOL_USER_ID", "")
INSTAGRAM_USERNAME  = os.environ.get("INSTAGRAM_USERNAME", "")
SHEETS_TRACKING_ID  = os.environ.get("SHEETS_TRACKING_ID", "")
SHEETS_RANGE        = "Sheet1!A:G"
REDIS_URL           = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Fallback captions used when content-creator is unavailable
CAPTION_FALLBACKS = [
    "🍽️ El secreto que le falta a tu cocina… #foodbusiness #foodie #restaurant #foodtok",
    "Nadie habla de este truco 👇 #chef #cooking #foodbusiness #viral",
    "¡Guarda esto antes de olvidarlo! 🔖 #foodie #recipe #foodbusiness #restaurant",
    "POV: Finalmente sabes cómo lo hacen los pros 😮 #cooking #foodbusiness #viral",
    "Esto cambió todo en nuestra cocina 🔥 #restaurant #foodie #foodbusiness",
    "Ojalá lo hubiera sabido antes… 👨‍🍳 #chef #cooking #foodtok #foodbusiness",
    "¡Etiqueta a alguien que NECESITA ver esto! 👇 #food #foodbusiness #restaurant #viral",
    "El truco que nos trajo 1000+ clientes 🍴 #foodbusiness #restaurant #viral",
]

# ─── LOGGING ───────────────────────────────────────────────────────────────────
os.makedirs(LOCAL_TEMP_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(f"{LOCAL_TEMP_DIR}/pipeline.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ─── REDIS CLIENT ──────────────────────────────────────────────────────────────

def get_redis() -> redis.Redis:
    return redis.from_url(REDIS_URL, decode_responses=True)


def redis_push_job(r: redis.Redis, job: dict):
    """Push a new reel job to the Redis queue for caption generation."""
    r.lpush("reel:needs_caption", json.dumps(job))
    r.hset(f"reel:status:{job['reel_id']}", mapping={
        "status": "needs_caption",
        "hook_id": job["hook_id"],
        "body_id": job["body_id"],
        "video_path": job["video_path"],
        "created_at": job["created_at"],
    })
    log.info(f"📤 Job pushed to Redis queue — reel_id={job['reel_id']}")


def redis_wait_for_caption(r: redis.Redis, reel_id: str, timeout: int = 120) -> str | None:
    """
    Wait up to `timeout` seconds for the content-creator to generate a caption.
    Returns the caption string, or None if it timed out.
    """
    key = f"reel:caption:{reel_id}"
    result = r.brpop(key, timeout=timeout)
    if result:
        _, caption = result
        log.info(f"📝 Caption received from content-creator — reel_id={reel_id}")
        return caption
    log.warning(f"⏰ Caption timeout after {timeout}s — using fallback caption")
    return None


# ─── GOOGLE DRIVE via RCLONE ───────────────────────────────────────────────────

def list_drive_files(folder: str) -> list[str]:
    result = subprocess.run(
        ["rclone", "lsf", f"{RCLONE_REMOTE}:{folder}", "--include", "*.mp4"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        log.error(f"rclone lsf failed: {result.stderr}")
        return []
    return [f.strip() for f in result.stdout.strip().splitlines() if f.strip()]


def download_file(folder: str, filename: str, dest: str) -> bool:
    result = subprocess.run(
        ["rclone", "copyto", f"{RCLONE_REMOTE}:{folder}/{filename}", dest],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        log.error(f"Download failed for {filename}: {result.stderr}")
        return False
    log.info(f"Downloaded: {filename}")
    return True


def delete_local(path: str):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


# ─── VIDEO STITCHING via FFMPEG ────────────────────────────────────────────────

def stitch_clips(hook_path: str, body_path: str, output_path: str) -> bool:
    """Combine hook + body into 1080×1920 vertical reel with normalized audio."""
    concat_list = output_path + ".txt"
    with open(concat_list, "w") as f:
        f.write(f"file '{hook_path}'\n")
        f.write(f"file '{body_path}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", concat_list,
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,"
               "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-ar", "44100", "-b:a", "128k",
        "-movflags", "+faststart",
        output_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        os.remove(concat_list)
    except FileNotFoundError:
        pass

    if result.returncode != 0:
        log.error(f"FFmpeg failed: {result.stderr[-500:]}")
        return False

    log.info(f"Stitched reel: {output_path}")
    return True


# ─── COMBINATION PICKER ────────────────────────────────────────────────────────

def load_used_combinations() -> set:
    csv_path = f"{LOCAL_TEMP_DIR}/tracking.csv"
    used = set()
    if not os.path.exists(csv_path):
        return used
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            if row.get("status") in ("posted", "scheduled"):
                used.add((row["hook_id"], row["body_id"]))
    return used


def pick_combination(hooks: list, bodies: list) -> tuple[str, str] | None:
    used = load_used_combinations()
    candidates = [(h, b) for h in hooks for b in bodies if (h, b) not in used]
    if not candidates:
        log.warning("All combinations used! Add more hooks/bodies to Google Drive.")
        return None
    return random.choice(candidates)


# ─── TRACKING ──────────────────────────────────────────────────────────────────

def log_to_sheet(hook_id, body_id, caption, status, post_id=""):
    sheets_token = os.environ.get("SHEETS_TOKEN", "")
    if not sheets_token or not SHEETS_TRACKING_ID:
        _log_to_csv(hook_id, body_id, caption, status, post_id)
        return

    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/"
        f"{SHEETS_TRACKING_ID}/values/{SHEETS_RANGE}:append"
        f"?valueInputOption=USER_ENTERED"
    )
    headers = {"Authorization": f"Bearer {sheets_token}"}
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = {"values": [[now, hook_id, body_id, caption[:80], status, post_id, INSTAGRAM_USERNAME]]}

    resp = requests.post(url, headers=headers, json=body)
    if resp.status_code != 200:
        log.warning(f"Sheets failed, falling back to CSV: {resp.text}")
        _log_to_csv(hook_id, body_id, caption, status, post_id)
    else:
        log.info("Logged to Google Sheets ✅")


def _log_to_csv(hook_id, body_id, caption, status, post_id):
    csv_path = f"{LOCAL_TEMP_DIR}/tracking.csv"
    write_header = not os.path.exists(csv_path)
    with open(csv_path, "a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["timestamp", "hook_id", "body_id", "caption", "status", "post_id", "account"])
        writer.writerow([
            datetime.now().isoformat(),
            hook_id, body_id, caption[:80],
            status, post_id, INSTAGRAM_USERNAME
        ])
    log.info(f"Logged to CSV: {csv_path}")


# ─── MAIN PIPELINE ─────────────────────────────────────────────────────────────

def run_pipeline(dry_run: bool = False):
    """
    Full pipeline:
      1. List hooks & bodies from Google Drive
      2. Pick unused combination
      3. Download clips
      4. Stitch with FFmpeg
      5. Push to Redis → content-creator generates caption
      6. Push complete job to Redis approval queue
      7. approval_bot sends to Telegram/WhatsApp (handled separately)
      8. Log to Sheets/CSV
    """
    log.info("=" * 55)
    log.info("🍽️  Reel Machine — Starting pipeline run")
    log.info(f"   DRY RUN: {dry_run}")

    os.makedirs(LOCAL_TEMP_DIR, exist_ok=True)

    # 1. List clips
    hooks  = list_drive_files(HOOKS_FOLDER)
    bodies = list_drive_files(BODIES_FOLDER)
    log.info(f"Found {len(hooks)} hooks, {len(bodies)} bodies → {len(hooks)*len(bodies)} combos")

    if not hooks or not bodies:
        log.error("No clips found in Google Drive. Aborting.")
        return False

    # 2. Pick combo
    combo = pick_combination(hooks, bodies)
    if not combo:
        return False
    hook_id, body_id = combo
    log.info(f"Selected: hook={hook_id}  body={body_id}")

    if dry_run:
        log.info("DRY RUN — skipping download, stitch, and post.")
        _log_to_csv(hook_id, body_id, "(dry run)", "dry_run", "")
        return True

    # 3. Download
    hook_local  = os.path.join(LOCAL_TEMP_DIR, hook_id)
    body_local  = os.path.join(LOCAL_TEMP_DIR, body_id)
    reel_id     = f"reel_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_path = os.path.join(LOCAL_TEMP_DIR, f"{reel_id}.mp4")

    if not download_file(HOOKS_FOLDER, hook_id, hook_local):
        _log_to_csv(hook_id, body_id, "", "error_download_hook")
        return False
    if not download_file(BODIES_FOLDER, body_id, body_local):
        _log_to_csv(hook_id, body_id, "", "error_download_body")
        return False

    # 4. Stitch
    if not stitch_clips(hook_local, body_local, output_path):
        _log_to_csv(hook_id, body_id, "", "error_ffmpeg")
        delete_local(hook_local)
        delete_local(body_local)
        return False

    delete_local(hook_local)
    delete_local(body_local)

    # 5. Push to Redis — content-creator will generate the caption
    job = {
        "reel_id":    reel_id,
        "video_path": output_path,
        "hook_id":    hook_id,
        "body_id":    body_id,
        "created_at": datetime.now().isoformat(),
    }

    try:
        r = get_redis()
        redis_push_job(r, job)

        # 6. Wait for caption (up to 2 minutes)
        caption = redis_wait_for_caption(r, reel_id, timeout=120)
        if not caption:
            caption = random.choice(CAPTION_FALLBACKS)

        # 7. Push complete job to approval queue
        job["caption"] = caption
        r.lpush("reel:ready_for_approval", json.dumps(job))
        r.hset(f"reel:status:{reel_id}", mapping={"status": "pending_approval", "caption": caption[:100]})
        log.info(f"📤 Job in approval queue — reel_id={reel_id}")
        _log_to_csv(hook_id, body_id, caption, "pending_approval", "")
        return True

    except redis.RedisError as e:
        log.error(f"Redis error: {e} — falling back to direct approval")
        # Graceful fallback: if Redis is down, still try to post
        from approval_bot import submit_for_approval, start_approval_server
        start_approval_server()
        caption = random.choice(CAPTION_FALLBACKS)
        status = submit_for_approval(reel_id, output_path, hook_id, body_id, caption)
        _log_to_csv(hook_id, body_id, caption, status, "")
        return status == "posted"


if __name__ == "__main__":
    import sys
    dry = "--dry-run" in sys.argv
    success = run_pipeline(dry_run=dry)
    sys.exit(0 if success else 1)
