#!/usr/bin/env python3
"""
Approval Bot - HTTP server + Telegram + WhatsApp integration
Receives webhooks, sends for approval, posts to Instagram/Facebook/Twitter
"""

import os
import json
import asyncio
import redis
import requests
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from twilio.rest import Client as TwilioClient
import uvicorn
from pydantic import BaseModel
import threading
import schedule
import time

app = FastAPI(title="Reel Approval Bot")

class MultiPlatformPoster:
    """Posts content to Instagram, Facebook, and Twitter"""

    def __init__(self):
        # Instagram Basic Display API
        self.ig_access_token = os.getenv('INSTAGRAM_ACCESS_TOKEN')
        self.ig_account_id = os.getenv('INSTAGRAM_ACCOUNT_ID')

        # Facebook Graph API
        self.fb_access_token = os.getenv('FACEBOOK_ACCESS_TOKEN')
        self.fb_page_id = os.getenv('FACEBOOK_PAGE_ID')

        # Twitter API v2
        self.twitter_bearer = os.getenv('TWITTER_BEARER_TOKEN')
        self.twitter_api_key = os.getenv('TWITTER_API_KEY')
        self.twitter_api_secret = os.getenv('TWITTER_API_SECRET')
        self.twitter_access_token = os.getenv('TWITTER_ACCESS_TOKEN')
        self.twitter_access_secret = os.getenv('TWITTER_ACCESS_SECRET')

        # Metricool (optional - can post to all platforms)
        self.metricool_token = os.getenv('METRICOOL_TOKEN')
        self.metricool_user_id = os.getenv('METRICOOL_USER_ID')

    def post_to_instagram(self, hook_data: dict) -> bool:
        """Post to Instagram via Graph API"""
        if not all([self.ig_access_token, self.ig_account_id]):
            print("Instagram credentials not configured")
            return False

        try:
            # For Reels, we'd need a video URL
            # This is a simplified version - real implementation needs video upload flow
            caption = f"{hook_data['hook']}\n\n{hook_data['caption']}"
            hashtags = ' '.join([f"#{tag}" for tag in hook_data['hashtags']])
            full_caption = f"{caption}\n\n{hashtags}"

            # Using Instagram Graph API to create a container
            # Note: Actual video upload requires additional steps
            url = f"https://graph.facebook.com/v18.0/{self.ig_account_id}/media"
            params = {
                'caption': full_caption,
                'access_token': self.ig_access_token
            }

            response = requests.post(url, params=params)
            result = response.json()

            if 'id' in result:
                print(f"Instagram container created: {result['id']}")
                return True
            else:
                print(f"Instagram API error: {result}")
                return False

        except Exception as e:
            print(f"Failed to post to Instagram: {e}")
            return False

    def post_to_facebook(self, hook_data: dict) -> bool:
        """Post to Facebook Page via Graph API"""
        if not all([self.fb_access_token, self.fb_page_id]):
            print("Facebook credentials not configured")
            return False

        try:
            caption = f"{hook_data['hook']}\n\n{hook_data['caption']}"
            hashtags = ' '.join([f"#{tag}" for tag in hook_data['hashtags']])
            message = f"{caption}\n\n{hashtags}"

            url = f"https://graph.facebook.com/v18.0/{self.fb_page_id}/feed"
            params = {
                'message': message,
                'access_token': self.fb_access_token
            }

            response = requests.post(url, params=params)
            result = response.json()

            if 'id' in result:
                print(f"Posted to Facebook: {result['id']}")
                return True
            else:
                print(f"Facebook API error: {result}")
                return False

        except Exception as e:
            print(f"Failed to post to Facebook: {e}")
            return False

    def post_to_twitter(self, hook_data: dict) -> bool:
        """Post to Twitter/X via API v2"""
        if not all([self.twitter_bearer, self.twitter_api_key, self.twitter_access_token]):
            print("Twitter credentials not configured")
            return False

        try:
            # Build tweet text (max 280 chars)
            text = hook_data['hook']
            if len(text) > 240:  # Leave room for hashtags
                text = text[:237] + "..."

            hashtags = ' '.join([f"#{tag}" for tag in hook_data['hashtags'][:3]])
            tweet_text = f"{text}\n\n{hashtags}"

            # Twitter API v2 endpoint
            url = "https://api.twitter.com/2/tweets"
            headers = {
                "Authorization": f"Bearer {self.twitter_bearer}",
                "Content-Type": "application/json"
            }
            payload = {"text": tweet_text}

            response = requests.post(url, headers=headers, json=payload)

            if response.status_code == 201:
                print(f"Posted to Twitter: {response.json()['data']['id']}")
                return True
            else:
                print(f"Twitter API error: {response.text}")
                return False

        except Exception as e:
            print(f"Failed to post to Twitter: {e}")
            return False

    def post_via_metricool(self, hook_data: dict, platforms: List[str]) -> dict:
        """Post via Metricool API (supports multiple platforms)"""
        if not all([self.metricool_token, self.metricool_user_id]):
            print("Metricool credentials not configured")
            return {}

        try:
            url = "https://metricool.com/api/v2/planning"
            headers = {
                "Authorization": f"Bearer {self.metricool_token}",
                "Content-Type": "application/json"
            }

            text = f"{hook_data['hook']}\n\n{hook_data['caption']}"
            hashtags = ' '.join([f"#{tag}" for tag in hook_data['hashtags']])
            full_text = f"{text}\n\n{hashtags}"

            payload = {
                "userId": self.metricool_user_id,
                "text": full_text,
                "platforms": platforms,  # ["instagram", "facebook", "twitter", "tiktok"]
                "scheduledTime": datetime.now().isoformat()
            }

            response = requests.post(url, headers=headers, json=payload)
            result = response.json()

            print(f"Metricool response: {result}")
            return result

        except Exception as e:
            print(f"Failed to post via Metricool: {e}")
            return {}

    def post_to_tiktok(self, hook_data: dict) -> bool:
        """Post to TikTok via unofficial API or scheduling service"""
        # TikTok doesn't have a public posting API for regular accounts
        # Options:
        # 1. Use a service like Metricool (already supported above)
        # 2. Use TikTok for Business API (requires approval)
        # 3. Use browser automation (not recommended)

        print("TikTok posting: Use Metricool integration or manual upload")
        print(f"Caption ready for TikTok: {hook_data['hook']}")

        # If using Metricool, TikTok can be included in the platforms list
        if self.metricool_token:
            return True  # Handled via Metricool

        return False

class ApprovalBot:
    def __init__(self):
        self.redis_client = redis.from_url(
            os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
            decode_responses=True
        )

        # Initialize clients
        self.telegram_bot = Bot(token=os.getenv('TELEGRAM_BOT_TOKEN'))
        self.twilio = TwilioClient(
            os.getenv('TWILIO_ACCOUNT_SID'),
            os.getenv('TWILIO_AUTH_TOKEN')
        )
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.whatsapp_from = os.getenv('TWILIO_WA_FROM')
        self.whatsapp_to = os.getenv('TWILIO_WA_TO')
        self.public_url = os.getenv('PUBLIC_BASE_URL', 'http://localhost:8080')

        # Platform poster
        self.poster = MultiPlatformPoster()
        self.default_platforms = os.getenv('DEFAULT_PLATFORMS', 'instagram').split(',')

        self.pending_approvals = {}  # In-memory storage for simplicity

    def get_pending_hook(self) -> Optional[dict]:
        """Get next hook from Redis queue"""
        try:
            data = self.redis_client.brpop('pending_hooks', timeout=5)
            if data:
                return json.loads(data[1])
        except Exception as e:
            print(f"Error getting pending hook: {e}")
        return None

    def store_approval(self, hook_id: str, hook_data: dict):
        """Store hook awaiting approval"""
        self.pending_approvals[hook_id] = {
            **hook_data,
            'requested_at': datetime.now().isoformat()
        }

    async def send_telegram_approval(self, hook_data: dict):
        """Send approval request via Telegram with platform selection"""
        hook_id = hook_data['id']
        self.store_approval(hook_id, hook_data)

        # Platform-specific approval URLs
        ig_url = f"{self.public_url}/approve/{hook_id}?platforms=instagram"
        fb_url = f"{self.public_url}/approve/{hook_id}?platforms=facebook"
        tw_url = f"{self.public_url}/approve/{hook_id}?platforms=twitter"
        tt_url = f"{self.public_url}/approve/{hook_id}?platforms=tiktok"
        all_url = f"{self.public_url}/approve/{hook_id}?platforms=instagram,facebook,twitter,tiktok"
        reject_url = f"{self.public_url}/reject/{hook_id}"

        keyboard = [
            [
                InlineKeyboardButton("Instagram", url=ig_url),
                InlineKeyboardButton("Facebook", url=fb_url)
            ],
            [
                InlineKeyboardButton("Twitter/X", url=tw_url),
                InlineKeyboardButton("TikTok", url=tt_url)
            ],
            [
                InlineKeyboardButton("All Platforms", url=all_url),
                InlineKeyboardButton("Reject", url=reject_url)
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        message = f"""New Content Ready for Approval

Hook: {hook_data['hook']}
Topic: {hook_data['topic']}
Persona: {hook_data['persona']}

Caption preview:
{hook_data['caption'][:200]}...

Select platform to post:"""

        try:
            await self.telegram_bot.send_message(
                chat_id=self.telegram_chat_id,
                text=message,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
            print(f"Sent Telegram approval request for {hook_id}")
        except Exception as e:
            print(f"Failed to send Telegram: {e}")

    def send_whatsapp_approval(self, hook_data: dict):
        """Send approval request via WhatsApp"""
        hook_id = hook_data['id']
        all_url = f"{self.public_url}/approve/{hook_id}?platforms=instagram,facebook,twitter,tiktok"
        reject_url = f"{self.public_url}/reject/{hook_id}"

        message = f"""New Content for Approval

Hook: {hook_data['hook']}
Topic: {hook_data['topic']}

Post to all platforms:
{all_url}

Reject: {reject_url}"""

        try:
            self.twilio.messages.create(
                from_=self.whatsapp_from,
                to=self.whatsapp_to,
                body=message
            )
            print(f"Sent WhatsApp approval request for {hook_id}")
        except Exception as e:
            print(f"Failed to send WhatsApp: {e}")

    def post_to_platforms(self, hook_data: dict, platforms: List[str] = None) -> dict:
        """Post approved content to selected platforms"""
        if platforms is None:
            platforms = self.default_platforms

        results = {}

        # Try Metricool first (supports multiple platforms)
        if self.poster.metricool_token:
            print("Using Metricool for multi-platform posting...")
            metricool_result = self.poster.post_via_metricool(hook_data, platforms)
            results['metricool'] = metricool_result

            if metricool_result:
                hook_data['posted_via'] = 'metricool'
                hook_data['platforms'] = platforms
                self.redis_client.lpush('approved_hooks', json.dumps(hook_data))
                return {'success': True, 'platforms': platforms, 'via': 'metricool'}

        # Fallback to individual APIs
        print("Falling back to individual platform APIs...")
        for platform in platforms:
            platform = platform.strip().lower()

            if platform == 'instagram':
                results['instagram'] = self.poster.post_to_instagram(hook_data)
            elif platform == 'facebook':
                results['facebook'] = self.poster.post_to_facebook(hook_data)
            elif platform == 'twitter':
                results['twitter'] = self.poster.post_to_twitter(hook_data)
            elif platform == 'tiktok':
                results['tiktok'] = self.poster.post_to_tiktok(hook_data)

        # Check if any succeeded
        any_success = any(results.values())

        if any_success:
            hook_data['posted_via'] = 'direct_api'
            hook_data['platforms'] = [p for p, success in results.items() if success]
            self.redis_client.lpush('approved_hooks', json.dumps(hook_data))

        return {
            'success': any_success,
            'platforms': platforms,
            'results': results,
            'via': 'direct_api'
        }

    def log_activity(self, message: str):
        """Log activity to file"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open('/app/logs/bot.log', 'a') as f:
            f.write(f"[{timestamp}] {message}\n")

# Initialize bot
bot = ApprovalBot()

@app.get("/", response_class=HTMLResponse)
async def index():
    """Health check / status page"""
    return """
    <html>
        <head><title>Reel Approval Bot</title></head>
        <body>
            <h1>Reel Approval Bot</h1>
            <p>Status: Running</p>
            <p><a href="/health">Health Check</a></p>
        </body>
    </html>
    """

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "pending_approvals": len(bot.pending_approvals),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/approve/{hook_id}")
async def approve(hook_id: str, platforms: str = None):
    """Approve endpoint - called when user clicks approve

    Args:
        platforms: Comma-separated list of platforms (instagram,facebook,twitter,tiktok)
    """
    if hook_id not in bot.pending_approvals:
        raise HTTPException(status_code=404, detail="Hook not found or already processed")

    hook_data = bot.pending_approvals.pop(hook_id)
    hook_data['approved_at'] = datetime.now().isoformat()
    hook_data['status'] = 'approved'

    # Parse platforms from query param or use defaults
    if platforms:
        platform_list = [p.strip() for p in platforms.split(',')]
    else:
        platform_list = bot.default_platforms

    # Post to selected platforms
    result = bot.post_to_platforms(hook_data, platform_list)

    if result['success']:
        posted_to = ', '.join(result.get('platforms', platform_list))
        bot.log_activity(f"Approved and posted to {posted_to}: {hook_id}")
        return {
            "status": "success",
            "message": f"Content approved and posted to {posted_to}",
            "hook": hook_data['hook'],
            "platforms": result.get('platforms', []),
            "via": result.get('via', 'unknown')
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to post to any platform")

@app.get("/reject/{hook_id}")
async def reject(hook_id: str):
    """Reject endpoint - called when user clicks reject"""
    if hook_id not in bot.pending_approvals:
        raise HTTPException(status_code=404, detail="Hook not found or already processed")

    hook_data = bot.pending_approvals.pop(hook_id)
    hook_data['rejected_at'] = datetime.now().isoformat()
    hook_data['status'] = 'rejected'

    # Store in rejected queue for analytics
    bot.redis_client.lpush('rejected_hooks', json.dumps(hook_data))

    bot.log_activity(f"Rejected: {hook_id}")

    return {
        "status": "rejected",
        "message": "Content rejected",
        "hook": hook_data['hook']
    }

@app.get("/queue/stats")
async def queue_stats():
    """Get queue statistics"""
    pending = bot.redis_client.llen('pending_hooks')
    approved = bot.redis_client.llen('approved_hooks')
    rejected = bot.redis_client.llen('rejected_hooks')

    return {
        "pending": pending,
        "approved": approved,
        "rejected": rejected,
        "awaiting_manual_approval": len(bot.pending_approvals)
    }

# Background worker to check for new hooks and send for approval
def background_worker():
    """Background thread to process new hooks"""
    print("Background worker started")

    while True:
        try:
            hook = bot.get_pending_hook()
            if hook:
                print(f"Found new hook: {hook['id']}")

                # Send for approval
                asyncio.run(bot.send_telegram_approval(hook))
                bot.send_whatsapp_approval(hook)

                bot.log_activity(f"Sent for approval: {hook['id']}")
        except Exception as e:
            print(f"Worker error: {e}")

        time.sleep(5)  # Check every 5 seconds

# Start background worker on startup
@app.on_event("startup")
async def startup_event():
    """Start background worker on startup"""
    thread = threading.Thread(target=background_worker, daemon=True)
    thread.start()
    print("Approval Bot started")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
