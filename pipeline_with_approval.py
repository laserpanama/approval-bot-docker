#!/usr/bin/env python3
"""
🍽️ FOOD BUSINESS — Reel Machine WITH APPROVAL
Full pipeline: stitch → notify → approve → post
"""

import os, subprocess, random, logging, uuid
from datetime import datetime
from approval_bot import submit_for_approval, start_approval_server

RCLONE_REMOTE   = "gdrive"
DRIVE_ROOT      = "Instagram Reels Pipeline"
HOOKS_FOLDER    = f"{DRIVE_ROOT}/hooks"
BODIES_FOLDER   = f"{DRIVE_ROOT}/bodies"
LOCAL_TEMP_DIR  = "/tmp/reel_machine"

CAPTION_TEMPLATES = [
    "🔥 Our best-selling dish — nobody can stop at one bite! #foodie #panama",
    "This is how we prep 200 orders a day 👀 #restaurant #foodbusiness",
    "POV: You found the best food in Panama 😍 #local #foodie #comida",
    "Tag someone who NEEDS to try this! 👇 #foodbusiness #viral #panama",
    "Save this before you forget! 🔖 #recipe #foodie #restaurant",
    "Nobody talks about this trick 👇 #chef #cooking #foodbusiness #viral",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("/tmp/reel_machine/pipeline.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


def list_drive_files(folder):
    r = subprocess.run(
        ["rclone", "lsf", f"{RCLONE_REMOTE}:{folder}", "--include", "*.mp4"],
        capture_output=True, text=True
    )
    return [f.strip() for f in r.stdout.strip().splitlines() if f.strip()]


def download_file(folder, filename, dest):
    r = subprocess.run(
        ["rclone", "copyto", f"{RCLONE_REMOTE}:{folder}/{filename}", dest],
        capture_output=True, text=True
    )
    return r.returncode == 0


def stitch_clips(hook_path, body_path, output_path):
    concat_list = output_path + ".txt"
    with open(concat_list, "w") as f:
        f.write(f"file '{hook_path}'\nfile '{body_path}'\n")
    r = subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list,
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,"
               "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-ar", "44100", "-b:a", "128k",
        "-movflags", "+faststart", output_path
    ], capture_output=True, text=True)
    try: os.remove(concat_list)
    except: pass
    return r.returncode == 0


def load_used(csv="/tmp/reel_machine/tracking.csv"):
    import csv as _csv
    used = set()
    if not os.path.exists(csv): return used
    with open(csv) as f:
        for row in _csv.DictReader(f):
            if row.get("status") in ("posted", "rejected"):
                used.add((row["hook_id"], row["body_id"]))
    return used


def log_result(hook_id, body_id, caption, status, post_id=""):
    import csv as _csv
    path = "/tmp/reel_machine/tracking.csv"
    new  = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = _csv.writer(f)
        if new: w.writerow(["timestamp","hook_id","body_id","caption","status","post_id"])
        w.writerow([datetime.now().isoformat(), hook_id, body_id, caption[:80], status, post_id])


def run_pipeline():
    os.makedirs(LOCAL_TEMP_DIR, exist_ok=True)

    hooks  = list_drive_files(HOOKS_FOLDER)
    bodies = list_drive_files(BODIES_FOLDER)
    used   = load_used()

    candidates = [(h, b) for h in hooks for b in bodies if (h, b) not in used]
    if not candidates:
        log.warning("All combinations used! Upload more hooks/bodies.")
        return False

    hook_id, body_id = random.choice(candidates)
    hook_p  = f"{LOCAL_TEMP_DIR}/{hook_id}"
    body_p  = f"{LOCAL_TEMP_DIR}/{body_id}"
    reel_id = str(uuid.uuid4())[:8]
    out_p   = f"{LOCAL_TEMP_DIR}/reel_{reel_id}.mp4"
    caption = random.choice(CAPTION_TEMPLATES)

    log.info(f"Selected: {hook_id} + {body_id}")

    if not download_file(HOOKS_FOLDER, hook_id, hook_p): return False
    if not download_file(BODIES_FOLDER, body_id, body_p): return False
    if not stitch_clips(hook_p, body_p, out_p): return False

    # Clean up source clips (keep only stitched reel until approved)
    for p in [hook_p, body_p]:
        try: os.remove(p)
        except: pass

    log.info(f"Reel stitched → {out_p}. Sending for approval...")

    # ── APPROVAL STEP ──────────────────────────────────────────
    status = submit_for_approval(
        reel_id    = reel_id,
        video_path = out_p,
        hook_id    = hook_id,
        body_id    = body_id,
        caption    = caption,
        wait       = True   # blocks here until you tap approve or reject
    )
    # ───────────────────────────────────────────────────────────

    log_result(hook_id, body_id, caption, status)
    log.info(f"Pipeline complete — status: {status}")
    return status == "posted"


if __name__ == "__main__":
    # Start approval server once (if not already running)
    start_approval_server(port=8080)
    run_pipeline()
