FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY src/ ./src/
COPY templates/ ./templates/

# Create directories
RUN mkdir -p /app/logs /app/webhooks /app/videos

EXPOSE 8080

# Run the approval bot service
CMD ["python", "-u", "src/bot.py"]
