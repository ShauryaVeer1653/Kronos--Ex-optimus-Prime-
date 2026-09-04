<div align="center">

# 🌱 KRONOS — Smart Soil, Healthy Crops

> *A digital agronomist in every farmer's pocket.*

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.0.3-000000?logo=flask)](https://flask.palletsprojects.com)
[![Groq](https://img.shields.io/badge/LLM-Llama%203.3%2070B%20%28Groq%29-f55036?logo=groq)](https://groq.com)
[![InfluxDB](https://img.shields.io/badge/InfluxDB-Cloud-22ADF6?logo=influxdb)](https://influxdata.com)
[![Open-Meteo](https://img.shields.io/badge/Weather-Open--Meteo-blue)](https://open-meteo.com)
[![SDG](https://img.shields.io/badge/SDG-2%20%7C%2012%20%7C%2015-green)](https://sdgs.un.org)

</div>

---

## 📋 Table of Contents

1. [The Problem](#-the-problem)
2. [Our Solution](#-our-solution)
3. [Hardware Prototype](#-hardware-prototype)
4. [System Architecture](#-system-architecture)
5. [Data Pipeline](#-data-pipeline)
6. [Tech Stack](#-tech-stack)
7. [Project Structure](#-project-structure)
8. [Key Features](#-key-features)
9. [Setup & Installation](#-setup--installation)
10. [Environment Variables](#-environment-variables)
11. [Running the System](#-running-the-system)
12. [API Reference](#-api-reference)
13. [Current State & Upgrade Roadmap](#-current-state--upgrade-roadmap)
14. [SDG Alignment](#-sdg-alignment)
15. [Team](#-team)

---

## 🚨 The Problem

Traditional agriculture operates with significant information gaps:

| Problem | Impact |
|:--------|:-------|
| **Slow, disconnected data** — soil health relies on lab tests that take days/weeks | Farmers make guesswork-based decisions |
| **Raw data overload** — existing IoT probes dump raw numbers with no interpretation | Farmers cannot translate sensor readings into actions |
| **No real-time feedback loop** — systems do not adapt to weather, season, or crop context | Wasted fertilizer, water, and reduced yields |
| **Digital divide** — dashboards assume technical literacy | Low-literacy rural farmers are excluded |

> **The Gap:** A lack of systems that adapt and respond *in real-time* to translate raw sensor data into actionable, farmer-friendly decisions.

---

## 💡 Our Solution

**KRONOS** is an end-to-end precision agriculture system that closes the loop from soil to decision:

```
Soil Probe ──► ESP32 ──► InfluxDB Cloud ──► AI Advisory Engine ──► Dashboard + Chatbot ──► Farmer
```

| Capability | Description |
|:-----------|:------------|
| 🔬 **Real-Time Monitoring** | Measures N, P, K, pH, EC, Moisture & Temperature — 7 parameters in one probe |
| 🤖 **AI Advisory** | Recommends specific crops, sowing windows, irrigation schedules & fertilizer dosages (with quantities in kg/acre) |
| 🌦 **16-Day Weather Planner** | Fuses Open-Meteo forecasts with soil state to optimize field operations |
| 💬 **Farmer-Friendly Chatbot** | Plain-text, emoji-rich advice. Ask: "Is my soil ready for maize?" |
| 📊 **Precision Dashboard** | NPK bands, soil type classification, risk alerts, and trend charts |

---

## ⚙️ Hardware Prototype

### Components

| Component | Role | Spec |
|:----------|:-----|:-----|
| **ESP32-S3 Microcontroller** | Brain — manages sensors, data logging, Wi-Fi uplink | Dual-core 240 MHz, 8MB Flash |
| **7-in-1 Soil Probe Sensor** | Measures N, P, K, pH, EC, Moisture, Temperature simultaneously | RS-485 / UART Modbus |
| **OLED Display** | Shows live soil readings on-device | 0.96" / 1.3" SSD1306 |
| **Battery** | Standalone field power | 5,000–10,000 mAh Li-Po |
| **Solar Panel (optional)** | Extended deployment — 7–14 day runtime without recharge | 5V/1W panel |
| **PVC Enclosure** | Rugged, dust-proof, farm-ready housing | IP65 rated |

### Hardware Block Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    KRONOS Hardware Node                         │
│                                                                 │
│  ┌──────────────────┐      ┌──────────────────────────────┐    │
│  │   POWER SUPPLY   │─────►│       7-in-1 SOIL PROBE      │    │
│  │ Battery 5-10 Ah  │      │  N | P | K | pH | EC | Hum | T   │    │
│  │ + Solar (opt.)   │      └──────────────┬───────────────┘    │
│  └──────────────────┘                     │ RS-485 Modbus      │
│                                           ▼                    │
│                              ┌─────────────────────┐           │
│                              │    ESP32-S3 MCU      │           │
│                              │  Reads sensor data   │           │
│                              │  Runs local ML       │           │
│                              │  Drives OLED         │           │
│                              │  Wi-Fi uplink        │           │
│                              └──────────┬───────────┘           │
│                                         │ Wi-Fi / HTTP          │
└─────────────────────────────────────────┼───────────────────────┘
                                          ▼
                              ┌───────────────────────┐
                              │   InfluxDB Cloud      │
                              │  (Time-Series Store)  │
                              └───────────┬───────────┘
                                          │
                              ┌───────────▼───────────┐
                              │  KRONOS AI Backend    │
                              │  Dashboard + Chatbot  │
                              └───────────────────────┘
```

---

## 🏗 System Architecture

KRONOS is a three-layer system:

### Layer 1 — Edge (Hardware)
The physical ESP32-S3 node in the field. Reads the 7-in-1 probe every second via RS-485 Modbus and pushes timestamped JSON to **InfluxDB Cloud** via Wi-Fi.

### Layer 2 — Ingestion & Storage
- **InfluxDB Cloud** stores all time-series sensor data under the `Soil Monitoring` bucket.
- A Python **data streamer** (`app(for taking data).py`) polls InfluxDB at ~1s intervals and materializes rows into:
  - **CSV files** — daily partitioned (`soil_YYYY-MM-DD.csv`) for low-latency queries.
  - **Parquet files** — columnar format (`data/parquet/day=...`) for analytics.
  - **State file** — `data/state/last_ts.state` tracks the last-written timestamp for resumable polling.

### Layer 3 — AI Advisory Backend (`app3(main).py`)
A **Flask** web server that exposes the dashboard and chatbot. On every analysis request:
1. Reads and merges the last 14 CSV files.
2. Applies 3-point rolling average smoothing.
3. Runs deterministic soil science (NPK bands, soil type, risk alerts).
4. Fuses live Open-Meteo 14-day forecast.
5. Calls **Llama 3.3 70B via Groq** for crop-specific advisory text.
6. Returns a structured Markdown report rendered as HTML.

### Full Architecture Diagram

```
                         ┌─────────────────────────────────────────────────┐
                         │              KRONOS PLATFORM                    │
                         │                                                 │
  [FIELD]                │  [INGESTION]       [STORE]       [BRAIN]        │  [USER]
                         │                                                 │
  7-in-1 Probe           │  app(for          InfluxDB    app3(main).py     │
  │                      │  taking data).py   Cloud      Flask Server      │
  │ RS-485               │  │                 │           │                │
  ▼                      │  │  Flux QL        │           │                │
  ESP32-S3 ─── Wi-Fi ───►│──┤  every ~1s ────┤           │                │
  OLED Display           │  │                 │           │                │
                         │  ▼                 │           │                │
                         │  CSV (daily)       │           ▼                │
                         │  Parquet (part.)   │     read_latest_csvs()     │
                         │  State file        │     rolling avg (3pt)      │
                         │                    │     soil_type_infer()      │
                         │                    │     fertilizer_reco()      │
                         │                    │     risk_warnings()        │
                         │                    │          │                 │
                         │                    │          ▼                 │
                         │                    │  Open-Meteo API            │
                         │                    │  14-day forecast           │
                         │                    │  derive_weather_signals()  │
                         │                    │          │                 │
                         │                    │          ▼                 │
                         │                    │  Groq / Llama 3.3 70B     │
                         │                    │  crop advisory + chatbot   │
                         │                    │          │                 │
                         │                    │          ▼                 │
                         │                    │  Flask Routes ────────────►│──► Browser
                         │                    │  /api/analysis             │    Dashboard
                         │                    │  /api/chat                 │    Chatbot
                         └────────────────────────────────────────────────┘
```

---

## 🔄 Data Pipeline

The pipeline follows 4 stages — *from soil to decision*:

### Stage 1 — From Soil to Data

```
Soil Probe (RS-485 Modbus)
    │
    ▼
ESP32-S3 reads: N, P, K, pH, EC, Moisture, Temperature
    │
    ▼ (Wi-Fi)
InfluxDB Cloud  <──── Flux QL query (every ~1s)
    │
    ▼
app(for taking data).py
    ├── CSV  →  data/csv/soil_YYYY-MM-DD.csv
    ├── Parquet → data/parquet/day=YYYY-MM-DD/
    └── State → data/state/last_ts.state
```

**Key details:**
- Poll interval: `1 second`
- EC is stored in raw `uS/cm` and converted to `dS/m` on read (divided by 1000)
- Timestamps stored in IST (`+05:30`)
- Up to last `14 CSV files` are merged per analysis window

---

### Stage 2 — From Data to Insights

```
read_latest_csvs(window_hours=N)
    │
    ├── Merge + deduplicate on `time`
    ├── 3-point rolling average per field
    ├── EC unit conversion (uS/cm → dS/m)
    │
    ▼
soil_type_infer(df)
    ├── Sandy  → low moisture + fast drying rate + low EC
    ├── Clayey → high moisture + slow drying + high EC
    └── Loamy  → intermediate profile (optimal)

fertilizer_reco(latest)
    ├── N band: [low < 125 | adequate 125–250 | high > 250] mg/kg
    ├── P band: [low < 10  | adequate 10–25   | high > 25]  mg/kg
    └── K band: [low < 50  | adequate 50–125  | high > 125] mg/kg

risk_warnings(latest)
    ├── Fungal risk  (30–38°C + 35–70% humidity)
    ├── Drought stress (moisture < 20% + temp > 32°C)
    ├── Salinity stress (EC >= 2.0 + humidity >= 35%)
    ├── Acidic soil (pH < 5.5) → lime prescription
    ├── Alkaline soil (pH > 7.8) → gypsum prescription
    └── Heat stress (soil temp > 40°C)
```

---

### Stage 3 — From Insights to Advice

```
format_advisory(ctx, crop, window_label)
    │
    ├── Crop profile lookup  →  CROP_KB (10+ built-in crops)
    │   └── or generate dynamically via Groq if unknown crop
    │
    ├── Suitability check (pH range, EC max per crop)
    ├── pH correction prescription (lime / gypsum / elemental S)
    ├── EC correction prescription (flood leach + gypsum)
    │
    ├── Per-nutrient dosage  _dose(nutrient, band)
    │   ├── N low → Urea 30–40 kg/acre in 2 splits
    │   ├── P low → SSP 40–50 kg/acre or DAP 15–20 kg/acre
    │   └── K low → MOP 20–25 kg/acre or SOP 25–30 kg/acre
    │
    ├── Micronutrient alerts (Zinc lockout, Mn toxicity, Ca displacement)
    ├── Irrigation recommendation (per crop profile)
    │
    └── Groq Llama 3.3 70B → crop-specific dynamic fertilizer plan
            temperature=0.35, max_tokens=1800, retry with exp. backoff
```

---

### Stage 4 — From Advice to Action

```
Flask Endpoints
    │
    ├── GET  /                →  Dashboard HTML
    ├── POST /api/chat        →  Chatbot response (Groq + soil context)
    ├── POST /api/analysis    →  Full advisory report (HTML)
    ├── GET  /api/sensor-data →  Latest sensor readings (JSON)
    ├── POST /api/weather     →  14-day forecast + sowing windows
    └── GET  /api/health      →  System health check (JSON)

User Interfaces
    ├── Dashboard  — Soil health cards, NPK status, risk alerts, weather
    └── Chatbot    — Free-form farmer queries with emoji-rich responses
```

---

## 🛠 Tech Stack

### Backend

| Layer | Technology | Purpose |
|:------|:-----------|:--------|
| **Web Framework** | Flask 3.0.3 | REST API + server-side rendered dashboard |
| **LLM** | Llama 3.3 70B via Groq API | Crop advisory, chatbot, dynamic crop profiles |
| **Numerical Analysis** | NumPy, Pandas | Sensor data processing, rolling averages, linear regression |
| **Markdown** | `markdown` (Python) | Convert AI output to HTML |

### Data Layer

| Component | Technology | Purpose |
|:----------|:-----------|:--------|
| **Time-Series DB** | InfluxDB Cloud (AWS us-east-1) | Raw sensor data storage |
| **Query Language** | Flux QL | Time-range filtering, field pivoting |
| **Local Cache** | CSV (daily partitioned) | Fast local reads for analysis |
| **Analytics Store** | Apache Parquet | Columnar storage for ML/batch analytics |
| **State Management** | Plain text file | Resumable polling checkpoint |

### Hardware

| Component | Technology | Purpose |
|:----------|:-----------|:--------|
| **Microcontroller** | ESP32-S3 | Sensor management, Wi-Fi, local ML |
| **Soil Sensor** | 7-in-1 RS-485 Modbus Probe | NPK + pH + EC + Moisture + Temp |
| **Display** | SSD1306 OLED | Local readings display |
| **Power** | 5–10 Ah Li-Po + Solar | 7–14 day field deployment |
| **Enclosure** | PVC IP65 | Dust/water protection |

### External APIs

| API | Provider | Usage |
|:----|:---------|:------|
| **LLM Inference** | Groq — `llama-3.3-70b-versatile` | Advisory generation, chatbot, crop profiles |
| **Weather Forecast** | Open-Meteo | 14-day daily forecast (temp, precip, wind) |
| **Geocoding** | Open-Meteo Geocoding API | City → lat/lon resolution |
| **Seasonal Forecast** | ECMWF SEAS5 (via Open-Meteo) | 6-month seasonal planning |

### AI/ML Components

| Component | Description |
|:----------|:------------|
| **Deterministic Soil Science** | Rule-based NPK banding, pH/EC thresholds calibrated for Indian alluvial soils |
| **Soil Type Classifier** | Infers Sandy / Clayey / Loamy from moisture mean + drying slope + EC |
| **Dynamic Crop Profiles** | If crop not in built-in KB, generates JSON profile via Groq (auto-expanding KB) |
| **Weather Signal Extraction** | Identifies sowing windows, rain-day avoidance, heat stress periods from 14-day forecast |
| **Risk Engine** | Multi-condition alert rules (fungal, drought, salinity, pH toxicity) |
| **Pre-trained Model** | `model.pkl` — scikit-learn model for additional soil classification |

---

## 📁 Project Structure

```
soil/
│
├── README.md                             ← This file
├── .env                                  ← InfluxDB credentials, Gemini API key
├── model.pkl                             ← Pre-trained soil classification model
│
├── app(for taking data).py               ← DATA INGESTION DAEMON
│      InfluxDB → CSV + Parquet + state
│
├── app2a.py                              ← (Deprecated prototype)
├── gemini(depriciated).py                ← (Deprecated - Gemini backend)
├── mini_home(depriciated).py             ← (Deprecated)
├── soil_ai_service(depriciated).py       ← (Deprecated)
├── temp_date_converter.py                ← Utility script
├── fvj.html                              ← Standalone HTML prototype
│
├── data/
│   ├── csv/       ← Daily CSVs  → soil_YYYY-MM-DD.csv
│   ├── parquet/   ← Partitioned Parquet → day=YYYY-MM-DD/
│   └── state/     ← last_ts.state (polling checkpoint)
│
├── templates/
│   └── index.html                        ← Legacy dashboard template
│
├── static/                               ← CSS, JS, assets
│
└── Gemin_i_caht/                         ← MAIN APPLICATION
    │
    ├── app3(main).py                     ← PRODUCTION BACKEND (v2.1)
    │      Flask + Groq + Full Advisory
    │
    ├── app.py                            ← (Earlier Gemini version)
    ├── app1.py                           ← (Earlier iteration)
    ├── app2.py                           ← (Earlier iteration)
    ├── aopp3.py                          ← (Earlier iteration)
    │
    ├── requirements.txt                  ← Python dependencies
    ├── .env                              ← Groq API key
    │
    ├── data/
    │   └── csv/                          ← Symlinked / copied sensor CSVs
    │
    ├── templates/
    │   └── index.html                    ← Main dashboard Jinja template
    │
    └── static/                           ← Static assets
```

---

## ✨ Key Features

### 🌾 Built-in Crop Knowledge Base
10+ crops pre-loaded with pH range, EC tolerance, P/K impact hints, fertilizer protocols, and irrigation schedules:

`Dragon Fruit` · `Rice` · `Wheat` · `Maize` · `Tomato` · `Sugarcane` · `Potato` · `Mustard` · `Cotton` · `Soybean`

> Any crop not in the KB is **auto-generated via Groq** and cached for future requests.

### 📊 Precision Fertilizer Dosing
Not just "apply urea" — KRONOS gives you:
- **Exact quantities**: `Urea @ 30–40 kg/acre in 2 equal splits`
- **Timing**: `Split 1: Apply immediately | Split 2: 21–28 DAS`
- **Organic alternatives**: `FYM 4–5 tonnes/acre + neem cake 80 kg/acre`
- **Foliar rescue**: `Urea spray 2% (20g/L) — 2 sprays 10 days apart`

### 🌦 Weather-Smart Advisory
- Identifies **optimal sowing windows** (3+ consecutive dry, moderate-temp days)
- Flags **rain-day spray blackouts** (avoid chemical spraying before rain)
- Warns of **heat stress events** (>36°C) and recommends pre-dawn irrigation
- Uses **ECMWF SEAS5** for 6-month seasonal crop planning

### 💬 AI Chatbot
- Powered by **Llama 3.3 70B** (ultra-low latency via Groq)
- Context-aware: every message includes live soil readings + weather
- Emoji-rich, plain-language responses for low-literacy users
- Offline alert mode: "Sensor disconnected — check Wi-Fi"

### 🔴 Risk Alert Engine

| Condition | Detection Rule | Action |
|:----------|:--------------|:-------|
| Fungal risk | 30–38°C + 35–70% humidity | Apply fungicide, improve drainage |
| Drought stress | Moisture < 20% + Temp > 32°C | Emergency irrigation |
| Salinity stress | EC >= 2.0 dS/m + Humidity >= 35% | Flood leach + gypsum |
| Acidic soil | pH < 5.5 | CaCO3 lime 200–400 kg/acre |
| Alkaline soil | pH > 7.8 | Gypsum or elemental sulphur |
| Heat stress | Soil Temp > 40°C | Mulch + increase irrigation frequency |

---

## 🚀 Setup & Installation

### Prerequisites
- Python 3.11+
- InfluxDB Cloud account (free tier works)
- Groq API key (free tier available)
- ESP32-S3 with 7-in-1 soil probe (for live hardware data)

### 1. Navigate to the project

```bash
cd soil/
```

### 2. Install data ingestion dependencies

```bash
pip install influxdb-client pandas pyarrow python-dotenv
```

### 3. Install main app dependencies

```bash
cd Gemin_i_caht/
pip install -r requirements.txt
pip install groq
```

---

## 🔐 Environment Variables

### `soil/.env`
```ini
# InfluxDB Credentials
INFLUXDB_URL=https://us-east-1-1.aws.cloud2.influxdata.com
INFLUXDB_TOKEN=<your_influxdb_token>
INFLUXDB_ORG=Kronos
INFLUXDB_BUCKET=Soil Monitoring
MEASUREMENT=soil_data

# Google Gemini API Key (legacy)
GEMINI_API_KEY=<your_gemini_key>
GEMINI_MODEL=gemini-2.0-pro
```

### `soil/Gemin_i_caht/.env`
```ini
GROQ_API_KEY=<your_groq_api_key>
```

> WARNING: Never commit real API keys to git. Add `.env` to `.gitignore`.

---

## ▶️ Running the System

### Step 1 — Start the data ingestion daemon

Run from the `soil/` directory (requires live hardware pushing to InfluxDB):

```bash
python "app(for taking data).py"
```

### Step 2 — Start the AI advisory server

```bash
cd Gemin_i_caht/
python "app3(main).py"
```

### Step 3 — Open the Dashboard

Navigate to `http://localhost:5000` in your browser.

---

## 🔌 API Reference

| Method | Endpoint | Description |
|:------:|:---------|:------------|
| `GET` | `/` | Renders the main dashboard |
| `POST` | `/api/chat` | Chatbot — `{"message": "...", "crop": "wheat"}` |
| `POST` | `/api/analysis` | Full agronomy report — `{"crop": "wheat", "window": "24h"}` |
| `GET` | `/api/sensor-data` | Latest raw sensor readings (JSON) |
| `POST` | `/api/weather` | Forecast — `{"city": "Kolkata", "crop": "rice"}` |
| `GET` | `/api/health` | System health check |

---

## 📈 Current State & Upgrade Roadmap

### What Is Working (Current State)

| Feature | Status |
|:--------|:------:|
| 7-in-1 hardware probe → InfluxDB | ✅ Production |
| CSV + Parquet local data store | ✅ Production |
| Deterministic soil science engine | ✅ Production |
| Groq Llama 3.3 70B chatbot | ✅ Production |
| 14-day weather fusion | ✅ Production |
| 10+ crop knowledge base | ✅ Production |
| Dynamic crop profile generation | ✅ Production |
| Risk alert engine | ✅ Production |
| Flask dashboard + API | ✅ Production |
| Retry/backoff on Groq rate limits | ✅ Production |
| 30-min analysis caching | ✅ Production |
| Historical CSV fallback | ✅ Production |

### Identified Gaps & Upgrade Plan

#### Critical / High Priority

| # | Gap | Proposed Upgrade |
|:--|:----|:-----------------|
| 1 | **No authentication** — dashboard is fully open | Add JWT-based auth + farmer profile system |
| 2 | **Single-node data pipeline** — blocking poll loop | Migrate to async ingestion (asyncio / Celery + Redis) |
| 3 | **No multi-farm support** — hardcoded single sensor | Add device registry + multi-sensor routing (sensor_id tag) |
| 4 | **API key hardcoded in source** — `GROQ_API_KEY` in `app3(main).py` line 23 | Move ALL keys to `.env` consistently |
| 5 | **No offline mode** — chatbot fails if Groq is down | Add local fallback (Ollama / llama.cpp GGUF) |

#### Medium Priority

| # | Gap | Proposed Upgrade |
|:--|:----|:-----------------|
| 6 | **No historical trend charts** — snapshot only | Add Chart.js / Plotly time-series charts (7/30-day views) |
| 7 | **Deprecated files clutter** | Archive deprecated files to `/archive` folder |
| 8 | **No push notifications** | Add WhatsApp/SMS alerts via Twilio for critical breaches |
| 9 | **`model.pkl` unused** — pre-trained model not wired in | Integrate into `soil_type_infer()` as ML prediction layer |
| 10 | **No unit tests** | Add pytest suite for soil science functions and API endpoints |

#### Future Enhancements

| # | Enhancement | Description |
|:--|:------------|:------------|
| 11 | **Mobile PWA** | Progressive Web App for offline farmer use |
| 12 | **Local language support** | Bengali, Hindi translations of chatbot responses |
| 13 | **Satellite data fusion** | Integrate NDVI from Sentinel-2 for crop health validation |
| 14 | **Predictive yield model** | Train ML model on historical soil + weather + yield data |
| 15 | **ESP32 OTA updates** | Over-the-air firmware updates to deployed hardware nodes |
| 16 | **LoRa/MQTT gateway** | Support no-Wi-Fi farms via LoRaWAN → MQTT bridge |
| 17 | **ECMWF SEAS5 seasonal planner UI** | Full UI for 6-month crop planning calendar |

---

## 🌍 SDG Alignment

| Goal | How KRONOS Contributes |
|:-----|:----------------------|
| **SDG 2 — Zero Hunger** | Improves crop yields through data-driven soil management and optimal sowing windows |
| **SDG 12 — Responsible Consumption & Production** | Reduces over-fertilization and water waste through precision dosing recommendations |
| **SDG 15 — Life on Land** | Prevents soil degradation through pH/EC monitoring and targeted soil health correction |

---

## 👥 Team

**Team Kronos** — Inter-College Competition on Prototype Design for Mankind

📧 teamkronos.2025@gmail.com  
📍 Kolkata, West Bengal, India

*Presented at Heritage Institution Innovation Council (Ministry of HRD Initiative)*

---

<div align="center">

**KRONOS** — *More than a soil sensor. A digital agronomist.*

*Kronos AI v2.1 · Llama 3.3 70B · Open-Meteo · Deterministic Soil Science*

</div>
