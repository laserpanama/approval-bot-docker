#!/usr/bin/env python3
"""
🍽️ MULTI-PLATFORM PUBLISHER
Posts the approved reel to Instagram (Trial Reel), TikTok, and Facebook
via Metricool's unified API — one video, three platforms.
"""

import os
import logging
import requests

log = logging.getLogger(__name__)

METRICOOL_TOKEN   = os.environ.get("METRICOOL_TOKEN", "")
METRICOOL_USER_ID = os.environ.get("METRICOOL_USER_ID", "")


# ── PLATFORM CONFIGS ────────────────────────────────────────────────────────────

def build_instagram_data() -> dict:
    return {
        "type":                    "REEL",
        "shareToFeed":             False,
        "shareTrialAutomatically": True,   # Trial Reel = non-followers only
    }


def build_tiktok_data() -> dict:
    return {
        "privacyLevel": "PUBLIC_TO_EVERYONE",
        "allowComments": True,
        "allowDuet":     True,
        "allowStitch":   True,
    }


def build_facebook_data() -> dict:
    return {
        "type": "REEL",   # Facebook Reels for non-follower reach
    }


# ── CAPTION ADAPTER ─────────────────────────────────────────────────────────────

def adapt_caption(base_caption: str, platform: str) -> str:
    """
    Adapt a base caption for each platform's style.
    Instagram: medium length, hashtag-rich
    TikTok:    short, lowercase, punchy
    Facebook:  longer, local, storytelling
    """
    if platform == "tiktok":
        # Shorten to 2 lines max, keep first sentence + key hashtags
        lines = base_caption.strip().split("\n")
        first_line = lines[0].lower().rstrip("!.").strip()
        # Extract hashtags
        hashtags = " ".join(w for w in base_caption.split() if w.startswith("#"))
        tiktok_tags = "#foodtok #fyp #panama " + " ".join(
            h for h in hashtags.split() if h not in ("#foodtok", "#fyp", "#panama")
        )
        return f"{first_line} 🍽️\n{tiktok_tags[:150]}"

    elif platform == "facebook":
        # Add local Panama context and WhatsApp CTA
        wa_number = os.environ.get("WHATSAPP_BUSINESS_NUMBER", "")
        local_footer = "\n\n📍 Panama City\n"
        if wa_number:
            local_footer += f"📲 Pedidos por WhatsApp: wa.me/{wa_number}\n"
        local_footer += "#ComidaPanama #Panama #RestaurantePanama"
        # Replace Instagram-specific hashtags
        fb_caption = base_caption.replace("#foodie", "#ComidaPanama")
        return fb_caption + local_footer

    else:  # instagram — use base caption as-is
        return base_caption


# ── MAIN PUBLISHER ──────────────────────────────────────────────────────────────

def upload_media(video_path: str) -> str | None:
    """Upload video to Metricool once, reuse media_id for all platforms."""
    headers = {"Authorization": f"Bearer {METRICOOL_TOKEN}"}
    with open(video_path, "rb") as vf:
        resp = requests.post(
            "https://app.metricool.com/api/v2/scheduler/media",
            headers=headers,
            files={"file": (os.path.basename(video_path), vf, "video/mp4")},
            data={"blogId": METRICOOL_USER_ID}
        )
    if resp.status_code != 200:
        log.error(f"Media upload failed: {resp.text}")
        return None
    media_id = resp.json().get("id") or resp.json().get("mediaId")
    log.info(f"Media uploaded → media_id={media_id}")
    return str(media_id)


def post_to_platforms(
    video_path:  str,
    caption:     str,
    platforms:   list[str] = None,   # ["instagram", "tiktok", "facebook"]
    publish_now: bool = True,
) -> dict:
    """
    Upload video once → post to all requested platforms via Metricool.
    Returns dict of {platform: post_id or None}
    """
    if platforms is None:
        platforms = ["instagram", "tiktok", "facebook"]

    if not METRICOOL_TOKEN or not METRICOOL_USER_ID:
        log.error("Missing METRICOOL_TOKEN or METRICOOL_USER_ID")
        return {p: None for p in platforms}

    # Upload once
    media_id = upload_media(video_path)
    if not media_id:
        return {p: None for p in platforms}

    results = {}
    headers = {"Authorization": f"Bearer {METRICOOL_TOKEN}"}

    platform_map = {
        "instagram": ("INSTAGRAM", build_instagram_data(), "instagramData"),
        "tiktok":    ("TIKTOK",    build_tiktok_data(),    "tiktokData"),
        "facebook":  ("FACEBOOK",  build_facebook_data(),  "facebookData"),
    }

    for platform in platforms:
        if platform not in platform_map:
            log.warning(f"Unknown platform: {platform}")
            results[platform] = None
            continue

        network, platform_data, data_key = platform_map[platform]
        adapted_caption = adapt_caption(caption, platform)

        payload = {
            "blogId":      METRICOOL_USER_ID,
            "networks":    [network],
            "text":        adapted_caption,
            "mediaIds":    [media_id],
            data_key:      platform_data,
            "publishNow":  publish_now,
        }

        resp = requests.post(
            "https://app.metricool.com/api/v2/scheduler/post",
            headers=headers,
            json=payload
        )

        if resp.status_code in (200, 201):
            post_id = resp.json().get("id", "N/A")
            log.info(f"✅ Posted to {platform.upper()} — post_id={post_id}")
            results[platform] = str(post_id)
        else:
            log.error(f"❌ Failed to post to {platform}: [{resp.status_code}] {resp.text}")
            results[platform] = None

    return results


# ── EXAMPLE USAGE ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Test with a dummy path (replace with real video)
    results = post_to_platforms(
        video_path = "/tmp/reel_machine/test_reel.mp4",
        caption    = "POV: You found the best food in Panama 😍 #local #foodie #comida #panama",
        platforms  = ["instagram", "tiktok", "facebook"],
    )

    print("\n📊 POST RESULTS:")
    for platform, post_id in results.items():
        status = f"✅ post_id={post_id}" if post_id else "❌ Failed"
        print(f"  {platform.upper():12} {status}")
