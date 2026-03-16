# Approval Bot Docker - Instagram Reels with AI Team

Multi-agent Docker setup for automated social media content with human approval via Telegram/WhatsApp.

Supports: **Instagram, Facebook, Twitter/X, TikTok**

## Architecture

```
Content Creator (TikTok/Growth Persona)
           ↓
     Redis Queue
           ↓
Approval Bot (Telegram/WhatsApp webhooks)
           ↓
    You Approve → Select Platform
           ↓
    Instagram | Facebook | Twitter | TikTok

+ Backup Team (Redis backup, health monitoring)
```

## Services

| Service | Description |
|---------|-------------|
| `content-creator` | Generates hooks/captions (TikTok/Growth/Content personas) |
| `redis` | Message broker between services |
| `approval-bot` | HTTP server + Telegram/WhatsApp integration |
| `backup-agent` | Daily Redis backups with retention |
| `health-monitor` | Watches all services, alerts on issues |
| `community-manager` | (Optional) Replies to comments/DMs |

## Supported Platforms

| Platform | Method | Notes |
|----------|--------|-------|
| **Instagram** | Graph API | Reels, Stories, Feed posts |
| **Facebook** | Graph API | Page posts |
| **Twitter/X** | API v2 | Tweets with hashtags |
| **TikTok** | Metricool | No direct API, use Metricool |

**Recommendation**: Use Metricool (one API key posts to all platforms)

## Quick Start

### 1. Configure Environment

```bash
cp .env.example .env
nano .env  # Add your tokens
```

### 2. Build & Run

```bash
docker-compose up -d
```

### 3. Check Status

```bash
docker-compose logs -f approval-bot
```

## Configuration

### Required

```env
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx
TWILIO_ACCOUNT_SID=xxx
TWILIO_AUTH_TOKEN=xxx
INSTAGRAM_USERNAME=xxx
INSTAGRAM_PASSWORD=xxx
```

### Optional

```env
CREATOR_PERSONA=tiktok_strategist  # tiktok_strategist | growth_hacker | content_creator
GENERATE_INTERVAL=3600             # Seconds between content generation
CONTENT_LANGUAGE=es                  # es | en
BACKUP_INTERVAL=86400                # Daily backup
BACKUP_RETENTION_DAYS=7
```

## Personas

Switch content creator persona via `CREATOR_PERSONA`:

- **`tiktok_strategist`** - Viral, fast-paced, trend-savvy (Spanish: "Estratega de TikTok")
- **`growth_hacker`** - Data-driven, psychological triggers (Spanish: "Growth Hacker")
- **`content_creator`** - Storytelling, authentic (Spanish: "Creador de Contenido")

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Status page |
| `GET /health` | Health check |
| `GET /approve/{id}` | Approve & post (called by Telegram/WhatsApp buttons) |
| `GET /reject/{id}` | Reject content |
| `GET /queue/stats` | Queue statistics |

## Backup

Backups are stored in `./backups/` as gzip-compressed JSON. Old backups (older than `BACKUP_RETENTION_DAYS`) are auto-deleted.

To restore:

```bash
docker-compose exec backup-agent python -c "
from src.backup import BackupAgent
agent = BackupAgent()
agent.restore_backup('/backups/reel_backup_20240312_120000.json.gz')
"
```

## Monitoring

Set `ALERT_WEBHOOK_URL` to receive alerts via Slack/Discord webhook when:
- Services go down
- Backups fail/succeed
- Queue depth exceeds thresholds

## Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f content-creator
```

Logs are also written to:
- `./content-creator/logs/creator.log`
- `./approval-bot/logs/bot.log`
- `./backup-team/logs/backup.log`

## Scaling

To run multiple content creators with different personas:

```yaml
content-creator-tiktok:
  extends: content-creator
  environment:
    - CREATOR_PERSONA=tiktok_strategist

content-creator-growth:
  extends: content-creator
  environment:
    - CREATOR_PERSONA=growth_hacker
```

## Security

- Never commit `.env` file
- Use Docker secrets for production
- Rotate Instagram credentials regularly
- Telegram webhook tokens should be kept secret

## Troubleshooting

**Bot not sending messages?**
- Check `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`
- Verify bot has permission to message the chat

**WhatsApp not working?**
- Ensure Twilio WhatsApp sandbox is active
- Verify `TWILIO_WA_FROM` uses `whatsapp:+` prefix

**Content not generating?**
- Set `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`
- Check `creator.log` for errors
- Will fallback to templates if AI fails

**Redis connection refused?**
- Ensure Redis container is healthy: `docker-compose ps redis`
- Check `REDIS_URL` format: `redis://redis:6379/0`

## License

MIT
