#!/bin/bash

echo "🌱 Farm Insights Setup Script"
echo "=============================="
echo ""

# Check if virtual environment already exists
if [ -d "venv" ]; then
    echo "✓ Virtual environment already exists"
else
    echo "Creating virtual environment..."
    python3 -m venv venv
    if [ $? -eq 0 ]; then
        echo "✓ Virtual environment created"
    else
        echo "✗ Failed to create virtual environment"
        exit 1
    fi
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ Setup complete!"
    echo ""
    echo "To run the application:"
    echo "  1. Activate the virtual environment: source venv/bin/activate"
    echo "  2. Start the server: python app.py"
    echo "  3. Open http://localhost:5000 in your browser"
    echo ""
else
    echo "✗ Failed to install dependencies"
    exit 1
fi
