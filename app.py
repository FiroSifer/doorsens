from flask import Flask, jsonify, render_template

app = Flask(__name__)

@app.route('/')
def index():
    # Serves the visual UI
    return render_template('index.html')

@app.route('/api/scan', methods=['POST'])
def scan():
    # AI/Camera removed. Returns an empty array.
    # The UI will gracefully show the "Awaiting Visual Input" radar screen.
    return jsonify([])

@app.route('/api/register', methods=['POST'])
def register():
    # Database and AI processing removed.
    return jsonify({"status": "error", "message": "Backend AI is disabled in this UI mockup."})

@app.route('/api/database')
def database():
    # Returns an empty list since there is no DB.
    return jsonify([])

@app.route('/api/database/<id>', methods=['DELETE'])
def delete_db_person(id):
    # Dummy delete response
    return jsonify({"status": "success"})

if __name__ == '__main__':
    # Run the lightweight UI server
    app.run(debug=True, port=5000)