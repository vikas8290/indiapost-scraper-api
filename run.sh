#!/usr/bin/env bash
set -e

# Navigate to script directory
cd "$(dirname "$0")"

# Check if venv exists, if not create it
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

echo "Activating virtual environment..."
source venv/bin/activate

echo "Installing/Updating dependencies..."
pip install -r requirements.txt

# Create .env if not exists
if [ ! -f ".env" ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
fi

echo "Starting India Post Tracker API on http://127.0.0.1:8000..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
