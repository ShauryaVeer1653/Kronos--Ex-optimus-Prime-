<div align="center">

# 🚀 KRONOS — Upgrade & Expansion Plan v3.0

> *From a smart soil sensor to a complete precision agriculture platform.*

**Status:** Feasibility Analysis + Implementation Roadmap  
**Date:** August 2026  
**Based on:** KRONOS v2.1 production system

</div>

---

## 📋 Proposed Upgrades Overview

| # | Feature | Feasibility | Effort | Impact |
|:--|:--------|:-----------:|:------:|:------:|
| 1 | GPS Mapping + Nutrient Heatmap | ✅ YES | High | 🔥🔥🔥 |
| 2 | Leaf Disease Detection (AI Vision) | ✅ YES | Medium | 🔥🔥🔥 |
| 3 | Multi-User Web App + Auth | ✅ YES | Medium | 🔥🔥🔥 |
| 4 | Uneven Water / Waterlogging Detection | ✅ YES* | High | 🔥🔥🔥 |

> *Waterlogging detection requires multi-node sensor deployment. Fully feasible with existing hardware + GPS.

---

## 1. 🗺️ GPS Field Mapping + Nutrient Heatmap

### Is it Feasible?

**YES — 100% feasible. This is the most powerful upgrade possible.**

### Hardware Addition: NEO-M8N GNSS Module

| Spec | Value |
|:-----|:------|
| Module | u-blox NEO-M8N (or M9N for better accuracy) |
| Interface | UART (Serial) or I2C → connects directly to ESP32-S3 |
| Accuracy | 2.5m CEP (standard) / <1m with SBAS correction |
| Cost | Rs. 350–700 per module (India) |
| Power draw | ~23 mA active (negligible vs. sensor + ESP32) |
| Cold start fix | ~26 seconds | Hot start fix | ~1 second |

### How It Works — End to End

```
[Field Walk]
Farmer walks the field with the KRONOS node
         │
         ▼
NEO-M8N GPS locks position (lat, lon, accuracy)
         │
         ▼
ESP32-S3 reads BOTH:
  ├── GPS: lat, lon, accuracy, timestamp
  └── Soil Probe: N, P, K, pH, EC, Moisture, Temp
         │
         ▼
One JSON payload pushed to InfluxDB:
{
  "lat": 22.5726,
  "lon": 88.3639,
  "accuracy_m": 2.1,
  "nitrogen": 145,
  "phosphorus": 18,
  "potassium": 78,
  "pH": 6.8,
  "conductivity": 1.2,
  "humidity": 32.4,
  "temperature": 28.1,
  "timestamp": "2026-08-16T08:15:00+05:30"
}
         │
         ▼
Backend aggregates spatial data per field/session
         │
         ▼
Interpolation Engine (Python: scipy / pykrige)
  ├── IDW (Inverse Distance Weighting)  ← fast, simple
  └── Kriging (Ordinary Kriging)        ← accurate, geostatistical
         │
         ▼
Heatmap rendered on Leaflet.js map
  ├── Layer: Nitrogen heatmap (blue → green → red)
  ├── Layer: Phosphorus heatmap
  ├── Layer: Potassium heatmap
  ├── Layer: pH heatmap
  ├── Layer: EC (salinity) heatmap
  └── Layer: Moisture heatmap
         │
         ▼
Web dashboard → farmer sees EXACTLY which zones
are nutrient-deficient → apply fertilizer only there
```

### Spatial Interpolation Options

| Method | Best For | Python Library | Accuracy |
|:-------|:---------|:--------------|:---------|
| **IDW** | Quick view, <50 points | `scipy.interpolate` | Medium |
| **Ordinary Kriging** | Geostatistical analysis, 20-200 points | `pykrige` | High |
| **RBF (Radial Basis)** | Smooth gradients | `scipy.interpolate.RBFInterpolator` | High |
| **Nearest Neighbor** | Very sparse data | `scipy.spatial.Voronoi` | Low |

> **Recommended: IDW for live preview, Kriging for final report generation.**

### Field Mapping Session Flow (UX)

```
Dashboard → "Start Field Survey"
    │
    ├── GPS status: Locked (2.1m accuracy) ✅
    ├── Auto-capture: every 5m walked (distance-based) OR every 30s
    ├── Live map: dots appear as readings are taken
    └── "End Survey" → triggers heatmap generation

Heatmap Features:
    ├── Toggle between N / P / K / pH / EC / Moisture layers
    ├── Overlay field boundary (GeoJSON polygon)
    ├── Export as PDF report with zone maps
    ├── "Variable Rate Application" zones:
    │     Zone A: Nitrogen deficient → highlight → apply 40 kg/acre
    │     Zone B: Adequate → highlight → no action
    │     Zone C: Excess → highlight → skip fertilizer
    └── Historical comparison: last survey vs this survey (delta maps)
```

### What You Get

- **Variable Rate Fertilization (VRF)** — apply fertilizer ONLY where needed. Studies show 20-40% reduction in fertilizer costs.
- **Yield prediction** — correlate historical soil maps with yield
- **Legal compliance** — GPS-tagged records for subsidy claims / organic certification
- **Field boundary mapping** — automatic area calculation in acres/hectares

---

> ### 📍 For Now — One Sensor, Temporal Mapping
>
> Since the 7-in-1 NPK probe is expensive and we currently have only **one unit**, multi-point simultaneous measurement is not feasible yet. However, **temporal mapping is a valid and accepted workaround** used even in research-grade precision agriculture:
>
> **How it works:**
> 1. In the **morning (6–8 AM)** — push the probe into the soil at **Zone A** (e.g. low-lying corner), hold for 30–60 seconds, log the GPS-tagged reading.
> 2. In the **mid-day (12 PM)** — repeat at **Zone B** (mid-field).
> 3. In the **evening (5–6 PM)** — repeat at **Zone C** (raised bund / near drainage).
> 4. Repeat across **10–20 spots** across the field over 2–3 days.
>
> The backend stores all readings with their GPS coordinates and timestamps. The heatmap engine then interpolates across these points — giving you a **coarse but real spatial picture** of your field's nutrient distribution.
>
> **Important caveat:** Soil nutrient levels (N, P, K) change slowly (days–weeks), so temporal offsets of a few hours between zone readings are acceptable. Moisture and EC are more dynamic and will reflect time-of-day variation — factor this in by taking readings at consistent times across days.
>
> **This works today, with your existing single probe + phone GPS.** No extra hardware needed.
>
> ✅ **Short term:** Temporal field walk (same sensor, different times/spots)
> 🔜 **Long term:** Multiple sensor nodes deployed simultaneously

### Technical Implementation

```
ESP32-S3 firmware additions:
├── TinyGPS++ library (NMEA GPRMC/GPGGA parsing)
├── GPS UART: pins GPIO 17 (TX), GPIO 18 (RX)
├── Minimum fix requirement: HDOP < 3.0 before logging
└── Distance filter: log only if moved > 3m from last point

Backend additions (Python):
├── New InfluxDB measurement: "soil_spatial"
├── Fields: lat, lon, accuracy_m + all soil fields
├── pykrige library: pip install pykrige
├── scipy: pip install scipy
├── New Flask routes:
│     POST /api/survey/start
│     POST /api/survey/end
│     GET  /api/survey/{survey_id}/heatmap?nutrient=nitrogen
│     GET  /api/surveys           ← list all surveys for farm

Frontend additions:
├── Leaflet.js + Leaflet.heat plugin
├── Survey session management UI
└── Layer toggle controls
```

---

## 2. 🍃 Leaf Disease Detection (AI Vision)

### Is it Feasible?

**YES — Very feasible. High accuracy models already exist.**

### How It Works

```
User opens KRONOS app on phone
    │
    ├── "Scan Leaf" button
    │
    ▼
Takes photo / uploads from gallery
    │
    ▼
Image sent to backend: POST /api/disease/detect
    │
    ▼
CHOICE OF MODEL BACKENDS:
    │
    ├── Option A: Google Cloud Vision API (Plant pathology endpoint)
    │     Pros: No training needed, 99%+ uptime, 50+ diseases
    │     Cons: Paid API (~Rs.1.2 per call)
    │
    ├── Option B: PlantVillage + EfficientNet-B4 (Self-hosted)
    │     Model trained on 87,000 images, 26 crops, 38 disease classes
    │     Accuracy: 99.35% on PlantVillage test set
    │     Deploy: Flask + PyTorch OR Tensorflow Lite on ESP32-S3
    │     Pros: FREE, offline-capable on device
    │     Cons: 3-4 days training / fine-tuning effort
    │
    └── Option C: Roboflow + custom dataset (Best for Indian crops)
          Fine-tune on Indian leaf conditions
          Deploy via Roboflow inference API
          Cost: Free tier (1000 calls/month)
    │
    ▼
Response:
{
  "disease": "Leaf Blight",
  "crop": "Rice",
  "confidence": 0.94,
  "severity": "Moderate",
  "cause": "Xanthomonas oryzae bacteria",
  "treatment": {
    "chemical": "Copper Oxychloride 3g/L spray",
    "organic": "Neem oil 5ml/L + 0.1% boric acid",
    "timing": "Apply at dusk. 2 sprays 7 days apart.",
    "prevention": "Avoid overhead irrigation. Improve drainage."
  },
  "affected_area_estimate": "~15% leaf area",
  "urgency": "HIGH"
}
    │
    ▼
Dashboard shows:
    ├── Disease card with annotated image (bounding boxes)
    ├── Treatment protocol
    ├── Cross-reference with live soil data
    │     (e.g. "Low K detected → increases blight susceptibility")
    └── Alert: "3 blight detections this week in your field"
```

### Supported Diseases (PlantVillage Dataset)

| Crop | Detectable Diseases |
|:-----|:--------------------|
| Rice | Leaf Blight, Brown Spot, Blast, Tungro |
| Wheat | Rust (Leaf, Stem, Yellow), Powdery Mildew, Blight |
| Maize | Blight, Grey Leaf Spot, Common Rust, Northern Leaf Blight |
| Tomato | Early Blight, Late Blight, Leaf Mold, Bacterial Spot, Mosaic Virus |
| Potato | Early Blight, Late Blight |
| Cotton | Bacterial Blight, Alternaria Blight |
| Soybean | Bacterial Pustule, Frog Eye Leaf Spot |

> Adding Indian-specific diseases (Sheath Blight for rice, etc.) requires fine-tuning on local dataset — 500-1000 labelled images per disease class.

### Soil-Disease Correlation (Killer Feature)

The unique advantage KRONOS has is **cross-referencing disease detection with live soil data**:

```
Disease: Rice Leaf Blight detected
    │
    ├── KRONOS soil check:
    │     pH: 7.2, Humidity: 68%, Temp: 33°C
    │     → All three are HIGH RISK factors for blight
    │
    ├── Advisory:
    │     "Your soil conditions are actively promoting blight.
    │      Reduce irrigation (EC rising). Improve drainage.
    │      Spray Copper Oxychloride at dusk."
    │
    └── Prevention:
          "Bring soil humidity below 55% to reduce spread risk."
```

**No other precision agriculture system does this combination.**

### Tech Stack for Disease Detection

```
Backend:
├── PyTorch 2.0 + torchvision (EfficientNet-B4)
├── PIL / OpenCV for image preprocessing
├── Model: PlantVillage pre-trained (.pth file, ~170MB)
├── Resize to 256x256, normalize, inference in ~80ms on CPU
├── Flask endpoint: POST /api/disease/detect (multipart/form-data)

Frontend:
├── <input type="file" accept="image/*" capture="environment">
├── Camera access for mobile PWA
├── Preview + annotated result overlay (Canvas API)

Training (if fine-tuning):
├── Dataset: PlantVillage (open access on Kaggle)
├── Framework: PyTorch + transfer learning on EfficientNet-B4
├── Time: 3-4 hours on Google Colab T4 GPU (free)
├── Target accuracy: >95% on Indian crop diseases
```

---

## 3. 👤 Multi-User Web App + Authentication

### Is it Feasible?

**YES — Standard implementation, well-understood.**

### Architecture

```
Current: Single Flask app, no auth, no users
    │
    ▼
Upgraded: Full multi-tenant web platform

┌─────────────────────────────────────────────────────────┐
│                    KRONOS Platform v3.0                  │
│                                                         │
│  ┌──────────────┐    ┌──────────────┐    ┌───────────┐  │
│  │   Auth Layer │    │  Farm Layer  │    │  AI Layer │  │
│  │              │    │              │    │           │  │
│  │ Register     │    │ Farm profiles│    │ Analysis  │  │
│  │ Login (JWT)  │    │ Sensor nodes │    │ Chatbot   │  │
│  │ OAuth Google │    │ Survey data  │    │ Disease   │  │
│  │ Profile mgmt │    │ Heatmaps     │    │ Weather   │  │
│  └──────────────┘    └──────────────┘    └───────────┘  │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │                  Database Layer                   │  │
│  │  PostgreSQL: users, farms, devices, surveys       │  │
│  │  InfluxDB: time-series sensor readings            │  │
│  │  S3/Cloudflare R2: leaf images, heatmap exports   │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### Database Schema (PostgreSQL)

```sql
-- Users
CREATE TABLE users (
    id UUID PRIMARY KEY,
    name VARCHAR(100),
    email VARCHAR(100) UNIQUE,
    phone VARCHAR(15),         -- WhatsApp alerts
    password_hash VARCHAR(255),
    language VARCHAR(10) DEFAULT 'en',  -- en, bn, hi
    created_at TIMESTAMP,
    plan VARCHAR(20) DEFAULT 'free'     -- free, pro, enterprise
);

-- Farms (each user can have multiple farms)
CREATE TABLE farms (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    name VARCHAR(100),              -- "North Field"
    location_city VARCHAR(100),
    boundary_geojson JSONB,         -- field polygon
    area_acres FLOAT,
    primary_crop VARCHAR(50),
    created_at TIMESTAMP
);

-- Sensor Nodes (each farm can have multiple nodes)
CREATE TABLE sensor_nodes (
    id UUID PRIMARY KEY,
    farm_id UUID REFERENCES farms(id),
    device_id VARCHAR(50) UNIQUE,   -- matches ESP32 MAC
    label VARCHAR(50),              -- "Node A - North Corner"
    lat FLOAT, lon FLOAT,           -- fixed installation position
    is_mobile BOOLEAN DEFAULT false,
    last_seen TIMESTAMP
);

-- Survey Sessions (for GPS mapping walks)
CREATE TABLE survey_sessions (
    id UUID PRIMARY KEY,
    farm_id UUID REFERENCES farms(id),
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    point_count INT,
    status VARCHAR(20)   -- 'active', 'processing', 'complete'
);

-- Disease Detections
CREATE TABLE disease_detections (
    id UUID PRIMARY KEY,
    farm_id UUID REFERENCES farms(id),
    detected_at TIMESTAMP,
    crop VARCHAR(50),
    disease VARCHAR(100),
    confidence FLOAT,
    severity VARCHAR(20),
    image_url VARCHAR(255),     -- S3/R2 path
    lat FLOAT, lon FLOAT,       -- GPS of photo location
    treatment_given JSONB
);
```

### Auth Flow

```
Register:
POST /api/auth/register
  { name, email, phone, password, language }
  → creates user + sends OTP to phone (Twilio)
  → returns JWT (access 1h) + refresh token (7d)

Login:
POST /api/auth/login
  { email, password }
  → returns JWT tokens

Google OAuth:
GET /auth/google → redirect → callback → JWT

Every protected request:
Authorization: Bearer <jwt_token>
  → middleware validates → injects user_id into request context

Farm Setup:
POST /api/farms         ← create farm
POST /api/farms/{id}/devices ← register ESP32 node
```

### User Dashboard Pages

```
/ (landing)              → Login / Register
/dashboard               → Overview: all farms, alerts summary
/farm/{id}               → Farm detail: live sensors, latest advisory
/farm/{id}/map           → GPS heatmap for this farm
/farm/{id}/survey/new    → Start a mapping walk
/farm/{id}/disease       → Disease detection history + new scan
/farm/{id}/weather       → 14-day weather planner
/farm/{id}/history       → Historical soil trends (charts)
/farm/{id}/reports       → Downloadable PDF reports
/settings                → Profile, language, alert preferences
/admin                   → (admin only) all users, device management
```

### Framework Recommendation

| Option | Recommendation | Why |
|:-------|:--------------|:----|
| **FastAPI** | ✅ Best choice | Async, auto-docs (Swagger), JWT built-in, 3x faster than Flask |
| Flask (current) | Workable | Already in use, add Flask-JWT-Extended + Flask-Login |
| Django | Overkill | Too heavy for this scale |

---

## 4. 💧 Uneven Water Accumulation / Waterlogging Detection

### Is it Feasible?

**YES — and this is actually where KRONOS GPS + multi-node becomes uniquely powerful.**

### The Problem — Why It Matters

When a field has uneven water accumulation:
- Zone A (low-lying corner): standing water → waterlogged, EC spikes, anaerobic roots
- Zone B (mid-field): optimal moisture
- Zone C (raised bund): dry, low moisture, nutrient leaching

A **single sensor** in any one zone gives a misleading picture of the whole field.

### Solution Architecture

```
APPROACH 0 (FOR NOW): Single Sensor — Temporal Zone Walk  ← USE THIS TODAY
──────────────────────────────────────────────────────────
Since 7-in-1 NPK probes are expensive and we have only ONE unit,
use the same probe at different spots at different times:

  Morning   (6–8 AM):   Insert probe in Zone A (low corner / pond-prone area)
  Mid-day   (12 PM):    Insert probe in Zone B (mid-field center)
  Evening   (5–6 PM):   Insert probe in Zone C (raised bund / near outlet)
  Next day  (morning):  Zones D, E ... continue systematically

  GPS: Log lat/lon at each measurement point (phone GPS is enough)
  Time: ~60 seconds per spot, entire field mapped in 2–3 sessions

What you learn:
  ├── Which zones have elevated EC after rain (waterlogged)
  ├── Which zones dry out fastest (low moisture by noon = sandy / raised)
  ├── NPK gradient across field (coarse but real)
  └── pH variation (acid pockets, alkaline zones near bunds)

Limitation: Moisture/EC readings will have time-of-day drift.
  → Always record in the same time slot per zone for fair comparison.
  → NPK readings are stable (hourly variation negligible) — fully reliable.

This requires NO additional hardware. Works with the current KRONOS node.

─────────────────────────────────────────
APPROACH 1: Multi-Node Deployment (Future — when budget allows)
─────────────────────────────────────────
Deploy 3-5 fixed sensor nodes at strategic field positions:
  Node A: Low-lying zone (pond-prone)
  Node B: Mid-field
  Node C: High ground / bund area
  Node D: Near inlet / irrigation channel
  Node E: Near drainage outlet

Each node has:
  ├── 7-in-1 soil probe
  ├── Fixed GPS coordinates (recorded once at install)
  └── Unique device_id → InfluxDB tag

Backend aggregates ALL nodes simultaneously:
  ├── Detects spatial variance (std dev across nodes)
  ├── High variance in EC = waterlogging in one zone
  ├── High variance in moisture = uneven drainage
  └── Flags: "Node A showing waterlogging — drain this zone"

─────────────────────────────────────────
APPROACH 2: Single Mobile Node + GPS Walk (after GPS module added)
─────────────────────────────────────────
Farmer walks the field with the KRONOS node + NEO-M8N GPS.
Takes readings every 5-10m. Best done right after heavy rain.
  ├── EC hotspots clearly visible (waterlogged zones = high EC)
  ├── Moisture gradient across field
  └── Heatmap shows exactly where water accumulated

This works with ONE device + GPS module (~Rs.600). No extra sensor cost.
```

### Waterlogging Detection Logic

```python
def detect_waterlogging(node_readings):
    """
    For each sensor node, detect waterlogging conditions.
    Returns per-zone status and recommended actions.
    """
    alerts = []
    for node in node_readings:
        ec   = node["conductivity"]  # dS/m
        hum  = node["humidity"]      # %
        temp = node["temperature"]   # °C

        # Waterlogging signature:
        # 1. Very high moisture (>75%) sustained over 6+ hours
        # 2. EC rising (salts concentrating in standing water)
        # 3. Temperature DROP (waterlogged soil = cooler)

        ec_trend   = get_trend(node["device_id"], "conductivity", hours=6)
        hum_trend  = get_trend(node["device_id"], "humidity", hours=6)

        if hum > 75 and ec_trend > 0.05:     # EC rising + high moisture
            severity = "CRITICAL" if hum > 85 else "WARNING"
            alerts.append({
                "node":     node["label"],
                "lat":      node["lat"],
                "lon":      node["lon"],
                "type":     "WATERLOGGING",
                "severity": severity,
                "data":     {"humidity": hum, "ec": ec},
                "actions":  waterlogging_protocol(node, severity)
            })
    return alerts


def waterlogging_protocol(node, severity):
    actions = []
    if severity == "CRITICAL":
        actions += [
            "IMMEDIATE: Open drainage channel / bund cut in this zone",
            f"Root asphyxiation risk in {node['label']} — act within 6 hours",
            "If no drainage: mechanically pump standing water",
        ]
    actions += [
        "After drainage: Apply Gypsum 300 kg/acre to prevent EC spike",
        "Hold all fertilizer applications until EC drops below 2.0 dS/m",
        "Monitor for anaerobic root disease (brown roots, sulfur smell)",
        "Foliar spray: Zinc 0.5% + Boron 0.1% to compensate leached micronutrients",
    ]
    return actions
```

### The EC/Moisture Differential — How It Tells You Everything

```
WHAT THE SENSORS TELL YOU ABOUT WATER STATE:

Scenario 1: WATERLOGGING (just rained/flooded)
─────────────────────────────────────────────
Humidity: 85-100%   ← soil completely saturated
EC:       rising ↑  ← salts dissolving into water
Temp:     -2 to -4°C below normal ← water mass cooling
Action:   DRAIN IMMEDIATELY

Scenario 2: POST-WATERLOGGING (draining)
─────────────────────────────────────────────
Humidity: dropping ↓ (80→65%)
EC:       SPIKE then drop ← salt flush
pH:       may drop (anaerobic fermentation produces acids)
Action:   Gypsum application, monitor drainage rate

Scenario 3: UNEVEN FIELD (differential accumulation)
─────────────────────────────────────────────
Node A humidity: 92% EC: 2.8 dS/m  ← waterlogged
Node B humidity: 55% EC: 1.4 dS/m  ← optimal
Node C humidity: 28% EC: 0.9 dS/m  ← too dry
Action:   Node A = drain | Node B = no action | Node C = irrigate
```

### Digital Elevation Model (DEM) Integration

To predict WHERE water will accumulate BEFORE it happens:

```
Data Source: SRTM 30m DEM (free, global) OR CARTOSAT-1 (India, 2.5m)
API: OpenTopography.org (free API)

What it gives you:
├── Field micro-topography → identify natural depressions
├── Flow direction raster → predict runoff paths
├── Ponding probability map → flag zones BEFORE rain

Algorithm:
1. Download DEM for farm bounding box
2. Run flow accumulation (D8 algorithm via pysheds)
3. Identify sink points (natural ponds)
4. Overlay with rainfall forecast (Open-Meteo)
5. Output: "Zone A likely to accumulate water if >25mm rain"

Libraries: pysheds, rasterio, numpy
```

### Field Management Recommendations (Uneven Terrain)

| Problem | Detection | Solution |
|:--------|:----------|:---------|
| Natural depression waterlogging | Node A: hum >80%, EC rising | Drainage channel / subsoil drainage pipe |
| Bund leakage inflow | Sudden EC spike at field edge | Compact bund, check for seepage |
| Uneven irrigation | Moisture variance >25% across nodes | Adjust inlet flow, level bunds |
| Post-rain salt flush | EC drops field-wide | Hold fertilizer 48h, let salts flush |
| Anaerobic zone | Hum >80% + Temp drop + pH drop | Emergency drain, aerate soil |

---

## 🏗 Full v3.0 Architecture (All Upgrades Combined)

```
╔══════════════════════════════════════════════════════════════════════╗
║                    KRONOS PLATFORM v3.0                              ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  ┌─────────────────────────────────────────────────────────────┐    ║
║  │                    EDGE LAYER (Hardware)                    │    ║
║  │                                                             │    ║
║  │   ESP32-S3 Node                                             │    ║
║  │   ├── 7-in-1 Soil Probe (N,P,K,pH,EC,Moisture,Temp)        │    ║
║  │   ├── NEO-M8N GPS (lat, lon, accuracy)                     │    ║
║  │   └── OLED Display (live readings + GPS fix status)         │    ║
║  │                                                             │    ║
║  │   Modes: Fixed Node (permanent) | Mobile (survey walk)      │    ║
║  └──────────────────────────┬──────────────────────────────────┘    ║
║                             │ Wi-Fi → HTTPS                          ║
║  ┌──────────────────────────▼──────────────────────────────────┐    ║
║  │                    DATA LAYER                               │    ║
║  │                                                             │    ║
║  │   InfluxDB Cloud        PostgreSQL         S3 / R2          │    ║
║  │   Time-series data      Users, Farms,      Leaf images      │    ║
║  │   (N,P,K,pH,EC,         Devices,           Heatmap PDFs     │    ║
║  │    lat, lon, temp)      Surveys,           Report exports   │    ║
║  │                         Disease log                         │    ║
║  └──────────────────────────┬──────────────────────────────────┘    ║
║                             │                                         ║
║  ┌──────────────────────────▼──────────────────────────────────┐    ║
║  │                    BRAIN LAYER (Backend)                    │    ║
║  │                                                             │    ║
║  │   FastAPI (Python)                                          │    ║
║  │   ├── Auth Module    (JWT, OAuth Google, OTP via Twilio)   │    ║
║  │   ├── Farm Module    (CRUD, device mgmt, boundaries)        │    ║
║  │   ├── Soil AI        (deterministic engine + Groq LLM)      │    ║
║  │   ├── Spatial Engine (Kriging, IDW, heatmap generation)     │    ║
║  │   ├── Disease AI     (EfficientNet-B4, PlantVillage)        │    ║
║  │   ├── Weather Module (Open-Meteo + ECMWF SEAS5)             │    ║
║  │   ├── Alert Engine   (waterlogging, risk, WhatsApp/SMS)     │    ║
║  │   └── Report Engine  (PDF generation, heatmap export)       │    ║
║  └──────────────────────────┬──────────────────────────────────┘    ║
║                             │                                         ║
║  ┌──────────────────────────▼──────────────────────────────────┐    ║
║  │                    PRESENTATION LAYER                       │    ║
║  │                                                             │    ║
║  │   Next.js / React PWA (Mobile-first, offline-capable)       │    ║
║  │   ├── Login / Register                                      │    ║
║  │   ├── Farm Dashboard   (live sensor cards + alerts)         │    ║
║  │   ├── GPS Heatmap      (Leaflet.js, layer toggle)           │    ║
║  │   ├── Disease Scanner  (camera, upload, result)             │    ║
║  │   ├── Chatbot          (Groq Llama 3.3 70B)                 │    ║
║  │   ├── Weather Planner  (14-day + seasonal)                  │    ║
║  │   ├── Reports          (PDF download)                       │    ║
║  │   └── Multi-language   (EN / BN / HI)                       │    ║
║  └─────────────────────────────────────────────────────────────┘    ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

## 📦 Full Upgraded Tech Stack

### Hardware
| Component | Current | Upgrade |
|:----------|:--------|:--------|
| MCU | ESP32-S3 | ESP32-S3 (same) |
| Soil Sensor | 7-in-1 RS-485 | 7-in-1 RS-485 (same) |
| GPS | None | **u-blox NEO-M8N** |
| Display | OLED | OLED (same) |
| Power | Li-Po 5-10Ah | Li-Po 5-10Ah (same) |
| Connectivity | Wi-Fi only | Wi-Fi + **optional LoRa** |

### Software
| Layer | Current | Upgrade |
|:------|:--------|:--------|
| Backend | Flask | **FastAPI** |
| LLM | Groq Llama 3.3 70B | Groq Llama 3.3 70B (same) |
| Vision AI | None | **EfficientNet-B4 (PyTorch)** |
| Spatial | None | **pykrige + scipy + rasterio** |
| Auth | None | **JWT + OAuth Google** |
| DB | InfluxDB + CSV | InfluxDB + **PostgreSQL** + **S3** |
| Frontend | Jinja HTML | **Next.js / React PWA** |
| Mapping | None | **Leaflet.js + Leaflet.heat** |
| Alerts | None | **Twilio (SMS/WhatsApp)** |
| Reports | None | **WeasyPrint (PDF)** |

---

## 🗓 Implementation Phases

### Phase 1 — Foundation (Weeks 1–2)
- [ ] Migrate Flask to FastAPI
- [ ] Add PostgreSQL (SQLAlchemy ORM)
- [ ] Implement JWT auth (register, login, protected routes)
- [ ] Move hardcoded API keys to `.env`
- [ ] Add multi-farm + device management

### Phase 2 — Hardware GPS (Weeks 3–4)
- [ ] Wire NEO-M8N to ESP32-S3 (UART)
- [ ] Add TinyGPS++ to firmware (GNSS parsing)
- [ ] Push GPS-tagged payloads to InfluxDB
- [ ] Backend: spatial data aggregation
- [ ] Frontend: Leaflet.js base map + farm boundary

### Phase 3 — Heatmap Engine (Week 5)
- [ ] Implement IDW interpolation (fast preview)
- [ ] Implement Ordinary Kriging (accurate maps)
- [ ] Heatmap layer rendering (Leaflet.heat)
- [ ] Survey session management UI
- [ ] PDF heatmap export (WeasyPrint)

### Phase 4 — Disease Detection (Week 6)
- [ ] Download PlantVillage dataset (Kaggle)
- [ ] Fine-tune EfficientNet-B4 on Google Colab (free T4 GPU)
- [ ] Export model to ONNX for fast CPU inference
- [ ] FastAPI endpoint: POST /api/disease/detect
- [ ] Frontend: camera input + result overlay
- [ ] Soil-disease correlation cross-reference

### Phase 5 — Waterlogging & Alerts (Week 7)
- [ ] Multi-node dashboard (per-node cards)
- [ ] Waterlogging detection algorithm
- [ ] DEM integration (OpenTopography API)
- [ ] EC/Moisture variance alerts
- [ ] Twilio WhatsApp/SMS alerts
- [ ] Push notifications (PWA)

### Phase 6 — Polish & PWA (Week 8)
- [ ] React/Next.js PWA shell (offline-capable)
- [ ] Bengali + Hindi i18n translations
- [ ] Mobile-first UI redesign
- [ ] Historical trend charts (Chart.js / Recharts)
- [ ] Admin panel (device management, user overview)

---

## 💰 Cost Estimate (Per Device)

| Component | Cost (INR) |
|:----------|:----------:|
| ESP32-S3 | ₹400 |
| 7-in-1 Soil Probe | ₹2,500 |
| NEO-M8N GPS | ₹600 |
| OLED 1.3" | ₹150 |
| Li-Po 10Ah | ₹800 |
| Solar Panel 5V/1W | ₹200 |
| PVC Enclosure IP65 | ₹300 |
| PCB + connectors | ₹250 |
| **Total per node** | **~₹5,200** |

**Cloud costs (per month, small scale):**
| Service | Cost |
|:--------|:----:|
| InfluxDB Cloud (free tier) | ₹0 |
| PostgreSQL (Railway / Supabase free) | ₹0 |
| Groq API (free tier 14,400 req/day) | ₹0 |
| Open-Meteo (free, unlimited) | ₹0 |
| Disease Detection model (self-hosted) | ₹0 |
| Cloudflare R2 (image storage, 10GB free) | ₹0 |
| **Total for MVP** | **₹0/month** |

---

## ⚠️ Challenges & Mitigations

| Challenge | Risk | Mitigation |
|:----------|:-----|:-----------|
| GPS accuracy in dense forest / under crop canopy | GPS shadow → poor fix | Use NEO-M9N (better sensitivity) + SBAS correction; require HDOP < 3.0 |
| Kriging requires minimum ~15-20 points | Sparse survey = poor heatmap | Enforce minimum point count; show IDW for <15 points |
| Disease model accuracy on Indian crop varieties | PlantVillage is mostly US/lab photos | Collect 500+ real field photos per disease class; fine-tune on Colab |
| Waterlogging detection false positives after rain | High moisture ≠ always waterlogging | Use EC trend (rising) as confirmation signal, not just absolute moisture |
| Multi-node ESP32 coordination | Time sync across nodes | NTP sync via Wi-Fi (standard on ESP32) — all timestamps in UTC |
| Battery drain with GPS active | GPS adds ~23mA continuous | Duty-cycle GPS: fix every 60s during survey, off in fixed-node mode |

---

## 🎯 Summary: What Version 3.0 Gives You

| Before (v2.1) | After (v3.0) |
|:--------------|:-------------|
| Single user, no login | Multi-user, farm-level accounts |
| One sensor, one location | Multiple nodes, full field coverage |
| "Your soil has low N" | "Zone 3 (NE corner) has low N — apply there only" |
| No visual data | Interactive heatmaps, GPS field maps |
| No plant health | Leaf disease detection with treatment protocol |
| No water management | Waterlogging zone detection + drainage advisories |
| Manual observation | Automated alerts via WhatsApp/SMS |
| Browser-only | Progressive Web App (works offline on mobile) |
| English only | English + Bengali + Hindi |

---

<div align="center">

**KRONOS v3.0** — *From a single sensor to a full spatial intelligence platform.*

*The upgrade transforms KRONOS from a point-measurement device*  
*into a field-wide, AI-powered, multi-user precision agriculture system.*

</div>
