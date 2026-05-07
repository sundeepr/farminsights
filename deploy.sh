#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "Pulling latest changes..."
git pull

echo "Installing dependencies..."
source venv/bin/activate
pip install -r requirements.txt -q

echo "Restarting service..."
sudo systemctl restart farminsights

echo "Status:"
sudo systemctl status farminsights --no-pager -l
