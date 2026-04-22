import sys 
import cv2
import threading
import face_recognition
import sqlite3
import numpy as np
import base64
from datetime import datetime
from flask import Flask, jsonify, request, Response, render_template

app = Flask(__name__)

# ==========================================
# 1. CAMERA LOGIC
# ==========================================
_cap = None
_lock = threading.Lock()

def init_camera():
    """Starts the camera in the background so it's ready instantly for the UI."""
    global _cap
    print("[INFO] Warming up camera... Please wait.")
    
    with _lock:
        # cv2.CAP_DSHOW fixes the 5-15 second delay on Windows.
        # On Mac/Linux, standard VideoCapture is usually fast enough.
        if sys.platform.startswith('win'):
            _cap = cv2.VideoCapture(0, cv2.CAP_DSHOW) 
        else:
            _cap = cv2.VideoCapture(1)
            
        _cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        _cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        # Read a dummy frame to force the hardware to initialize immediately
        _cap.read()
        
    print("[INFO] Camera is ready!")

# Start the camera in a background thread the moment the app starts
threading.Thread(target=init_camera, daemon=True).start()

def get_live_frame():
    global _cap
    with _lock:
        if _cap is None or not _cap.isOpened():
            return None # Return None if camera is still warming up
            
        ret, frame = _cap.read()
        
    if ret and frame is not None:
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return None

def take_snapshot():
    return get_live_frame()

# ==========================================
# 2. RECOGNITION LOGIC
# ==========================================

def extract_all_faces(image_rgb, expand_ratio=0.4): # <-- Changed 0.2 to 0.4
    # Get the height and width of the original image
    img_height, img_width = image_rgb.shape[:2]
    
    locs = face_recognition.face_locations(image_rgb, model="hog")
    faces = []
    
    for t, r, b, l in locs:
        # Calculate width and height of the detected face
        face_height = b - t
        face_width = r - l
        
        # Calculate how many pixels to add based on the ratio
        margin_y = int(face_height * expand_ratio)
        margin_x = int(face_width * expand_ratio)
        
        # Expand the bounding box
        new_t = t - margin_y
        new_b = b + margin_y
        new_l = l - margin_x
        new_r = r + margin_x
        
        # Safety check: clamp values to image boundaries
        new_t = max(0, new_t)
        new_b = min(img_height, new_b)
        new_l = max(0, new_l)
        new_r = min(img_width, new_r)
        
        faces.append(image_rgb[new_t:new_b, new_l:new_r].copy())
        
    return faces

# ==========================================
# 3. DATABASE LOGIC (Thread-Safe Fixes)
# ==========================================
DB_NAME = "faces.db"

def init_db():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS people (name TEXT, encoding BLOB)")
        conn.commit()
    finally:
        conn.close()

def load_everything():
    init_db()
    names, encodings = [], []
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    try:
        for name, blob in conn.execute("SELECT name, encoding FROM people"):
            names.append(name)
            encodings.append(np.frombuffer(blob, dtype=np.float64))
    finally:
        conn.close()
    return names, encodings

def save_person(name, face_image):
    if face_image is None or face_image.size == 0:
        return False
        
    # FIX: Since face_image is ALREADY cropped exactly to the face, 
    # we explicitly tell face_encodings the box size so it doesn't fail.
    h, w = face_image.shape[:2]
    known_box = [(0, w, h, 0)]
    
    enc = face_recognition.face_encodings(face_image, known_face_locations=known_box)
    
    if enc:
        encoding_blob = enc[0].tobytes()
        conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        try:
            conn.execute("INSERT INTO people (name, encoding) VALUES (?, ?)", (name, encoding_blob))
            conn.commit()
        finally:
            conn.close()
        return True
    return False

def identify(face_image, known_names, known_encodings):
    current_enc = face_recognition.face_encodings(face_image)
    if not current_enc or not known_encodings:
        return "Unknown Visitor"
    
    matches = face_recognition.compare_faces(known_encodings, current_enc[0], tolerance=0.5)
    if True in matches:
        first_match_index = matches.index(True)
        return known_names[first_match_index]
    return "Unknown Visitor"

def delete_person(name):
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    try:
        conn.execute("DELETE FROM people WHERE name=?", (name,))
        conn.commit()
    finally:
        conn.close()

# ==========================================
# 4. FLASK API ROUTES
# ==========================================
app_state = {
    "total": 0,
    "verified": 0,
    "unknown": 0,
    "activity": [],
    "last_scan_faces": []
}

init_db()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/stats')
def stats():
    names, _ = load_everything()
    return jsonify({
        "db_count": len(names),
        "total": app_state["total"],
        "verified": app_state["verified"],
        "unknown": app_state["unknown"],
        "activity": app_state["activity"][::-1][:10]
    })

@app.route('/api/scan', methods=['POST'])
def scan():
    frame = take_snapshot()
    if frame is None:
        return jsonify({"error": "Camera error"}), 500
    
    names, encodings = load_everything()
    faces = extract_all_faces(frame)
    app_state["last_scan_faces"] = faces
    
    results = []
    now = datetime.now()
    
    for face_img in faces:
        name = identify(face_img, names, encodings)
        is_known = (name != "Unknown Visitor")
        
        try:
            bgr_face = cv2.cvtColor(face_img, cv2.COLOR_RGB2BGR)
            ret, buffer = cv2.imencode('.jpg', bgr_face)
            b64_image = base64.b64encode(buffer).decode('utf-8') if ret else ""
        except Exception:
            b64_image = ""
        
        res = {
            "image": b64_image,
            "name": name,
            "uid": f"UID-{abs(hash(name)) % 10000:04d}" if is_known else "UNKNOWN",
            "timestamp": now.strftime("%H:%M:%S"),
            "date": now.strftime("%Y-%m-%d"),
            "conf": 85 if is_known else 10,
            "verified": is_known,
            "faces_total": len(faces)
        }
        results.append(res)
        
        app_state["total"] += 1
        if is_known: app_state["verified"] += 1
        else: app_state["unknown"] += 1
        app_state["activity"].append(res)
    
    return jsonify(results)

@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.json
        name = data.get("name")
        face_img = None
        
        if not name:
            return jsonify({"status": "error", "message": "Name is required."})
        
        # 1. Registration from Scan Results
        if "index" in data:
            idx = int(data["index"])
            if idx >= len(app_state["last_scan_faces"]):
                return jsonify({"status": "error", "message": "Face data lost from memory. Please rescan."})
            face_img = app_state["last_scan_faces"][idx]
        
        # 2. Registration from Manual Import File
        elif "image" in data:
            img_data_str = data["image"]
            if ',' in img_data_str:
                img_data_str = img_data_str.split(',')[1]
                
            img_data = base64.b64decode(img_data_str)
            np_arr = np.frombuffer(img_data, np.uint8)
            bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            
            if bgr is None:
                return jsonify({"status": "error", "message": "Invalid or corrupted image file."})
                
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            faces = extract_all_faces(rgb)
            
            if not faces:
                return jsonify({"status": "error", "message": "No faces detected in the uploaded image."})
            face_img = faces[0]
            
        if face_img is None:
            return jsonify({"status": "error", "message": "No valid face image provided."})
        
        success = save_person(name, face_img)
        if success:
            return jsonify({"status": "success", "id": name})
        return jsonify({"status": "error", "message": "Could not extract facial data. Try a clearer image."})
        
    except Exception as e:
        # If it crashes, it will safely return the exact error message to the UI instead of breaking
        print("Backend Crash:", str(e))
        return jsonify({"status": "error", "message": f"Server processing error: {str(e)}"})

@app.route('/api/database')
def database():
    names, _ = load_everything()
    res = [{"name": n, "id": n, "added": "N/A"} for n in names]
    return jsonify(res)

@app.route('/api/database/search')
def database_search():
    q = request.args.get('q', '').lower()
    names, _ = load_everything()
    res = [{"name": n, "id": n, "added": "N/A"} for n in names if q in n.lower()]
    return jsonify(res)

@app.route('/api/database/<id>', methods=['DELETE'])
def delete_db_person(id):
    delete_person(id)
    return jsonify({"status": "success"})

def gen_frames():
    while True:
        frame = get_live_frame()
        if frame is not None:
            bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            ret, buffer = cv2.imencode('.jpg', bgr)
            if ret:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    # use_reloader=False stops Flask from crashing interactive environments
    app.run(debug=True, use_reloader=False, threaded=True, host='0.0.0.0', port=5000)