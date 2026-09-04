# 🌱 Kronos AI — Complete Technical Walkthrough

> Version 2.2 · Flask + Groq (Llama 3.3 70B) + Open-Meteo + TensorFlow CNN
> This document explains how every part of the system works, where every number comes from, exactly what the AI does vs. doesn't do, and answers to questions judges typically ask.

---

## 1. Big Picture Architecture

```
┌──────────────┐   MQTT/WiFi   ┌──────────────┐   polls every 1s   ┌───────────────────┐
│ ESP32/Arduino│ ────────────▶ │  InfluxDB    │ ◀───────────────── │ soil_data_pipeline│
│ Soil Sensor  │   telemetry   │  (cloud)     │                    │ (.py, runs 24/7)  │
│ NPK/pH/EC/   │               └──────────────┘                    │  → CSV + Parquet  │
│ Temp/GPS     │                                                   │  in data/csv/     │
└──────────────┘                                                   └─────────┬─────────┘
                                                                             │ reads
                                                             ┌───────────────▼───────────────┐
                                                             │      kronos_app.py (Flask)     │
                                                             │ ─────────────────────────────  │
                                                             │ 1. Deterministic soil science  │
                                                             │    (thresholds, trends, bands) │
                                                             │ 2. Groq LLM (Llama 3.3 70B)    │
                                                             │    chat / dosages / plans      │
                                                             │ 3. Open-Meteo weather APIs     │
                                                             │ 4. Disease engine (CNN+Vision) │
                                                             │ 5. Report store (data/reports) │
                                                             └───────────────┬───────────────┘
                                                                             │ JSON + HTML
                                                             ┌───────────────▼───────────────┐
                                                             │ template_kronos.html           │
                                                             │ iOS-style SPA: Chart.js plots, │
                                                             │ gauge, weather strip, chat,    │
                                                             │ scan tab, heatmap tab          │
                                                             └───────────────────────────────┘
```

**Core design principle:** *Deterministic first, AI second.* All measurements, classifications (N/P/K low-adequate-high), risk flags, suitability verdicts, and priority tables are computed with fixed agronomic thresholds in plain Python — **never by the LLM**. The LLM is only used for (a) natural-language chat grounded in that computed context, (b) crop-specific fertilizer dosage write-ups, and (c) irrigation/seasonal plan narratives. This makes the science reproducible and audit-proof.

---

## 2. Data Ingestion — from probe to CSV

### 2.1 Hardware → InfluxDB
An ESP32/Arduino probe pushes readings (~1/sec) over WiFi into **InfluxDB** (`soil_data` measurement). Fields: `conductivity` (µS/cm), `humidity` (% soil moisture), `nitrogen`, `phosphorus`, `potassium` (mg/kg), `pH`, `temperature` (°C), `latitude`, `longitude`.

### 2.2 `soil_data_pipeline.py` (the bridge)
Runs continuously:
1. Polls InfluxDB every 1 s using a Flux range query starting from a persisted timestamp in `data/state/last_ts.state` (so restarts never re-ingest or lose data).
2. Converts timestamps to **IST (+05:30)** ISO strings.
3. Appends rows to daily CSV files `data/csv/soil_YYYY-MM-DD.csv` (one file per day) and mirrors to Parquet (`data/parquet/`) for analytics.

The dashboard **never talks to InfluxDB directly** — it reads these CSVs, so it keeps working even if InfluxDB is briefly unreachable.

---

## 3. Backend — `kronos_app.py` layer by layer

### 3.1 Config & safety rails (top of file)
- Keys come from root `.env` via `python-dotenv`: `GROQ_API_KEY`, model name (`llama-3.3-70b-versatile`), InfluxDB creds, `RATE_LIMIT_PER_MIN`.
- Hardcoded **agronomic thresholds** calibrated for Indian alluvial soils:

| Constant | Meaning | Value |
|---|---|---|
| `SOIL_HUM_LO/HI` | Sandy↔Loam↔Clay moisture split | 25% / 35% |
| `SLOPE_FAST/SLOW` | Drying rate cut-offs (±%/hr) | −2.0 / −0.5 |
| `N_LOW/N_HIGH` | Nitrogen band mg/kg | 125–250 |
| `P_LOW/P_HIGH` | Phosphorus band mg/kg | 10–25 |
| `K_LOW/K_HIGH` | Potassium band mg/kg | 50–125 |
| `EC_LOW/HIGH/WARN` | Salinity µS/cm | 1000 / 1500 / 2000 |
| `PH_ACID/PH_ALK` | pH limits | 5.5 / 7.8 |

### 3.2 Crop Knowledge Base (`CROP_KB`)
10 crops hardcoded (dragon fruit, rice, wheat, maize, tomato, sugarcane, potato, mustard, cotton, soybean), each with: ideal `ph_range`, `ec_max`, P/K impact hints, fertilizer notes, and an `irrigation_hint`. **If a farmer types any other crop**, `generate_crop_profile()` asks Groq once for a strict-JSON profile (temperature 0.2), validates all required keys, caches it in memory, and reuses it. A `__failed__` marker prevents retry loops on garbage input.

### 3.3 Reading & cleaning data
- `read_latest_csvs(window_hours)` — loads up to the last 14 daily CSVs, dedupes by timestamp, parses times as UTC-aware, optionally slices to a recent window.
- **Zero-as-missing rule** (`_clean_sensor_cols`): unwired/disconnected channels report exact `0`; those are masked to `NaN` so phantom zeros can never poison averages (e.g., pH "2.4" that was really `(7.17+0+0)/3`). Then a **3-point rolling mean** smooths noise while preserving gaps (`NaN` stays `NaN` → charts honestly show gaps when offline).
- `read_csvs_between(from, to)` — same cleaning but smoothing is applied **per calendar day** so smoothing never bleeds across day boundaries; used for historical date-range analysis.
- **Live mode (recent change):** `/api/sensor_series?` with no window returns only the **last 15 minutes** of valid data. If nothing valid arrived in 15/10/5 min, it seeds the chart with the single most recent valid reading ("Live · starting from last reading") and continues live — old history is never shown in Live view.

### 3.4 The deterministic analysis core

- **`slope_per_hour`** — least-squares linear fit of moisture vs. time → drying/wetting rate in %/hour (needs ≥3 points).
- **`soil_type_infer`** — texture classification from physics-style heuristics:
  - Sandy = low mean moisture AND drying faster than −2 %/hr AND EC < 1000 (water drains fast, low dissolved ions).
  - Clayey = high moisture (>35%) AND slow drainage (> −0.5 %/hr) AND high EC ≥ 1500.
  - Everything else = Loamy. Returns reasons so the logic is explainable.
- **`_band(v, lo, hi)`** — classifies each macronutrient into `low / adequate / high / unknown`.
- **`fertilizer_reco`** — one-line recommendations per band (urea for low-N, SSP/DAP for low-P, MOP for low-K, pause-N when excess).
- **`risk_warnings`** — fixed trigger table: warm+moist → fungal risk; dry+hot → drought; EC≥2000 with wet soil → salinity stress; pH<5.5 → lime dose; pH>7.8 → gypsum/sulphur; T>40 °C → mulch warning.
- **`sensor_connected`** — two-layer disconnect detection: (1) is the newest row valid on any channel? (2) are ≥80% of the last 10 rows zero/NaN across NPK+EC (bulk disconnect)? The UI then shows "Sensor offline — showing last valid data" instead of lying.

### 3.5 Report generation — `format_advisory()` (the flagship output)
Builds a full markdown report **entirely deterministically**, except one section:
1. Header: crop, date, location, soil type, analysis window.
2. Sensor table: each parameter gets status text + crop impact chosen from threshold tables (e.g., EC > 4000 → "Toxic salinity… osmotic stress").
3. Suitability matrix: measured pH/EC against the crop profile's `ph_range`/`ec_max` → ✅/❌ per criterion + overall verdict.
4. Correction protocols: exact lime/sulphur/gypsum doses (kg/acre), depth, timing, recheck schedule — selected from templates based on which direction pH/EC are off.
5. Micronutrient alerts: pH>7.5 → Zn/Fe lockout protocol; pH<5.5 → Mn/Al toxicity; EC>2000 → Ca/B displacement.
6. Irrigation note: moisture <25% → "Irrigate Now"; >75% → "Skip Irrigation"; else continue, plus the crop's `irrigation_hint`.
7. **AI section:** one Groq call (max 1200 tokens) writes the crop-specific N/P/K action plan with kg/acre doses, growth-stage timing, organic alternatives — grounded by the measured values injected into the prompt.
8. Priority summary table: ranked actions (pH fix #1 Critical → nutrients Urgent → micro Important → maintenance).
9. Footer: bottom-line risk statement.

Reports are saved as JSON (id, timestamps, html, md, full context snapshot) to `data/reports/` and browsable/deletable via `/reports` endpoints. Both live reports and historical-range reports go through this identical path.

### 3.6 Weather intelligence (Open-Meteo — free, no key)
- **Geocoding**: `geocoding-api.open-meteo.com` city→lat/lon.
- **14-day forecast**: `api.open-meteo.com/v1/forecast` — tmax/tmin, precipitation sum & probability, wind. Loaded automatically at startup for Kolkata in a background thread (UI never blocks).
- **Signal derivation** (`derive_weather_signals`, deterministic): rain days (pop≥50% or ≥5 mm), heat-stress days (tmax≥36 °C), cool nights (tmin≤10 °C), field-work-friendly days, **best sowing window** (longest run ≥3 comfortable days), heavy-rain clusters (≥2 rainy days in a 5-day sliding window), total 14-day rain.
- **Seasonal planning**: Open-Meteo's `seasonal-api` serves the **ECMWF SEAS5** ensemble forecast; the app aggregates its ~6 months of daily ensemble members into monthly means of tmax/tmin and totals of rain → fed to the LLM for a month-by-month management plan.

### 3.7 AI chat — `get_chat_response()`
Pipeline per message:
1. Language mapping (English/Hindi/Bengali) → "Respond entirely in X".
2. **Grounding context**: fresh soil analysis if cache is older than 30 min (or forced by a window/date-range picker); otherwise reuse `cached_analysis`. Historical date ranges load that exact span instead. Context includes latest values, NPK bands, soil type, alerts, sensor status.
3. Weather block appended (full 14-day table if toggle on, one-line snippet otherwise).
4. Off-topic guardrail: keyword check `is_agri()` adds a redirect instruction for non-farming questions.
5. `call_groq()` sends system prompt + last **10 turns** of history + user prompt (temperature 0.35), converts markdown→HTML server-side, retries on 429 with exponential backoff (1→16 s).

System prompt enforces: concise, bullet-organized, specific numbers (kg/acre, mm), simple English, no repetition, reference provided data naturally.

### 3.8 Disease detection — `plant_disease_detection/disease_engine.py`
Three-stage pipeline per image (`run_diagnostic_pipeline`):
1. **Plant check** — local heuristic (`is_likely_plant_image`) rejects non-plant photos early.
2. **Offline CNN** — TensorFlow/Keras Sequential model loaded from `plant_disease_weights.weights.h5`, trained on a PlantVillage-style dataset of **38 classes** (crop × healthy/disease). Runs fully offline, returns label parsed into {crop, disease} + confidence.
3. **Gemini Vision cross-check** — when API available, produces a second opinion with cause/cure/treatment/prevention/severity; both predictions shown side-by-side.
4. Curated **disease DB** (`disease_db`) supplies treatment info per known disease.

Exposed to the main app via `/api/disease/analyze` (upload ≤16 MB, filename sanitized, rate-limited) and served images via `/api/disease/image/<file>`.

### 3.9 Heatmap — `heatmap_flask.py`
- Queries raw GPS-tagged points from InfluxDB for a chosen time range.
- Device health gate: LIVE / LIVE-no-GPS / OFFLINE pill computed from reading age (`STALE_THRESHOLD_SEC`) and GPS presence; distinct empty states for each case.
- Interpolation: **Ordinary Kriging** (`pykrige`) with selectable variogram model and nlags, geographic coordinates type, padded grid (default n×n), TTL-cached results keyed by a hash of inputs.
- Rendered as colored overlays on Leaflet maps with sample markers, colormap choice per metric, edge fade mask, PNG download endpoint.

### 3.10 Frontend — `template_kronos.html` (single-file iOS-style SPA)
- Tabs: Dashboard, Scan, Weather/Irrigation, Heatmap, Chat, Reports history.
- **Chart.js line charts** (6 metrics) with gradient fills; **SVG pH gauge** arc; band chips; weather strip cards.
- Time controls: Live (15-min rolling), preset windows (1h/6h/24h/week), custom absolute range.
- Polling loop `tick()` every 10 s (configurable): refreshes instant values from `/dashboard_data` **and** chart series from `/api/sensor_series` in live mode, with an overlap guard and change-detection so silent refreshes don't spam the UI.
- Chat supports voice input (Web Speech API) and language selection; session tabs keep multiple conversations.
- Grafana iframe was removed — everything is native now (live charts + heatmap cover it).

### 3.11 Security & robustness details worth citing
- Per-IP sliding-window **rate limiter** (default 15/min) on every LLM/expensive endpoint.
- Security headers (`nosniff`, frame-options, referrer-policy) after every request; 16 MB upload cap; `secure_filename`.
- `_json_safe()` recursively converts numpy/pandas/NaN → browser-safe JSON (no literal NaN crashes).
- All secrets in `.env`, never committed; keys checked at boot with hard exit if missing.
- Graceful degradation everywhere: no CSVs → honest error; weather down → synchronous retry path; disease weights missing → feature disabled with clear message; Groq 429 → exponential backoff.

---

## 4. Where every number the user sees comes from

| Displayed item | Generated by | AI involved? |
|---|---|---|
| Live chart points | CSV rows, zero-cleaned, smoothed, 15-min live window | ❌ |
| pH gauge value | Latest *valid* row's pH | ❌ |
| Soil type (Sandy/Loamy/Clayey) | Moisture mean + drying slope + EC rules | ❌ |
| N/P/K Low/Adequate/High chips | Fixed band thresholds | ❌ |
| Risk alert lines | Fixed trigger table | ❌ |
| Suitability ✅/❌ matrix | Measured vs. crop profile ranges | Profile possibly AI-generated once, then cached |
| Lime/gypsum/fertilizer dose tables | Deterministic template selection | ❌ |
| N/P/K detailed action plans | Prompt w/ measured values → Llama 3.3 70B | ✅ |
| Chat answers | Context-injected Llama 3.3 70B | ✅ |
| Irrigation 14-day schedule | Forecast + crop hint → LLM formats | ✅ (numbers anchored to forecast) |
| Seasonal 6-month plan | ECMWF SEAS5 monthly means → LLM narrative | ✅ (weather numbers are real model output) |
| Disease diagnosis | Local CNN (38-class) ± Gemini Vision cross-check | ✅ CV models |

---

## 5. Likely judge questions — and strong answers

**Q1. "Is the AI hallucinating my fertilizer advice?"**
No. Every classification (bands, suitability, risks, priorities) is deterministic Python with published-threshold logic — you can read it in `kronos_app.py`. The LLM only writes the *prose* of dosage plans and always receives the measured values in its prompt. We also cross-check: even if Groq fails entirely, the report still renders fully with template dosages (see fallback branch `*Could not generate dynamic crop dosage*`).

**Q2. "What happens when the sensor disconnects or misreads?"**
Three layers: (1) exact-zero readings are treated as missing, not zero — phantom averages impossible; (2) `sensor_connected()` detects disconnects from the newest row validity + zero-ratio of the last 10 rows and the UI says "Sensor offline — showing last valid data"; (3) charts show genuine gaps (NaN preserved) rather than fake straight lines. Live view additionally rolls forward: if nothing arrived in 15 min it starts from the last valid reading and continues live.

**Q3. "Why Groq/Llama 3.3 70B instead of GPT-4?"**
Groq's LPUs give near-instant tokens (~300+ tok/s) at negligible cost, critical for a field tool where farmers wait on 2G/3G. Llama 3.3 70B benchmarks close to GPT-4-class for structured advisory tasks, and temperature is held low (0.2–0.35) for consistency. The architecture is provider-agnostic — swapping `call_groq()` swaps the brain without touching anything else.

**Q4. "How accurate is soil type inference?"**
It's a transparent physical heuristic (moisture level + drying rate + EC ≈ drainage behavior), not a lab replacement. We chose explainability over black-box accuracy deliberately; `soil_detail.reasons` shows *why* each verdict was reached. Future work: calibrate against lab-textured field samples with a small ML classifier.

**Q5. "How do you prevent prompt abuse / API cost blow-up?"**
Per-IP sliding-window rate limit (429 responses), 30-min analysis cache so repeated chats don't recompute, 10-turn history cap to bound context size, max_tokens caps per endpoint, off-topic guardrail, and 16 MB upload cap. All keys stay server-side in `.env`.

**Q6. "Does it work offline?"**
Partially by design: charts, dashboard values, deterministic report sections, and the disease CNN all run locally without internet. Only chat narratives, weather forecasts, and seasonal plans need connectivity — and they degrade with explicit messages, not silent failures.

**Q7. "Why Kriging for the heatmap?"**
Ordinary Kriging is a geostatistical best-linear-unbiased estimator: it interpolates unknown soil properties between sparse GPS-tagged probes with quantifiable variance, unlike IDW which ignores spatial correlation structure. Variogram model and lag count are user-selectable, and results are cached (TTL) since kriging is O(n³)-ish.

**Q8. "How does the disease model work? What dataset?"**
A 38-class plantvillage-style CNN (TensorFlow/Keras) running fully offline in-browser-upload time (~ms inference), covering major crops × {healthy, bacterial/fungal/viral diseases}. It's cross-checked by Gemini Vision when online; both opinions display side by side. Non-plant images are rejected before inference.

**Q9. "What's your unit economics / can this scale?"**
Every external service is free-tier friendly: Open-Meteo (no key), Groq free tier, InfluxDB cloud free tier, static frontend. State is flat files (CSV/JSON) — trivially replaceable with Postgres/S3. Flask + gunicorn workers scale horizontally behind any proxy; the only shared state is the small analysis/weather cache, which can move to Redis.

**Q10. "How fresh is 'Live'?"**
Live mode shows only the trailing 15 minutes of valid readings and auto-polls every 10 s; if the sensor pauses longer than 15/10/5 minutes, the chart seeds itself from the most recent valid value and resumes appending as new data arrives — so the farmer never stares at stale hours-old curves labeled as live.

**Q11. "Multi-language support?"**
Chat accepts English, Hindi, Bengali (voice input too via Web Speech API); the target language is enforced in the prompt wrapper around the same grounded context.

**Q12. "What would you build next?"**
- Calibrated ML soil-texture classifier replacing heuristics;
- yield-response model linking NPK corrections to expected outcomes;
- SMS/IVR channel for feature phones;
- multi-probe fleet dashboards with per-field accounts;
- on-device TinyML anomaly detection at the probe to catch drift/calibration loss early.

---

## 6. One-minute demo script
1. Open Dashboard → point out live 15-min charts updating every 10 s, honest gaps, sensor-status honesty.
2. Pick a crop (e.g., Dragon Fruit) → Generate Report → walk through suitability matrix → deterministic correction protocol → AI-written dosage plan → priority table.
3. Weather tab → 14-day forecast with derived sowing window → generate irrigation schedule → show SEAS5 seasonal plan.
4. Scan tab → upload a leaf photo → CNN + Vision dual diagnosis.
5. Map tab → kriged heatmap with device-health gating.
6. Chat tab → ask "should I irrigate today?" in Hindi → answer cites live moisture + tomorrow's rain probability.
