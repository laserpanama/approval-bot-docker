# Run Approval Bot Locally (Without Docker)

## Prerequisites

### WSL/Ubuntu
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python, Redis, and dependencies
sudo apt install -y python3 python3-pip python3-venv redis-server

# Verify installations
python3 --version
redis-server --version
```

### Windows (without WSL)
1. Install Python from https://python.org
2. Install Redis for Windows: https://github.com/microsoftarchive/redis/releases
3. Or use WSL (recommended)

## Setup

1. **Navigate to project directory**:
```bash
cd /c/Users/E/approval-bot-docker
```

2. **Run the start script**:
```bash
chmod +x start.sh
./start.sh
```

Or manually:

```bash
# 1. Start Redis
redis-server --daemonize yes

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install redis==5.0.1 openai==1.12.0 anthropic==0.18.1 requests==2.31.0 python-dotenv==1.0.0 schedule==1.2.1
pip install fastapi==0.109.2 uvicorn==0.27.1 python-telegram-bot==20.8 twilio==9.0.0 pydantic==2.6.1

# 4. Export environment variables
export $(grep -v '^#' .env | xargs)

# 5. Start Content Creator (in terminal 1)
cd content-creator/src
python3 creator.py

# 6. Start Approval Bot (in terminal 2)
cd approval-bot/src
python3 bot.py
```

## Test the Bot

1. **Health Check**:
```bash
curl http://localhost:8080/health
```

2. **Send test message to Telegram Bot**:
   - Find your bot on Telegram (using your bot token)
   - Send `/start` command
   - Check logs for connection

3. **Manually add content to queue**:
```bash
redis-cli LPUSH content_queue '{"id":"test-1","hook":"Test hook","caption":"Test caption","topic":"test","persona":"tiktok","hashtags":["test"],"platforms":["instagram"]}'
```

## Troubleshooting

### Permission Denied
```bash
# Fix permissions
chmod +x start.sh

# Or run with bash
bash start.sh
```

### Redis Connection Failed
```bash
# Check if Redis is running
redis-cli ping

# Should return: PONG

# If not running:
redis-server --daemonize yes
```

### Python Module Not Found
```bash
# Make sure virtual environment is active
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

### Port Already in Use
```bash
# Find process using port 8080
lsof -i :8080

# Kill the process
kill -9 <PID>

# Or use different port
export APPROVAL_PORT=8081
```

## File Structure
```
approval-bot-docker/
├── .env                    # Your credentials (already created)
├── start.sh                # One-click start script
├── run-local.md           # This file
├── content-creator/
│   └── src/creator.py     # Content generation agent
└── approval-bot/
    └── src/bot.py         # Telegram/WhatsApp + posting
```

## Next Steps
1. Add Instagram/Facebook/Twitter API tokens to `.env`
2. Configure content personas in `.env` (CREATOR_PERSONA)
3. Test webhook endpoints with ngrok for external access
