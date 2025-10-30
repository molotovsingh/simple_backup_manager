#!/bin/bash

# Job Restart Manager - Startup Script

echo "🚀 Starting Job Restart Manager..."

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed."
    exit 1
fi

# Check if we're in the right directory
if [ ! -f "app.py" ]; then
    echo "❌ Please run this script from the job-restart-manager directory"
    exit 1
fi

# Install dependencies if needed
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

echo "📦 Activating virtual environment..."
source venv/bin/activate

echo "📦 Installing dependencies..."
pip install -r requirements.txt

echo "🌐 Starting web application..."
echo "📱 Open http://localhost:5000 in your browser"
echo "🛑 Press Ctrl+C to stop the server"
echo ""

python app.py
