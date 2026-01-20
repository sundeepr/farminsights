# Farm Insights - Plant Health Dashboard

A Flask web application for displaying plant health analysis reports with an interactive dashboard.

## Features

- **Interactive Satellite Map** - View your plants on a real satellite imagery map
- **Heatmap Overlay** - Visual heat map showing plant health issues at a glance
- **Color-Coded Markers** - Instantly identify healthy vs stressed plants
  - Green = Good health (75-100)
  - Orange = Fair health (65-74)
  - Red = Poor health (0-64)
  - Grey = Unknown/Error
- **Layer Control** - Switch between satellite and street map views
- **Advanced Zoom Controls** - Zoom to individual plants or view all at once
- **Filter & Search** - Filter by health status and search by image name
- **Real-time Statistics** - View average health scores and analysis counts
- **Detailed Popups** - Click any marker for comprehensive plant analysis:
  - Health scores and status
  - Issues detected
  - Recommended interventions
  - GPS coordinates and timestamps
- **Synchronized UI** - Click markers or sidebar items for seamless navigation
- **Responsive Scrolling** - Smooth scrolling through all plant data

## Quick Start (Easiest Method)

```bash
# Run the setup script (one-time setup)
./setup.sh

# Run the application
./run.sh
```

Then open your browser to `http://localhost:5000`

## Manual Installation

You have several options to install the required dependencies:

### Option 1: Using a Virtual Environment (Recommended)

```bash
# Create a virtual environment
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Option 2: Using pipx and venv

```bash
# Install in a virtual environment (automatically managed)
python3 -m venv venv
source venv/bin/activate
pip install Flask
```

### Option 3: System-wide Installation (Use with caution)

```bash
# Use --break-system-packages flag (not recommended)
pip install -r requirements.txt --break-system-packages

# OR use apt (Debian/Ubuntu)
sudo apt install python3-flask
```

## Running the Application

1. If using a virtual environment, make sure it's activated:
```bash
source venv/bin/activate
```

2. Start the Flask server:
```bash
python app.py
# OR
python3 app.py
```

3. Open your web browser and navigate to:
```
http://localhost:5000
```

The application will be running on port 5000 by default.

4. To stop the server, press `Ctrl+C` in the terminal.

5. To deactivate the virtual environment when done:
```bash
deactivate
```

## Project Structure

```
farmInsights/
├── app.py                                      # Flask application
├── requirements.txt                            # Python dependencies
├── plant_health_report_2026-01-13_22-40-05.json  # Plant health data
├── templates/
│   └── index.html                              # Main dashboard template
└── static/                                      # Static files (if needed)
```

## API Endpoints

- `GET /` - Main dashboard page
- `GET /api/data` - Returns plant health data in JSON format

## Configuration

The Flask app runs with the following default settings:
- Host: `0.0.0.0` (accessible from network)
- Port: `5000`
- Debug mode: `True` (disable in production)

To change these settings, modify the `app.run()` parameters in [app.py](app.py).

## Data Format

The application expects a JSON file named `plant_health_report_2026-01-13_22-40-05.json` in the root directory with the following structure:

```json
{
  "report_metadata": {
    "generated_at": "timestamp",
    "model_used": "model_name",
    "total_images": 0,
    "successful_analyses": 0
  },
  "images": [
    {
      "image_name": "filename",
      "timestamp": "timestamp",
      "gps_coordinates": {...},
      "plant_health_analysis": {...}
    }
  ]
}
```

## License

MIT License
