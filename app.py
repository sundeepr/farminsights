from flask import Flask, render_template, jsonify, send_from_directory
import json
import os
import glob

app = Flask(__name__)

# Configure the app
app.config['JSON_SORT_KEYS'] = False

@app.route('/')
def index():
    """Render the main page"""
    return render_template('index.html')

@app.route('/api/files')
def get_files():
    """API endpoint to list available data files"""
    data_files = glob.glob('data/*.json')
    files = []
    for f in sorted(data_files, reverse=True):
        filename = os.path.basename(f)
        # Extract a readable display name from the filename
        display_name = filename.replace('.json', '').replace('_', ' ').replace('-', '/')
        files.append({'filename': filename, 'display': display_name})
    return jsonify(files)

@app.route('/api/data')
@app.route('/api/data/<filename>')
def get_data(filename=None):
    """API endpoint to get plant health data"""
    if filename is None:
        # Get the most recent file by default
        data_files = glob.glob('data/*.json')
        if not data_files:
            return jsonify({'error': 'No data files found'}), 404
        filename = os.path.basename(sorted(data_files, reverse=True)[0])

    filepath = os.path.join('data', filename)
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        return jsonify(data)
    except FileNotFoundError:
        return jsonify({'error': 'Data file not found'}), 404
    except json.JSONDecodeError:
        return jsonify({'error': 'Invalid JSON data'}), 500

@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serve static files"""
    return send_from_directory('static', filename)

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    # Run the app in debug mode
    app.run(debug=True, host='0.0.0.0', port=5000)
