#!/bin/bash

echo "🌱 Starting Farm Insights Application..."
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "✗ Virtual environment not found!"
    echo "Please run ./setup.sh first to set up the application."
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

# Check if Flask is installed
python -c "import flask" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "✗ Flask not found!"
    echo "Please run ./setup.sh first to install dependencies."
    exit 1
fi

# Start the Flask application
echo "✓ Starting Flask server on http://localhost:5000"
echo "Press Ctrl+C to stop the server"
echo ""
python app.py
