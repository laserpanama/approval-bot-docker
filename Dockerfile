FROM python:3.11-slim

# FIX: install cron at BUILD time (not runtime) — faster, cached, reliable
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    unzip \
    cron \
    && curl https://rclone.org/install.sh | bash \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# FIX: copy ALL required files including pipeline_with_approval.py
COPY pipeline.py .
COPY pipeline_with_approval.py .
COPY approval_bot.py .
COPY multi_platform_publisher.py .

# Include the worker and backup modules for the single-container architecture
COPY content-creator/ ./content-creator/
COPY backup-team/ ./backup-team/

COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

RUN mkdir -p /tmp/reel_machine

EXPOSE 8080

CMD ["./entrypoint.sh"]
