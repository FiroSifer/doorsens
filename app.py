from flask import Flask, jsonify, render_template

app = Flask(__name__, static_folder='static', template_folder='templates')

@app.route('/')
def index():
    """Serves the main HTML file which contains all the UI and logic."""
    return render_template('index.html')

@app.route('/api/scan', methods=['POST'])
def scan():
    """
    MOCK SCAN: Returns an empty list. 
    The UI will correctly show the 'Awaiting Visual Input' radar.
    """
    return jsonify([])

@app.route('/api/register', methods=['POST'])
def register():
    """
    MOCK REGISTER: Returns an error message.
    The UI will display this message to the user.
    """
    return jsonify({"status": "error", "message": "Functionality disabled in UI-only mode."})

@app.route('/api/database')
def database():
    """
    MOCK DATABASE: Returns an empty list.
    The UI will correctly show 'Database is empty.'
    """
    return jsonify([])

@app.route('/api/database/<name>', methods=['DELETE'])
def delete_db_person(name):
    """MOCK DELETE: Returns a success message so the UI can update."""
    return jsonify({"status": "success"})

# The /video_feed endpoint is completely removed.

if __name__ == '__main__':
    app.run(debug=True, port=5000)