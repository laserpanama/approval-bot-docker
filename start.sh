#!/bin/bash
# Start Approval Bot locally without Docker

set -e

echo "================================"
echo "Approval Bot - Local Runner"
echo "================================"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if running in WSL
if grep -q Microsoft /proc/version; then
    echo -e "${GREEN}Running in WSL detected${NC}"
    IS_WSL=true
else
    IS_WSL=false
fi

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check prerequisites
echo -e "\n${YELLOW}Checking prerequisites...${NC}"

if ! command_exists python3; then
    echo -e "${RED}Error: Python 3 is not installed${NC}"
    echo "Install with: sudo apt update && sudo apt install python3 python3-pip python3-venv"
    exit 1
fi

if ! command_exists redis-server; then
    echo -e "${YELLOW}Redis not found. Installing...${NC}"
    sudo apt update
    sudo apt install -y redis-server
fi

# Check Redis is running
echo -e "\n${YELLOW}Starting Redis...${NC}"
if ! pgrep -x "redis-server" > /dev/null; then
    redis-server --daemonize yes
    echo -e "${GREEN}Redis started${NC}"
else
    echo -e "${GREEN}Redis already running${NC}"
fi

# Create Python virtual environment if not exists
if [ ! -d "venv" ]; then
    echo -e "\n${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv venv
fi

# Activate virtual environment
echo -e "\n${YELLOW}Activating virtual environment...${NC}"
source venv/bin/activate

# Install dependencies
echo -e "\n${YELLOW}Installing dependencies...${NC}"
pip install --upgrade pip

# Install content creator dependencies
echo "Installing content-creator dependencies..."
pip install -q redis==5.0.1 openai==1.12.0 anthropic==0.18.1 requests==2.31.0 python-dotenv==1.0.0 schedule==1.2.1

# Install approval-bot dependencies
echo "Installing approval-bot dependencies..."
pip install -q fastapi==0.109.2 uvicorn==0.27.1 redis==5.0.1 requests==2.31.0 python-telegram-bot==20.8 twilio==9.0.0 python-dotenv==1.0.0 pydantic==2.6.1 jinja2==3.1.3

echo -e "${GREEN}All dependencies installed${NC}"

# Export environment variables
echo -e "\n${YELLOW}Loading environment variables...${NC}"
export $(grep -v '^#' .env | xargs)

# Create logs directory
mkdir -p logs

# Function to cleanup on exit
cleanup() {
    echo -e "\n${YELLOW}Shutting down...${NC}"
    if [ -n "$CONTENT_CREATOR_PID" ]; then
        kill $CONTENT_CREATOR_PID 2>/dev/null || true
    fi
    if [ -n "$APPROVAL_BOT_PID" ]; then
        kill $APPROVAL_BOT_PID 2>/dev/null || true
    fi
    echo -e "${GREEN}Cleanup complete${NC}"
}
trap cleanup EXIT

# Start Content Creator in background
echo -e "\n${YELLOW}Starting Content Creator...${NC}"
cd content-creator/src
python3 creator.py &
CONTENT_CREATOR_PID=$!
cd ../..
echo -e "${GREEN}Content Creator started (PID: $CONTENT_CREATOR_PID)${NC}"

# Wait for content creator to initialize
sleep 2

# Start Approval Bot in background
echo -e "\n${YELLOW}Starting Approval Bot...${NC}"
cd approval-bot/src
python3 bot.py &
APPROVAL_BOT_PID=$!
cd ../..
echo -e "${GREEN}Approval Bot started (PID: $APPROVAL_BOT_PID)${NC}"

echo -e "\n================================"
echo -e "${GREEN}All services started!${NC}"
echo "================================"
echo ""
echo "Services running:"
echo "  - Redis: localhost:6379"
echo "  - Approval Bot: http://localhost:8080"
echo "  - Telegram Bot: @your_bot"
echo ""
echo "To test:"
echo "  - Health check: curl http://localhost:8080/health"
echo "  - Telegram: Send message to your bot"
echo ""
echo "Press Ctrl+C to stop all services"
echo "================================"

# Wait for both processes
wait
