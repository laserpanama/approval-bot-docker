#!/bin/bash
set -e

echo "🍽️  Food Reel Machine starting..."
echo "   Timezone: $(date)"
echo "   TZ env: ${TZ:-not set}"
echo "   Redis: ${REDIS_URL:-redis://redis:6379/0}"

# Wait for Redis to be ready
echo "⏳ Waiting for Redis..."
until python3 -c "import redis; redis.from_url('${REDIS_URL:-redis://redis:6379/0}').ping()" 2>/dev/null; do
  sleep 2
done
echo "✅ Redis is up"

# Clear crontab first to prevent job accumulation on container restart
crontab -r 2>/dev/null || true

# Write fresh cron jobs (Panama time = UTC-5, TZ set in docker-compose)
{
  echo "0 9  * * * python3 /app/pipeline.py >> /tmp/reel_machine/cron.log 2>&1"
  echo "0 14 * * * python3 /app/pipeline.py >> /tmp/reel_machine/cron.log 2>&1"
  echo "0 19 * * * python3 /app/pipeline.py >> /tmp/reel_machine/cron.log 2>&1"
} | crontab -

# Export env vars to cron (cron doesn't inherit them by default)
env | grep -E 'METRICOOL|TELEGRAM|TWILIO|PUBLIC_BASE|INSTAGRAM|WHATSAPP|SHEETS|REDIS|APPROVAL|OPENAI|ANTHROPIC' >> /etc/environment

# Start cron daemon
service cron start
echo "✅ Cron jobs scheduled (9am, 2pm, 7pm Panama time)"

# Start approval bot (blocks — keeps container alive)
echo "✅ Starting approval bot on port 8080..."
python3 /app/approval_bot.py
