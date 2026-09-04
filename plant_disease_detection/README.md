# 🌿 Plant Disease Recognition System (PhytoScan)

[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11-3776AB?logo=python&logoColor=white)](https://python.org)
[![TensorFlow](https://img.shields.io/badge/TensorFlow-2.15+-FF6F00?logo=tensorflow&logoColor=white)](https://tensorflow.org)
[![Flask](https://img.shields.io/badge/Flask-3.0+-000000?logo=flask)](https://flask.palletsprojects.com)
[![Gemini](https://img.shields.io/badge/AI-Google%20Gemini%20Vision-4285F4?logo=google)](https://ai.google.dev/)

An intelligent diagnostic vision system that detects plant leaf diseases across **30+ agricultural crops and 150+ pathologies**, providing instant causes, treatments, organic remedies, and prevention protocols.

---

## ⚡ Key Highlights

* **Dual Engine Architecture**:
  * **Offline Engine**: High-speed deep convolutional neural network (CNN) trained on the PlantVillage dataset (38 disease classes). Runs locally with zero internet required.
  * **Cloud Fallback Engine**: Google Gemini Vision API for high-resolution edge cases, rare crop diseases, and contextual verification.
* **Pre-Trained Weights Included**: The model weights (`model/plant_disease_weights.weights.h5` — ~31 MB) are already bundled directly in the repository. No manual downloading or Google Drive links needed!
* **Dual Run Mode**:
  1. **Unified within Kronos AI**: Mounted directly inside the Kronos farm intelligence dashboard (`Gemin_i_caht/kronos_app.py` under the **Plant Disease** tab).
  2. **Standalone Web Application**: Runs independently on port `5002` with its own dedicated UI.

---

## 📁 Directory Structure

```
plant_disease_detection/
├── README.md                      ← This guide
├── app.py                         ← Standalone Flask web application
├── disease_engine.py              ← Core inference engine (CNN + Gemini Vision)
├── disease_database.json          ← Rich clinical remedy & agronomic database
├── gemini_corrections.json        ← Knowledge validation & accuracy rules
├── plant_disease.json             ← Class-to-crop taxonomy mapping
├── requirements.txt               ← Dependencies (TensorFlow/tf-keras, Flask, Pillow)
│
├── model/
│   ├── plant_disease_weights.weights.h5  ← Bundled pre-trained 38-class weights
│   └── class_names.json                  ← Taxonomy labels
│
├── static/                        ← CSS, JavaScript, and UI icons
├── templates/                     ← Jinja2 HTML templates
└── uploads/                       ← Temporary upload buffer (.gitkeep)
```

---

## 🛠️ Installation & Setup Tutorial

### 1. Prerequisites
* Python 3.10 or 3.11 installed
* Recommended: Virtual environment (`venv` or `conda`)

### 2. Navigate to the Directory
```bash
cd plant_disease_detection
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

> **Note on TensorFlow / Keras**: If you are on TensorFlow 2.16+, install `tf-keras`:
> ```bash
> pip install tf-keras
> ```

### 4. Configure Environment Variables (Optional)
The offline CNN model works **100% without any API key**. 

If you also wish to enable the optional Gemini Vision fallback for extended diagnostics, copy the `.env.example` from root or create a `.env` in this directory:
```bash
# plant_disease_detection/.env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.0-flash
```

---

## 🚀 How to Run

### Mode A — Standalone Web App
To run this module as an independent web server:

```bash
python app.py
```
* **Local URL**: `http://localhost:5002`
* Upload a leaf image (PNG, JPG, WebP) and click **"Analyze Plant"**.
* View the predicted disease, confidence score, pathogen cause, chemical cure, and organic remedy.

---

### Mode B — Unified with Kronos AI Platform
If you are running the full **Kronos AI** farm management system, you do **not** need to start `app.py` separately! 

`kronos_app.py` automatically imports `disease_engine.py`:
```bash
# From the project root:
python Gemin_i_caht/kronos_app.py
```
* Open `http://localhost:5000` (or the port shown in terminal).
* Click the **"Plant Disease"** tab in the sidebar to scan leaves within the unified farm dashboard.

---

## 🔌 API Reference

### 1. Leaf Image Analysis
* **Endpoint**: `POST /predict` (or `/api/disease/analyze`)
* **Payload**: `multipart/form-data` with key `img`, `file`, or `image`
* **Response**:
```json
{
  "status": "success",
  "prediction": {
    "crop": "Tomato",
    "disease": "Early blight",
    "confidence": 0.962,
    "cause": "Alternaria solani fungal infection causing concentric leaf rings.",
    "cure": "Apply Mancozeb or Chlorothalonil fungicide. Prune lower infected leaves.",
    "organic": "Neem oil spray (5ml/L) or copper soap bio-fungicide.",
    "prevention": "Avoid overhead irrigation; mulch soil to prevent fungal spores splashing."
  },
  "image_url": "/api/disease/image/scan_abcd1234_leaf.jpg"
}
```

### 2. Supported Crops
* **Endpoint**: `GET /api/disease/crops`
* **Response**: Returns list of all cataloged crops and detectable disease categories.

---

## 🔬 Supported Crops & Diseases (Sample)

| Crop | Detectable Conditions |
| :--- | :--- |
| **Apple** | Apple Scab, Black Rot, Cedar Apple Rust, Healthy |
| **Corn (Maize)** | Cercospora Leaf Spot, Common Rust, Northern Leaf Blight, Healthy |
| **Grape** | Black Rot, Esca (Black Measles), Leaf Blight, Healthy |
| **Potato** | Early Blight, Late Blight, Healthy |
| **Tomato** | Bacterial Spot, Early Blight, Late Blight, Leaf Mold, Septoria, Spider Mites, Target Spot, Yellow Leaf Curl, Mosaic Virus, Healthy |
| **Rice & Wheat** | Blast, Brown Spot, Tungro, Bacterial Blight, Rusts, Mildew, Aphids |
| **Pepper & Citrus** | Bacterial Spot, Citrus Greening, Healthy |
