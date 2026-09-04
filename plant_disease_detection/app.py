"""
PhytoScan / KRONOS Plant Disease Recognition System (Standalone)
================================================================
Standalone Flask app — imports core logic from disease_engine.py.
Can run independently on its own port, or be imported by kronos_app.py.
"""

import os
import uuid
from pathlib import Path

os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")

from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Import shared engine
from disease_engine import (
    run_diagnostic_pipeline, get_cnn_model, has_gemini_vision,
    get_disease_info, allowed_file, get_status,
    disease_db, _cnn_classes, _cnn_model_name,
    ENGINE_DIR as BASE_DIR,
)

# Environment
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")

# Flask Setup
app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = str(BASE_DIR / "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/", methods=["GET"])
@app.route("/home", methods=["GET"])
@app.route("/disease_detection", methods=["GET"])
def home_page():
    return render_template("disease_detection.html")


@app.route("/predict", methods=["POST"])
@app.route("/analyze", methods=["POST"])
@app.route("/api/predict", methods=["POST"])
def predict_endpoint():
    file = request.files.get("img") or request.files.get("file") or request.files.get("image")
    if not file or file.filename == "":
        return jsonify({"status": "error", "message": "No image file provided in request."}), 400

    if not allowed_file(file.filename):
        return jsonify({"status": "error", "message": f"Allowed extensions: {', '.join(['png','jpg','jpeg','webp','bmp'])}"}), 400

    safe_name = secure_filename(file.filename) or "leaf.jpg"
    temp_filename = f"scan_{uuid.uuid4().hex[:10]}_{safe_name}"
    save_path = os.path.join(app.config["UPLOAD_FOLDER"], temp_filename)
    file.save(save_path)

    try:
        diagnosis = run_diagnostic_pipeline(save_path)
        if diagnosis.get("status") == "success":
            return jsonify({
                "status": "success",
                "prediction": diagnosis,
                "image_url": url_for("serve_uploaded_image", filename=temp_filename, _external=True),
            })
        else:
            return jsonify(diagnosis), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/upload", methods=["POST", "GET"])
def upload_form_endpoint():
    if request.method == "POST":
        file = request.files.get("img") or request.files.get("file") or request.files.get("image")
        if not file or file.filename == "":
            return redirect(url_for("home_page"))
        safe_name = secure_filename(file.filename) or "leaf.jpg"
        temp_filename = f"scan_{uuid.uuid4().hex[:10]}_{safe_name}"
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], temp_filename)
        file.save(save_path)
        diagnosis = run_diagnostic_pipeline(save_path)
        return render_template(
            "disease_detection.html", result=True,
            imagepath=url_for("serve_uploaded_image", filename=temp_filename),
            prediction=diagnosis,
        )
    return redirect(url_for("home_page"))


@app.route("/uploads/<path:filename>")
@app.route("/uploadimages/<path:filename>")
def serve_uploaded_image(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.route("/api/health", methods=["GET"])
def api_health():
    status = get_status()
    status["status"] = "healthy"
    status["system"] = "PhytoScan Plant Disease Diagnostic Engine"
    return jsonify(status)


@app.route("/api/classes", methods=["GET"])
def api_classes():
    get_cnn_model()
    return jsonify({"total": len(_cnn_classes), "classes": _cnn_classes, "active_model": _cnn_model_name})


@app.route("/api/crops", methods=["GET"])
def list_crops():
    crops = list(disease_db.get("crops", {}).keys())
    return jsonify({"crops": crops, "count": len(crops)})


@app.route("/api/diseases/<crop>", methods=["GET"])
def list_crop_diseases(crop: str):
    crop_data = disease_db.get("crops", {}).get(crop.lower(), {})
    diseases = list(crop_data.get("diseases", {}).keys())
    return jsonify({"crop": crop, "diseases": diseases, "count": len(diseases), "description": crop_data.get("description", "")})


@app.route("/api/disease-info/<crop>/<disease>", methods=["GET"])
def get_disease_details(crop: str, disease: str):
    info = get_disease_info(crop, disease)
    if info:
        return jsonify({"crop": crop, "disease": disease, "info": info})
    return jsonify({"error": "Disease not found in local database"}), 404


if __name__ == "__main__":
    port = int(os.getenv("PORT") or os.getenv("DISEASE_DETECTION_PORT") or 5002)
    if port == 0:
        port = 5002
    print("=" * 60)
    print("PhytoScan Plant Disease Recognition Engine Starting")
    print(f"   Listening on: http://127.0.0.1:{port}")
    status = get_status()
    print(f"   Gemini Vision: {'Active' if status['gemini_vision_available'] else 'Standby / No API Key'}")
    get_cnn_model()
    print(f"   Offline CNN: {'Active (' + _cnn_model_name + ')' if status['offline_cnn_available'] else 'Not loaded'}")
    print(f"   Knowledge Base: {status['crops_in_database']} crops loaded")
    print("=" * 60)
    app.run(debug=True, use_reloader=False, host="127.0.0.1", port=port)
