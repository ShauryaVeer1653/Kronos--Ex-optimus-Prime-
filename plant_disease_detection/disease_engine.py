"""
disease_engine.py — PhytoScan / KRONOS Disease Detection Core
============================================================
Standalone module (no Flask dependencies) — importable by any app.

Dual Engine Architecture:
1. Cloud Engine: Google Gemini Vision API
2. Offline Engine: Deep Learning CNN (38-class pre-trained model)
3. Knowledge Engine: Comprehensive Disease & Agronomic Database
"""

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime

os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")

import numpy as np
from PIL import Image
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths & Config
# ---------------------------------------------------------------------------
ENGINE_DIR = Path(__file__).resolve().parent
# Load local .env first (takes priority for disease-specific keys)
load_dotenv(ENGINE_DIR / ".env", override=True)
# Then root .env for shared keys (won't override already-set vars)
load_dotenv(ENGINE_DIR.parent / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

logger = logging.getLogger("DiseaseEngine")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger("DiseaseEngine")

# ---------------------------------------------------------------------------
# Class Lists for Offline CNN Models
# ---------------------------------------------------------------------------
CLASS_NAMES_39 = [
    'Apple___Apple_scab', 'Apple___Black_rot', 'Apple___Cedar_apple_rust', 'Apple___healthy',
    'Background_without_leaves', 'Blueberry___healthy',
    'Cherry___Powdery_mildew', 'Cherry___healthy',
    'Corn___Cercospora_leaf_spot Gray_leaf_spot', 'Corn___Common_rust',
    'Corn___Northern_Leaf_Blight', 'Corn___healthy',
    'Grape___Black_rot', 'Grape___Esca_(Black_Measles)',
    'Grape___Leaf_blight_(Isariopsis_Leaf_Spot)', 'Grape___healthy',
    'Orange___Haunglongbing_(Citrus_greening)',
    'Peach___Bacterial_spot', 'Peach___healthy',
    'Pepper,_bell___Bacterial_spot', 'Pepper,_bell___healthy',
    'Potato___Early_blight', 'Potato___Late_blight', 'Potato___healthy',
    'Raspberry___healthy', 'Soybean___healthy',
    'Squash___Powdery_mildew', 'Strawberry___Leaf_scorch', 'Strawberry___healthy',
    'Tomato___Bacterial_spot', 'Tomato___Early_blight', 'Tomato___Late_blight',
    'Tomato___Leaf_Mold', 'Tomato___Septoria_leaf_spot',
    'Tomato___Spider_mites Two-spotted_spider_mite', 'Tomato___Target_Spot',
    'Tomato___Tomato_Yellow_Leaf_Curl_Virus', 'Tomato___Tomato_mosaic_virus',
    'Tomato___healthy',
]

EXTENDED_INFO = {
    "Rice___Bacterial_blight": {"name": "Rice — Bacterial blight", "cause": "Bacterium Xanthomonas oryzae pv. oryzae causing water-soaked stripes on leaves.", "cure": "Apply copper hydroxide bactericide. Use balanced nitrogen and resistant cultivars."},
    "Rice___Brownspot": {"name": "Rice — Brown spot", "cause": "Fungus Bipolaris oryzae causing circular dark brown lesions.", "cure": "Apply Mancozeb or Carbendazim. Treat seeds and balance soil potassium."},
    "Rice___Tungro": {"name": "Rice — Tungro Virus", "cause": "Viral complex spread by the Green Leafhopper vector.", "cure": "Apply targeted insecticide to control leafhopper vectors and rogue out infected plants."},
    "Rice___Blast": {"name": "Rice — Blast Disease", "cause": "Fungus Magnaporthe oryzae producing diamond-shaped spindle lesions.", "cure": "Apply Tricyclazole (75 WP) or Isoprothiolane at early symptom onset."},
    "Wheat___Aphid": {"name": "Wheat — Aphid Infestation", "cause": "Aphid sap-sucking pests causing leaf chlorosis and stunting.", "cure": "Foliar spray of Dimethoate 30 EC or Imidacloprid 17.8 SL."},
    "Wheat___Black_rust": {"name": "Wheat — Stem / Black Rust", "cause": "Fungus Puccinia graminis causing reddish-brown to black pustules.", "cure": "Apply Propiconazole 25 EC or Tebuconazole upon first notice."},
    "Wheat___Brown_leaf_rust": {"name": "Wheat — Brown Leaf Rust", "cause": "Fungus Puccinia triticina producing orange-brown pustules on foliage.", "cure": "Apply Propiconazole 25 EC or Mancozeb 75 WP."},
    "Wheat___Leaf_blight": {"name": "Wheat — Leaf Blight", "cause": "Fungus Bipolaris sorokiniana causing elongated necrotic lesions.", "cure": "Apply Mancozeb or Azoxystrobin spray and use clean seed stock."},
    "WHeat___Mite": {"name": "Wheat — Curl Mite", "cause": "Wheat curl mite transmitting mosaic viruses.", "cure": "Apply sulfur-based miticides and eliminate volunteer wheat."},
    "WHeat___Powdery_mildew": {"name": "Wheat — Powdery Mildew", "cause": "Fungus Blumeria graminis producing white powdery fungal patches.", "cure": "Apply Propiconazole or Triadimefon."},
    "Wheat___Scab": {"name": "Wheat — Head Scab (Fusarium)", "cause": "Fusarium graminearum affecting wheat heads during warm, humid flowering.", "cure": "Apply Triazole fungicides (Metconazole or Prothioconazole) at flowering."},
    "Wheat___Steam_fly": {"name": "Wheat — Stem Fly", "cause": "Dipteran stem fly larvae burrowing into shoots.", "cure": "Soil application of Chlorpyriphos or foliar Quinalphos."},
    "Wheat___healthy": {"name": "Wheat — Healthy Crop", "cause": "No disease present. Crop displays healthy vegetative vigor.", "cure": "Maintain regular balanced nutrition and irrigation."},
    "Wheat___Healthy_rust": {"name": "Wheat — Rust-Resistant Healthy", "cause": "Plant exhibits natural resistance; healthy foliage.", "cure": "No chemical treatment needed."},
}

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "bmp"}

# ---------------------------------------------------------------------------
# Load Disease Databases
# ---------------------------------------------------------------------------
disease_db = {}
DB_PATH = ENGINE_DIR / "disease_database.json"
if DB_PATH.exists():
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            disease_db = json.load(f)
        logger.info("Loaded disease_database.json: %d crops", len(disease_db.get("crops", {})))
    except Exception as e:
        logger.warning("Error loading disease_database.json: %s", e)

plant_disease_meta = {}
META_PATH = ENGINE_DIR / "plant_disease.json"
if META_PATH.exists():
    try:
        with open(META_PATH, "r", encoding="utf-8") as f:
            raw_list = json.load(f)
            plant_disease_meta = {item["name"]: item for item in raw_list}
        logger.info("Loaded plant_disease.json: %d entries", len(plant_disease_meta))
    except Exception as e:
        logger.warning("Error loading plant_disease.json: %s", e)


def get_disease_info(crop: str, disease: str) -> dict:
    """Look up disease details from local disease database."""
    crops = disease_db.get("crops", {})
    crop_lower = crop.strip().lower()
    for key, crop_data in crops.items():
        if key.lower() == crop_lower or crop_lower in key.lower():
            diseases = crop_data.get("diseases", {})
            disease_lower = disease.strip().lower()
            for dkey, ddata in diseases.items():
                if dkey.lower() == disease_lower or disease_lower in dkey.lower():
                    return ddata
            for dkey, ddata in diseases.items():
                if disease_lower in dkey.lower() or dkey.lower() in disease_lower:
                    return ddata
    return {}


# ---------------------------------------------------------------------------
# Offline CNN Model Management
# ---------------------------------------------------------------------------
_cnn_model = None
_cnn_classes = []
_cnn_model_name = "None"


def get_cnn_model():
    """Load the best available pre-trained local CNN model."""
    global _cnn_model, _cnn_classes, _cnn_model_name
    if _cnn_model is not None:
        return _cnn_model

    weights_path = ENGINE_DIR / "model" / "plant_disease_weights.weights.h5"
    if not weights_path.exists():
        logger.warning("No CNN weights found at model/plant_disease_weights.weights.h5")
        return None

    try:
        import tf_keras as tfk
        logger.info("Building CNN model and loading weights: %s", weights_path)

        _cnn_model = tfk.Sequential([
            tfk.layers.InputLayer(input_shape=(128, 128, 3)),
            tfk.layers.Conv2D(32, (3,3), padding='same', activation='relu', name='conv2d'),
            tfk.layers.Conv2D(32, (3,3), activation='relu', name='conv2d_1'),
            tfk.layers.MaxPooling2D((2,2), name='max_pooling2d'),
            tfk.layers.Conv2D(64, (3,3), padding='same', activation='relu', name='conv2d_2'),
            tfk.layers.Conv2D(64, (3,3), activation='relu', name='conv2d_3'),
            tfk.layers.MaxPooling2D((2,2), name='max_pooling2d_1'),
            tfk.layers.Conv2D(128, (3,3), padding='same', activation='relu', name='conv2d_4'),
            tfk.layers.Conv2D(128, (3,3), activation='relu', name='conv2d_5'),
            tfk.layers.MaxPooling2D((2,2), name='max_pooling2d_2'),
            tfk.layers.Conv2D(256, (3,3), padding='same', activation='relu', name='conv2d_6'),
            tfk.layers.Conv2D(256, (3,3), activation='relu', name='conv2d_7'),
            tfk.layers.MaxPooling2D((2,2), name='max_pooling2d_3'),
            tfk.layers.Conv2D(512, (3,3), padding='same', activation='relu', name='conv2d_8'),
            tfk.layers.Conv2D(512, (3,3), activation='relu', name='conv2d_9'),
            tfk.layers.MaxPooling2D((2,2), name='max_pooling2d_4'),
            tfk.layers.Dropout(0.25, name='dropout'),
            tfk.layers.Flatten(name='flatten'),
            tfk.layers.Dense(1500, activation='relu', name='dense'),
            tfk.layers.Dropout(0.4, name='dropout_1'),
            tfk.layers.Dense(38, activation='softmax', name='dense_1'),
        ])

        dummy = np.zeros((1, 128, 128, 3), dtype=np.float32)
        _ = _cnn_model(dummy, training=False)
        _cnn_model.load_weights(str(weights_path))

        _cnn_model_name = "plant_disease_cnn"
        _cnn_classes = [c for c in CLASS_NAMES_39 if c != "Background_without_leaves"]
        logger.info("Successfully loaded CNN model with %d classes.", len(_cnn_classes))
        return _cnn_model
    except Exception as e:
        logger.warning("Failed loading CNN model: %s", e)
        return None


def _parse_cnn_label(label: str) -> tuple:
    """Parse dataset class string into clean (crop, disease) names."""
    if "___" in label:
        crop_raw, disease_raw = label.split("___", 1)
    elif "__" in label:
        parts = label.split("__", 1)
        crop_raw, disease_raw = parts[0], parts[1]
    elif "_" in label:
        for prefix in ["Pepper_bell", "Pepper", "Potato", "Tomato"]:
            if label.startswith(prefix + "_"):
                crop_raw = prefix
                disease_raw = label[len(prefix) + 1:]
                break
        else:
            parts = label.split("_", 1)
            crop_raw, disease_raw = parts[0], parts[1] if len(parts) > 1 else "Unknown"
    else:
        crop_raw, disease_raw = label, "Unknown"

    crop = crop_raw.replace("__", " ").replace("_", " ").strip().title()
    disease = disease_raw.replace("__", " ").replace("_", " ").strip().title()
    if crop.lower() in ["pepper bell", "pepper"]:
        crop = "Bell Pepper"
    return crop, disease


def analyze_with_cnn(image_path: str) -> dict | None:
    """Predict plant disease using the local CNN model."""
    model = get_cnn_model()
    if model is None:
        return None

    try:
        target_size = (128, 128)
        try:
            in_shape = model.input_shape
            if in_shape and len(in_shape) == 4 and in_shape[1] is not None:
                target_size = (in_shape[1], in_shape[2])
        except Exception:
            pass

        pil_img = Image.open(image_path).convert("RGB")
        resized_img = pil_img.resize(target_size)
        feature = np.array(resized_img, dtype=np.float32)
        feature = np.expand_dims(feature, axis=0)

        import tensorflow as tf
        raw_predictions = model(feature, training=False).numpy()[0]

        pred_sum = float(np.sum(raw_predictions))
        if abs(pred_sum - 1.0) < 0.05:
            predictions = raw_predictions
        else:
            predictions = tf.nn.softmax(raw_predictions).numpy()

        classes = _cnn_classes
        num_classes = len(predictions)
        if num_classes != len(classes):
            logger.warning("Model outputs %d classes but loaded %d class names", num_classes, len(classes))

        pred_idx = int(np.argmax(predictions))
        confidence = float(predictions[pred_idx]) * 100.0
        raw_label = classes[pred_idx] if pred_idx < len(classes) else f"Class #{pred_idx}"

        crop, disease = _parse_cnn_label(raw_label)
        meta = plant_disease_meta.get(raw_label) or EXTENDED_INFO.get(raw_label) or {}
        db_info = get_disease_info(crop, disease)

        is_healthy = "healthy" in raw_label.lower() or "healthy" in disease.lower()
        CONFIDENCE_THRESHOLD = 55.0
        is_uncertain = confidence < CONFIDENCE_THRESHOLD and not is_healthy

        if is_uncertain:
            clean_name = f"{crop} — Uncertain (needs verification)"
            cause_text = f"CNN confidence is low ({confidence:.1f}%). The leaf may be healthy or has an unrecognized condition. Gemini verification recommended."
            cure_text = "Awaiting Gemini verification for accurate diagnosis."
        else:
            clean_name = meta.get("name") or (f"{crop} — Healthy" if is_healthy else f"{crop} — {disease}")
            cause_text = meta.get("cause") or (
                "No pathogen detected. Foliage displays healthy cell structure and chlorophyll." if is_healthy
                else f"Pathogen or physiological stress detected on {crop} foliage."
            )
            cure_text = meta.get("cure") or (
                "Maintain optimal crop irrigation and balanced nutrition." if is_healthy
                else "Apply recommended protective fungicide/bactericide and isolate infected leaves."
            )

        organic_treatments = db_info.get("organic_treatment", [])
        chemical_treatments = db_info.get("chemical_treatment", [])
        prevention_tips = db_info.get("prevention", [])

        organic_str = "; ".join(organic_treatments) if organic_treatments else cure_text
        chemical_str = "; ".join(chemical_treatments) if chemical_treatments else "Apply target-specific fungicide or systemic treatment."
        prevention_str = "; ".join(prevention_tips) if prevention_tips else "Maintain crop spacing, avoid overhead watering, and practice crop rotation."

        return {
            "is_plant": True,
            "is_uncertain": is_uncertain,
            "crop": crop,
            "disease": "Healthy" if is_healthy else ("Uncertain" if is_uncertain else disease),
            "name": clean_name,
            "raw_label": raw_label,
            "confidence": f"{confidence:.2f}%",
            "confidence_score": round(confidence, 2),
            "severity": "none" if is_healthy else ("unknown" if is_uncertain else ("high" if confidence > 80 else "moderate")),
            "cause": cause_text,
            "cure": cure_text,
            "treatment": {
                "organic": "None required - crop is healthy." if is_healthy else ("Awaiting verification." if is_uncertain else organic_str),
                "chemical": "None required." if is_healthy else ("Awaiting verification." if is_uncertain else chemical_str),
                "biological": "Maintain healthy soil microbiome." if is_healthy else ("Awaiting verification." if is_uncertain else "Apply bio-fungicides or beneficial microbes."),
            },
            "prevention": prevention_str,
            "safe_to_consume": True if is_healthy else None,
            "source": f"cnn_model ({_cnn_model_name})",
        }
    except Exception as e:
        logger.error("CNN analysis error: %s", e, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Plant Detection Heuristic
# ---------------------------------------------------------------------------
def is_likely_plant_image(image_path: str) -> bool:
    """Quick heuristic: check if image has enough green/organic color to be a plant."""
    try:
        img = Image.open(image_path).convert("RGB").resize((64, 64))
        arr = np.array(img, dtype=np.float32)
        r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
        green_mask = (g > r * 0.8) & (g > b * 0.8) & (g > 40)
        brown_mask = (r > 80) & (g > 50) & (b < g) & (r > b * 1.1)
        plant_pixels = float(np.sum(green_mask | brown_mask))
        total_pixels = float(green_mask.size)
        ratio = plant_pixels / total_pixels
        logger.info("Plant pixel ratio: %.2f%%", ratio * 100)
        return ratio > 0.08
    except Exception as e:
        logger.warning("Plant detection heuristic failed: %s", e)
        return True


# ---------------------------------------------------------------------------
# Gemini Vision
# ---------------------------------------------------------------------------
CORRECTIONS_LOG = ENGINE_DIR / "gemini_corrections.json"


def _save_gemini_correction(cnn_result: dict, gemini_result: dict, image_path: str):
    """Save case where Gemini disagreed with CNN — useful for future retraining."""
    try:
        corrections = []
        if CORRECTIONS_LOG.exists():
            with open(CORRECTIONS_LOG, "r", encoding="utf-8") as f:
                corrections = json.load(f)
        entry = {
            "timestamp": datetime.now().isoformat(),
            "image": os.path.basename(image_path),
            "cnn_prediction": {
                "name": cnn_result.get("name", ""), "crop": cnn_result.get("crop", ""),
                "disease": cnn_result.get("disease", ""), "confidence": cnn_result.get("confidence_score", 0),
                "raw_label": cnn_result.get("raw_label", ""),
            },
            "gemini_prediction": {
                "name": gemini_result.get("name", ""), "crop": gemini_result.get("crop", ""),
                "disease": gemini_result.get("disease", ""), "confidence": gemini_result.get("confidence_score", 0),
            },
        }
        corrections.append(entry)
        with open(CORRECTIONS_LOG, "w", encoding="utf-8") as f:
            json.dump(corrections, f, indent=2, ensure_ascii=False)
        logger.info("Saved Gemini correction for %s", entry["image"])
    except Exception as e:
        logger.warning("Failed to save correction: %s", e)


def has_gemini_vision() -> bool:
    """Check if Gemini API Key is configured."""
    return bool(GEMINI_API_KEY or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))


def analyze_with_gemini(image_path: str) -> dict | None:
    """Use Gemini Vision to analyze plant disease."""
    api_key = GEMINI_API_KEY or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None

    model_name = GEMINI_MODEL or os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
    prompt = """You are a plant pathology expert specializing in agricultural crop diseases.
Analyze this leaf/plant image and return a JSON object with this exact structure:
{
  "is_plant": true,
  "crop": "Crop/Plant English Name",
  "disease": "Disease Name or Healthy",
  "confidence": "high|medium|low",
  "confidence_score": 95.0,
  "severity": "none|mild|moderate|severe|critical",
  "cause": "Detailed pathogen and cause description",
  "cure": "Detailed treatment and remedy overview with specific product names and dosages",
  "description": "Detailed clinical assessment of visible symptoms",
  "treatment": {
    "organic": "Detailed organic treatment remedies",
    "chemical": "Detailed chemical fungicide/pesticide options",
    "biological": "Biological control measures"
  },
  "prevention": "Detailed preventative cultural practices",
  "safe_to_consume": true/false
}
Be as detailed and specific as possible. Include product names, dosages, application frequencies.
If not a plant or leaf image, return {"is_plant": false, "error": "Not a recognizable plant or crop image."}.
Output pure JSON only without markdown formatting.
"""

    # 1. Try modern google.genai SDK
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        img = Image.open(image_path)
        for m in [model_name, "gemini-3.6-flash", "gemini-2.0-flash"]:
            try:
                response = client.models.generate_content(model=m, contents=[img, prompt])
                text = response.text.strip()
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0].strip()
                result = json.loads(text)
                if result.get("is_plant", False):
                    crop = result.get("crop", "")
                    disease = result.get("disease", "")
                    result["name"] = f"{crop} — {disease}" if disease and disease.lower() != "healthy" else f"{crop} (Healthy)"
                    result["source"] = f"gemini_vision ({m})"
                    return result
            except Exception as model_err:
                logger.debug("google.genai model %s failed: %s", m, model_err)
                continue
    except ImportError:
        pass
    except Exception as e:
        logger.warning("google.genai error: %s", e)

    # 2. Fallback to google.generativeai legacy SDK
    try:
        import google.generativeai as genai_legacy
        genai_legacy.configure(api_key=api_key)
        img = Image.open(image_path)
        for m in [model_name, "gemini-3.6-flash", "gemini-2.0-flash"]:
            try:
                model = genai_legacy.GenerativeModel(m)
                response = model.generate_content([prompt, img])
                text = response.text.strip()
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0].strip()
                result = json.loads(text)
                if result.get("is_plant", False):
                    crop = result.get("crop", "")
                    disease = result.get("disease", "")
                    result["name"] = f"{crop} — {disease}" if disease and disease.lower() != "healthy" else f"{crop} (Healthy)"
                    result["source"] = f"gemini_vision ({m})"
                    return result
            except Exception as model_err:
                logger.debug("google.generativeai model %s failed: %s", m, model_err)
                continue
    except Exception as e:
        logger.warning("google.generativeai analysis failed: %s", e)

    return None


# ---------------------------------------------------------------------------
# Core Diagnostic Pipeline
# ---------------------------------------------------------------------------
def run_diagnostic_pipeline(image_path: str) -> dict:
    """
    Run diagnostic pipeline:
    1. Local plant detection (skip Gemini for non-plant images)
    2. Local CNN Model (fast, offline)
    3. Gemini Vision (for comparison / correction if available)
    """
    result = {"timestamp": datetime.now().isoformat()}

    # 1. Quick local plant check
    if not is_likely_plant_image(image_path):
        cnn_data = analyze_with_cnn(image_path)
        if cnn_data and cnn_data.get("is_plant", False):
            result.update(cnn_data)
        else:
            return {"status": "error", "is_plant": False,
                    "message": "No leaf or plant detected in this image. Please upload a clear photo of a plant leaf."}
        result["status"] = "success"
        return result

    # 2. Local CNN Model (fast, offline)
    cnn_data = analyze_with_cnn(image_path)
    if cnn_data and cnn_data.get("is_plant", False):
        result.update(cnn_data)
        logger.info("CNN prediction: %s (%s)", result.get("name"), result.get("confidence"))
    else:
        return {"status": "error", "is_plant": False,
                "message": "Unable to identify a plant disease in this image. Please upload a clear photo of a plant leaf."}

    # 3. Gemini Vision — cross-check CNN prediction
    gemini_data = analyze_with_gemini(image_path)
    if gemini_data and gemini_data.get("is_plant", False):
        result["gemini_prediction"] = {
            "name": gemini_data.get("name", ""), "crop": gemini_data.get("crop", ""),
            "disease": gemini_data.get("disease", ""), "confidence": gemini_data.get("confidence", ""),
            "confidence_score": gemini_data.get("confidence_score", 0), "cause": gemini_data.get("cause", ""),
            "cure": gemini_data.get("cure", ""), "treatment": gemini_data.get("treatment", {}),
            "prevention": gemini_data.get("prevention", ""), "severity": gemini_data.get("severity", ""),
            "source": gemini_data.get("source", ""),
        }
        logger.info("Gemini prediction: %s", gemini_data.get("name"))

        cnn_crop = (result.get("crop") or "").strip().lower()
        cnn_disease = (result.get("disease") or "").strip().lower()
        gem_crop = (gemini_data.get("crop") or "").strip().lower()
        gem_disease = (gemini_data.get("disease") or "").strip().lower()
        cnn_is_healthy = "healthy" in cnn_disease
        gem_is_healthy = "healthy" in gem_disease
        cnn_is_uncertain = result.get("is_uncertain", False)
        disagree = cnn_crop != gem_crop or (cnn_is_healthy != gem_is_healthy)

        if cnn_is_uncertain or disagree:
            reason = "CNN uncertain" if cnn_is_uncertain else "CNN/Gemini mismatch"
            logger.info("%s: CNN=%s vs Gemini=%s. Using Gemini.", reason, result.get("name"), gemini_data.get("name"))
            for key in ["name", "crop", "disease", "cause", "cure", "treatment", "prevention",
                         "severity", "confidence", "confidence_score", "source"]:
                result[key] = gemini_data.get(key, result.get(key))
            result["corrected_by"] = "gemini"
            result["is_uncertain"] = False
            _save_gemini_correction(cnn_data, gemini_data, image_path)
        else:
            result["corrected_by"] = "none"

    # Enrich from database
    crop = result.get("crop", "")
    disease = result.get("disease", "")
    if crop and disease:
        db_info = get_disease_info(crop, disease)
        if db_info:
            result["disease_info"] = db_info

    result["status"] = "success"
    return result


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in [ext.lower() for ext in ALLOWED_EXTENSIONS]


def get_status() -> dict:
    """Return engine status for health checks."""
    cnn_model = get_cnn_model()
    return {
        "gemini_vision_available": has_gemini_vision(),
        "offline_cnn_available": cnn_model is not None,
        "active_cnn_model": _cnn_model_name,
        "supported_classes": len(_cnn_classes),
        "crops_in_database": len(disease_db.get("crops", {})),
    }
