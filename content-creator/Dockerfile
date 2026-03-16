FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY src/ ./src/
COPY prompts/ ./prompts/
COPY templates/ ./templates/

# Create logs directory
RUN mkdir -p /app/logs

# Run the creator service
CMD ["python", "-u", "src/creator.py"]
