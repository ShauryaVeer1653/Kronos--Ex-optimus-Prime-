# kronos_app.py — Kronos AI  |  v2.2  |  End Product
# ─ Groq + Llama 3.3 70B  (no Gemini)
# ─ 14-day weather auto-loaded from Kolkata on startup
# ─ 6-month ECMWF SEAS5 seasonal planning
# ─ Assistance tab (full chat + weather toggle + quick chips)
# ─ Rich deterministic soil analysis
# v2.2: Moved API keys to .env, cleaned up project structure

import os, sys, time, json, math, threading, uuid as _uuid
from datetime import datetime, timezone, timedelta, timezone as _tz
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
from collections import defaultdict

from dotenv import load_dotenv
from flask import Flask, render_template_string, request, jsonify, url_for, send_from_directory
import requests
import pandas as pd
import numpy as np
import markdown
from groq import Groq

# ─────────────────── Config ───────────────────
load_dotenv(Path(__file__).parent.parent / ".env")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    print("❌ GROQ_API_KEY not found in .env. Add it to the root .env file.", file=sys.stderr)
    sys.exit(1)
GROQ_MODEL   = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

DEFAULT_CITY = "Kolkata"
DEFAULT_LAT  = 22.5726
DEFAULT_LON  = 88.3639

CSV_DIR = Path(__file__).parent.parent / "data" / "csv"   # soil/data/csv  (live sensor data)
FIELDS  = ["conductivity","humidity","nitrogen","phosphorus","potassium","pH","temperature"]

# Saved advisory reports (JSON on disk, browsable via /reports)
REPORTS_DIR = Path(__file__).parent.parent / "data" / "reports"

# Data timestamps are written by the pipeline in IST
IST = timezone(timedelta(hours=5, minutes=30))

ANALYSIS_CACHE_MINUTES = 30
cached_analysis: Optional[Dict] = None
last_analysis_time: Optional[datetime] = None

weather_prefs:   Dict = {"location": DEFAULT_CITY, "lat": DEFAULT_LAT, "lon": DEFAULT_LON, "crop": ""}
weather_context: Dict = {}

# Calibrated thresholds for Indian alluvial soils
SOIL_HUM_LO = 25.0;  SOIL_HUM_HI = 35.0
SLOPE_FAST  = -2.0;  SLOPE_SLOW  = -0.5
EC_LOW, EC_HIGH = 1000, 1500  # µS/cm
N_LOW,  N_HIGH  = 125, 250
P_LOW,  P_HIGH  = 10,  25
K_LOW,  K_HIGH  = 50,  125
EC_WARN = 2000  # µS/cm
PH_ACID = 5.5;  PH_ALK = 7.8

# ─────────────────── Groq Init ───────────────────
CSV_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    print(f"✅ Groq initialized ({GROQ_MODEL})")
except Exception as e:
    print(f"❌ Groq init failed: {e}"); sys.exit(1)

# ─────────────────── Crop Knowledge Base ───────────────────
CROP_KB: Dict[str, dict] = {
    "dragon fruit": {
        "ph_range": [5.5, 6.5], "ec_max": 2000,
        "blurb": "Cactus fruit; prefers slightly acidic, well-drained soil and low salinity.",
        "p_hint": "Low Phosphorus reduces flowering and fruit sweetness.",
        "k_hint": "Low Potassium reduces fruit size, color, and sweetness (°Brix).",
        "fert": "P low → SSP 35–45 kg/acre. K low → MOP 20–25 kg/acre.",
        "irrigation_hint": "Drought-tolerant; water deeply every 7–14 days. No waterlogging. Skip irrigation before/after rain. Reduce at flowering to concentrate sugars.",
    },
    "rice": {
        "ph_range": [5.5, 7.5], "ec_max": 3000,
        "blurb": "Paddy; tolerates high moisture but avoid combined waterlogging + salinity.",
        "p_hint": "P deficiency reduces tillering and panicle formation.",
        "k_hint": "K deficiency increases lodging risk and lowers grain filling.",
        "fert": "N in splits (basal, tillering, PI). P & K as basal if low.",
        "irrigation_hint": "Shallow flooding 3–5 cm during growth. Drain 2 weeks before harvest. Drain excess if rain >50mm/week. Critical stages: tillering, PI, grain filling.",
    },
    "wheat": {
        "ph_range": [6.0, 7.5], "ec_max": 4000,
        "blurb": "Major rabi cereal. Sensitive to heat stress at grain filling.",
        "p_hint": "Low P restricts root development and tillering.",
        "k_hint": "Low K weakens straw and impairs grain filling.",
        "fert": "N in 2–3 splits; P & K as basal. ZnSO4 25 kg/ha if deficient.",
        "irrigation_hint": "6 critical irrigations: CRI 21 DAS, Tillering 45 DAS, Jointing 65 DAS, Flowering 85 DAS, Milk 100 DAS, Dough 115 DAS. ~50mm each.",
    },
    "maize": {
        "ph_range": [6.0, 7.2], "ec_max": 2500,
        "blurb": "High-demand kharif/rabi crop.",
        "p_hint": "Low P causes stunted growth and purple leaves.",
        "k_hint": "Low K leads to lodging and hollow ear tips.",
        "fert": "High N in splits; P & K basal. Manure improves structure.",
        "irrigation_hint": "Every 5–7 days in dry spells. Most sensitive at tasseling and silking. Waterlogging >48 hrs is damaging. Pre-dawn irrigation on heat days >36°C.",
    },
    "tomato": {
        "ph_range": [6.0, 6.8], "ec_max": 2500,
        "blurb": "Needs consistent moisture for quality fruit.",
        "p_hint": "Low P restricts root growth and delays fruit set.",
        "k_hint": "K vital for firmness, colour, and preventing cracking.",
        "fert": "Balanced NPK; raise K at fruiting. Calcium prevents blossom-end rot.",
        "irrigation_hint": "Every 3–5 days (drip ideal). Skip on rain >10mm. Irrigate early morning on heat days >36°C. No overhead watering.",
    },
    "sugarcane": {
        "ph_range": [6.5, 8.0], "ec_max": 3000,
        "blurb": "Long-duration cash crop; heavy feeder.",
        "p_hint": "Low P reduces tillering and root development.",
        "k_hint": "K crucial for sucrose formation and drought tolerance.",
        "fert": "Very high K demand. Multi-split applications.",
        "irrigation_hint": "Every 7–10 days during growth. Reduce last 30–45 days (ripening) to boost sucrose. Ensure good drainage in heavy rain.",
    },
    "potato": {
        "ph_range": [5.0, 6.5], "ec_max": 2000,
        "blurb": "Tuber crop; prefers acidic, cool, well-drained soil.",
        "p_hint": "Low P limits tuber initiation and number.",
        "k_hint": "High K essential for tuber size and starch.",
        "fert": "Balanced NPK with high K. Well-decomposed FYM.",
        "irrigation_hint": "Frequent light irrigation every 5–7 days. Never waterlog. Critical: stolon formation and tuber bulking. Reduce 2 weeks before harvest.",
    },
    "mustard": {
        "ph_range": [6.0, 7.5], "ec_max": 4000,
        "blurb": "Key rabi oilseed; low water crop.",
        "p_hint": "Low P reduces branch count and siliquae.",
        "k_hint": "Low K reduces oil content and frost resistance.",
        "fert": "NPK + Sulphur (gypsum 200 kg/ha). Boron 1 kg/ha if deficient.",
        "irrigation_hint": "2–3 irrigations per season. Critical: rosette (25–30 DAS) and flowering (55–65 DAS). Excess moisture triggers Alternaria blight.",
    },
    "cotton": {
        "ph_range": [6.0, 8.0], "ec_max": 5000,
        "blurb": "Fiber crop; waterlogging-sensitive.",
        "p_hint": "Low P delays flowering and reduces boll size.",
        "k_hint": "K critical for boll development and fibre quality.",
        "fert": "High K during boll formation. Balance N to avoid excess vegetative growth.",
        "irrigation_hint": "Every 10–15 days. Critical stages: squaring, flowering, boll dev. Stop 4 weeks before harvest. Pre-dawn light irrigation on heat stress days.",
    },
    "soybean": {
        "ph_range": [6.0, 7.0], "ec_max": 2500,
        "blurb": "N-fixing legume; key oilseed/protein crop.",
        "p_hint": "Low P affects nodulation and N-fixation.",
        "k_hint": "Low K reduces seed size and oil content.",
        "fert": "Less N (self-fixing). P, K, Sulphur + rhizobium inoculant.",
        "irrigation_hint": "Every 7–10 days. Critical: germination, flowering, pod filling. Well-drained soil essential — waterlogging damages nodules.",
    },
}

# ─────────────────── Groq Helpers ───────────────────
SYSTEM_PROMPT = """You are Kronos — a smart, friendly agricultural advisor for Indian farmers.

RULES:
1. Be CONCISE but COMPLETE. Never cut off mid-sentence. Finish every thought.
2. For simple questions: 2-3 short paragraphs, then ask "Want a detailed breakdown?"
3. For complex questions: use bullet points, stay organized, be thorough.
4. Use specific numbers (kg/acre, mm) but no walls of text.
5. Simple English, no jargon. Emoji welcome 🌱💧☀️
6. If data is provided (soil, weather), reference it naturally.
7. Never repeat. Never pad. Every sentence adds value.
8. If you list options, give 2-3 max, not a catalogue."""


MD_EXT = ['tables', 'fenced_code', 'sane_lists']

def md(text: str) -> str:
    """Convert markdown to HTML with tables and line breaks."""
    return markdown.markdown(text, extensions=MD_EXT)


def call_groq(system: str, user: str, max_tokens: int = 2048, history: list = None) -> Dict[str, Any]:
    """Call Groq with optional conversation history for multi-turn chat."""
    messages = [{"role": "system", "content": system}]
    # Add conversation history (last 10 turns to stay within context)
    if history:
        for msg in history[-10:]:
            messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
    messages.append({"role": "user", "content": user})
    backoff = 1.0
    for attempt in range(3):
        try:
            resp = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=messages,
                temperature=0.35, max_tokens=max_tokens,
            )
            text = resp.choices[0].message.content or ""
            return {"status": "success", "message": md(text), "raw": text}
        except Exception as e:
            err = str(e)
            if "429" in err or "rate_limit" in err.lower():
                print(f"Groq rate-limit (attempt {attempt+1}), retry in {backoff:.1f}s…")
                time.sleep(backoff); backoff = min(backoff * 2, 16)
            else:
                print(f"Groq error: {err}")
                return {"status": "error", "message": "AI backend error. Please try again.", "raw": ""}
    return {"status": "error", "message": "Service temporarily busy. Please retry.", "raw": ""}


def generate_crop_profile(crop_name: str) -> Optional[dict]:
    key = crop_name.strip().lower()
    if not key: return None
    if key in CROP_KB: return CROP_KB[key]
    if CROP_KB.get(key, {}).get("__failed__"): return None
    print(f"🤖 Generating profile for '{crop_name}' via Groq…")
    try:
        resp = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": "Expert agronomist. Return ONLY valid JSON, no markdown."},
                {"role": "user",   "content": f'''Crop profile for: "{crop_name}". Return ONLY JSON:
{{"ph_range":[min,max],"ec_max":float,"blurb":"...","p_hint":"...","k_hint":"...","fert":"...","irrigation_hint":"..."}}'''},
            ],
            temperature=0.2, max_tokens=600,
        )
        raw = resp.choices[0].message.content.strip().replace("```json","").replace("```","").strip()
        profile = json.loads(raw)
        if not all(k in profile for k in ["ph_range","ec_max","blurb","p_hint","k_hint","fert","irrigation_hint"]):
            raise ValueError("Missing keys in profile")
        CROP_KB[key] = profile
        return profile
    except Exception as e:
        print(f"❌ Crop profile failed for '{crop_name}': {e}")
        CROP_KB[key] = {"__failed__": True}
        return None

# ─────────────────── Soil / CSV ───────────────────

_ZERO_INVALID_COLS = ("conductivity", "humidity", "nitrogen",
                      "phosphorus", "potassium", "pH")


def _smooth_series(clean: pd.Series) -> pd.Series:
    return clean.rolling(3, min_periods=1).mean()


def _clean_sensor_cols(df: pd.DataFrame) -> pd.DataFrame:
    """The probe reports exact 0 for unwired/disconnected channels.
    Treat those as MISSING (NaN) so rolling averages and the 'latest'
    reading never inherit phantom zeros (e.g. pH '2.4' = (7.17+0+0)/3).
    Junk positions stay NaN → charts show a real gap when offline."""
    for col in _ZERO_INVALID_COLS:
        if col in df.columns:
            raw = pd.to_numeric(df[col], errors="coerce")
            clean = raw.mask(raw == 0)
            df[col] = _smooth_series(clean).where(clean.notna())
    if "temperature" in df.columns:
        df["temperature"] = _smooth_series(pd.to_numeric(df["temperature"], errors="coerce"))
    return df


def read_latest_csvs(window_hours: Optional[int] = None, allow_historical: bool = False) -> Optional[pd.DataFrame]:
    """
    Read soil CSVs.
    window_hours: if set, only return rows within that many hours of now.
    allow_historical: if True and window gives empty result, fall back to latest available data.
    """
    try:
        csv_files = sorted(CSV_DIR.glob("soil_*.csv"), reverse=True)
        if not csv_files:
            # Also try parent data/csv as fallback
            alt = CSV_DIR.parent.parent.parent / "data" / "csv"
            csv_files = sorted(alt.glob("soil_*.csv"), reverse=True) if alt.exists() else []
        if not csv_files: return None
        dfs = []
        for f in csv_files[:14]:   # up to 14 files
            try: dfs.append(pd.read_csv(f))
            except Exception: pass
        if not dfs: return None
        df = pd.concat(dfs, ignore_index=True)
        if "time" not in df.columns: return None
        df = df.drop_duplicates(subset=["time"], keep="last")
        df["dt"] = pd.to_datetime(df["time"], errors="coerce", utc=True)
        df = df.dropna(subset=["dt"]).sort_values("dt")
        if window_hours and window_hours > 0:
            cutoff = pd.Timestamp.utcnow() - pd.Timedelta(hours=window_hours)
            windowed = df[df["dt"] >= cutoff]
            if windowed.empty and allow_historical:
                print(f"⚠️ No data in last {window_hours}h — using latest {len(df)} historical rows")
            else:
                df = windowed
        df = _clean_sensor_cols(df)
        return df.tail(1500)
    except Exception as e:
        print(f"CSV error: {e}"); return None


def read_csvs_between(date_from: str, date_to: str):
    """Read all CSVs and filter to an IST calendar-date range [date_from, date_to].
    Returns (dataframe, error_message). Rolling average is applied per-day so
    smoothing never bleeds across day boundaries."""
    try:
        csv_files = sorted(CSV_DIR.glob("soil_*.csv"))
        if not csv_files:
            return None, "No CSV files found."
        dfs = []
        for f in csv_files:
            try: dfs.append(pd.read_csv(f))
            except Exception: pass
        if not dfs:
            return None, "Could not read CSV files."
        df = pd.concat(dfs, ignore_index=True)
        if "time" not in df.columns:
            return None, "CSV files have no 'time' column."
        df = df.drop_duplicates(subset=["time"], keep="last")
        df["dt"] = pd.to_datetime(df["time"], errors="coerce", utc=True)
        df = df.dropna(subset=["dt"]).sort_values("dt")
        if date_from:
            df = df[df["dt"] >= pd.Timestamp(date_from, tz=IST)]
        if date_to:
            # accept YYYY-MM-DD or full datetime-local strings
            to_val = date_to if len(date_to) > 10 else date_to + " 23:59:59"
            df = df[df["dt"] <= pd.Timestamp(to_val, tz=IST)]
        if df.empty:
            return None, f"No data found for the range {date_from or 'start'} → {date_to or 'end'}"
        day_key = df["dt"].dt.strftime("%Y-%m-%d")
        for col in _ZERO_INVALID_COLS:   # zero-junk → NaN, per-day smoothing, gaps preserved
            if col in df.columns:
                raw = pd.to_numeric(df[col], errors="coerce")
                clean = raw.mask(raw == 0)
                df[col] = (clean.groupby(day_key)
                                 .transform(lambda s: s.rolling(3, min_periods=1).mean())
                           ).where(clean.notna())
        if "temperature" in df.columns:
            df["temperature"] = (pd.to_numeric(df["temperature"], errors="coerce")
                                 .groupby(day_key)
                                 .transform(lambda s: s.rolling(3, min_periods=1).mean()))
        return df, None
    except Exception as e:
        return None, str(e)


# ─────────────────── JSON safety / report persistence ───────────────────

def _json_safe(obj):
    """Recursively convert numpy/pandas/NaN values into JSON-safe primitives.
    Without this, jsonify emits literal NaN (invalid for browsers) or crashes
    on numpy scalars / pandas Timestamps."""
    if obj is None or isinstance(obj, (str, int, bool)):
        return obj
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    try:  # numpy scalars, pandas Timestamps, etc.
        return _json_safe(obj.item())
    except Exception:
        pass
    return str(obj)


def _clean_ctx(ctx: Dict) -> Dict:
    """Sanitize an analysis context for API responses (drop internal columns)."""
    safe = _json_safe(ctx)
    latest = safe.get("latest")
    if isinstance(latest, dict):
        latest.pop("dt", None)   # internal parsing column, not useful to clients
    return safe


def save_report(kind: str, label: str, crop: str,
                report_html: str, report_md: str, ctx: Dict) -> str:
    """Persist a generated report to data/reports/. Returns the report id."""
    rid = f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{_uuid.uuid4().hex[:6]}"
    rec = {
        "id": rid,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "kind": kind,                 # "live" | "range"
        "label": label,
        "crop": crop,
        "sensor_disconnected": bool(ctx.get("sensor", {}).get("disconnected", False)),
        "report_html": report_html,
        "report_md": report_md,
        "context": _clean_ctx(ctx),
    }
    try:
        (REPORTS_DIR / f"report_{rid}.json").write_text(
            json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print("Report save failed:", e)
    return rid


def list_reports(limit: int = 50) -> List[Dict]:
    out = []
    for f in sorted(REPORTS_DIR.glob("report_*.json"), reverse=True)[:limit]:
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
            out.append({"id": r.get("id"),
                        "created_at": r.get("created_at"),
                        "kind": r.get("kind", "live"),
                        "label": r.get("label", ""),
                        "crop": r.get("crop", ""),
                        "sensor_disconnected": r.get("sensor_disconnected", False)})
        except Exception:
            continue
    return out


def slope_per_hour(times, values):
    v = pd.to_numeric(values, errors="coerce")
    t = (times - times.iloc[0]).dt.total_seconds() / 3600.0
    ok = v.notna() & t.notna()
    if ok.sum() < 3: return None
    m, _ = np.polyfit(t[ok], v[ok], 1)
    return float(m)


def soil_type_infer(df):
    if df.empty: return "unknown", {"reasons": ["no data"]}
    h  = df["humidity"].mean()     if "humidity"     in df.columns else np.nan
    ec = df["conductivity"].mean() if "conductivity" in df.columns else np.nan
    hs = slope_per_hour(df["dt"], df["humidity"]) if "humidity" in df.columns else None
    if pd.notna(h) and pd.notna(ec):
        if   h < SOIL_HUM_LO and hs is not None and hs < SLOPE_FAST  and ec < EC_LOW:
            label, reasons = "Sandy",  ["low moisture, rapid drying, low EC"]
        elif h > SOIL_HUM_HI and hs is not None and hs > SLOPE_SLOW  and ec >= EC_HIGH:
            label, reasons = "Clayey", ["high moisture, slow drying, high EC"]
        else:
            label, reasons = "Loamy",  ["intermediate moisture and EC — good tilth"]
    else:
        label, reasons = "Unknown", ["insufficient sensor data"]
    return label, {"humidity_mean": float(h) if pd.notna(h) else None,
                   "ec_mean": float(ec) if pd.notna(ec) else None,
                   "humidity_slope_per_hr": hs, "reasons": reasons}


def _band(v, lo, hi):
    if v is None or (isinstance(v, float) and np.isnan(v)): return "unknown"
    try: v = float(v)
    except Exception: return "unknown"
    if v < lo: return "low"
    if v > hi: return "high"
    return "adequate"


def fertilizer_reco(latest):
    bands = {"N": _band(latest.get("nitrogen"),   N_LOW, N_HIGH),
             "P": _band(latest.get("phosphorus"), P_LOW, P_HIGH),
             "K": _band(latest.get("potassium"),  K_LOW, K_HIGH)}
    lines = []
    if bands["N"] == "low":  lines.append("Nitrogen deficient — apply urea.")
    if bands["P"] == "low":  lines.append("Phosphorus deficient — apply SSP/DAP.")
    if bands["K"] == "low":  lines.append("Potassium deficient — apply MOP.")
    if bands["N"] == "high": lines.append("Nitrogen excess — pause N applications.")
    if not lines:            lines.append("Macronutrients balanced.")
    return " ".join(lines), {"bands": bands}


def risk_warnings(latest):
    T = latest.get("temperature"); h = latest.get("humidity")
    EC = latest.get("conductivity"); pH = latest.get("pH")
    alerts = []
    if T and h and 30 <= T <= 38 and 35 <= h <= 70:
        alerts.append("🌡 Warm & moist → elevated fungal & microbial activity.")
    if h and T and h < 20 and T > 32:
        alerts.append("🏜 Low moisture + high temp → drought stress / wilting risk.")
    if EC and h and EC >= EC_WARN and h >= 35:
        alerts.append("⚗ High EC + high moisture → salinity stress / root damage risk.")
    if pH and pH < PH_ACID:
        alerts.append("🔴 Acidic soil (pH < 5.5) → apply lime (CaCO₃) 200–400 kg/acre.")
    if pH and pH > PH_ALK:
        alerts.append("🟡 Alkaline soil (pH > 7.8) → apply gypsum or elemental sulfur.")
    if T and T > 40:
        alerts.append("🔥 Extreme soil temperature → mulch surface, increase irrigation frequency.")
    if not alerts:
        alerts.append("✅ No immediate risk flags detected.")
    return alerts


def sensor_connected(df):
    """Offline if the LATEST reading has no valid channel values (primary),
    or if the recent tail is overwhelmingly zero/NaN (secondary)."""
    if df is None or df.empty:
        return False, {"disconnected": True}

    def valid(v):
        try:
            f = float(v)
            return not (math.isnan(f) or math.isclose(f, 0.0, abs_tol=1e-6))
        except Exception:
            return False

    core = [c for c in ("nitrogen", "phosphorus", "potassium",
                        "conductivity", "humidity") if c in df.columns]
    latest_valid = any(valid(df.iloc[-1].get(c)) for c in core)

    tail = df.tail(10)
    def zeroish(s):
        s = pd.to_numeric(s, errors="coerce")
        return ((s.isna()) | (np.isclose(s.fillna(0.0), 0.0, atol=1e-6))).mean()
    ratios = {c: float(zeroish(tail[c])) for c in core}
    npk_vals = [ratios[c] for c in ("nitrogen", "phosphorus", "potassium") if c in ratios]
    npk_z = float(np.mean(npk_vals)) if npk_vals else 1.0
    bulk_disc = ((npk_z >= 0.8 and ratios.get("conductivity", 1.0) >= 0.8) or
                 (ratios.get("humidity", 1.0) >= 0.95 and ratios.get("conductivity", 1.0) >= 0.95))

    disc = (not latest_valid) or bulk_disc
    return (not disc), {"disconnected": bool(disc), "latest_valid": bool(latest_valid),
                        "zero_ratios": ratios, "npk_zeroish": npk_z}


def build_context(df):
    if df.empty: return {}
    # 'latest' must be the most recent VALID row (probe junk rows are all-NaN
    # after cleaning), otherwise the dashboard/gauge would show blanks forever
    # until the hardware reconnects.
    core_cols = [c for c in ("conductivity", "humidity", "nitrogen",
                             "phosphorus", "potassium", "pH") if c in df.columns]
    if core_cols:
        valid_mask = df[core_cols].notna().any(axis=1)
        base = df[valid_mask] if valid_mask.any() else df
    else:
        base = df
    latest         = base.iloc[-1].to_dict()
    soil_label, sd = soil_type_infer(df)
    fert_text, fm  = fertilizer_reco(latest)
    alerts         = risk_warnings(latest)
    _, sensor_meta = sensor_connected(df)
    return {"latest": latest, "soil_type": soil_label, "soil_detail": sd,
            "fert_text": fert_text, "fert_meta": fm, "alerts": alerts, "sensor": sensor_meta}


def _icon(b):
    return {"low":"❌ Low","adequate":"✅ Adequate","high":"⚠️ High","unknown":"⚪ Unknown"}.get(b,"⚪")


def _trend_label(slope):
    if slope is None: return ""
    if slope < -1.5: return " ↓↓ Fast dry"
    if slope < -0.3: return " ↓ Drying"
    if slope > 1.5:  return " ↑↑ Fast wet"
    if slope > 0.3:  return " ↑ Wetting"
    return " → Stable"


def _md_table_row(*cells):
    return '| ' + ' | '.join(str(c) for c in cells) + ' |'


def _dose(nutrient, band, crop_fert_hint=""):
    """Return a detailed, actionable dosage string for a given nutrient band."""
    if band == "adequate": return "✅ Adequate — no immediate action needed."
    if band == "high":
        return {"N": "⚠️ Excess — pause ALL nitrogen inputs for 14 days. Risk: leaf burn, lodging, delayed fruiting.",
                "P": "⚠️ Excess — skip P fertilizer this cycle. Excess P locks out Zinc and Iron.",
                "K": "⚠️ Excess — skip K fertilizer. Monitor for Mg/Ca imbalance (antagonism)."}[nutrient]
    # LOW band — detailed with source options
    if nutrient == "N":
        return ("❌ Deficient — apply Nitrogen:\n"
                "  - **Chemical:** Urea (46-0-0) @ 30–40 kg/acre in 2 equal splits\n"
                "    → Split 1: Apply immediately as basal, water in (20–25 mm)\n"
                "    → Split 2: Apply at 21–28 DAS or next critical growth stage\n"
                "  - **Organic:** Well-decomposed FYM 4–5 tonnes/acre + neem cake 80 kg/acre\n"
                "  - **Foliar rescue:** Urea spray 2% (20g per litre) — 2 sprays 10 days apart\n"
                "  - *Expected uplift: +15–25% vegetative growth within 2 weeks*")
    if nutrient == "P":
        return ("❌ Deficient — apply Phosphorus:\n"
                "  - **Chemical (preferred):** SSP (Single Super Phosphate, 16-0-0-12S) @ 40–50 kg/acre\n"
                "    → Apply as basal incorporation 5–7 cm deep before sowing/transplant\n"
                "  - **Alternative:** DAP (18-46-0) @ 15–20 kg/acre (reduces N top-up needed)\n"
                "  - **Organic:** Bone meal 80–100 kg/acre OR rock phosphate 100–120 kg/acre\n"
                "  - **Foliar:** MKP (0-52-34) spray 0.5% for fast uptake at critical stages\n"
                "  - *Bonus: SSP provides Sulphur (12%), improving protein quality and root growth*")
    if nutrient == "K":
        return ("❌ Deficient — apply Potassium:\n"
                "  - **Chemical:** MOP (Muriate of Potash, 0-0-60) @ 20–25 kg/acre\n"
                "    → Apply in 2 splits — 50% basal + 50% at pre-flowering/fruiting stage\n"
                "  - **Alternative:** SOP (Sulphate of Potash, 0-0-50) @ 25–30 kg/acre\n"
                "    → Better choice for high-EC soils (less chloride)\n"
                "  - **Organic:** Wood ash 150–200 kg/acre (contains ~5% K + Calcium)\n"
                "  - **Foliar rescue:** K2SO4 spray 0.5% at fruiting stage\n"
                "  - *K is critical for fruit quality, disease resistance, and water-use efficiency*")
    return "No action."


def format_advisory(ctx, crop, window_label="Latest"):
    latest = ctx.get("latest", {})
    bands  = ctx.get("fert_meta", {}).get("bands", {})
    soil   = ctx.get("soil_type", "Unknown")
    sd     = ctx.get("soil_detail", {})
    pH = latest.get("pH"); ec = latest.get("conductivity")
    T  = latest.get("temperature"); h = latest.get("humidity")
    N  = latest.get("nitrogen"); P = latest.get("phosphorus"); K = latest.get("potassium")
    trend  = _trend_label(sd.get("humidity_slope_per_hr"))
    prof   = generate_crop_profile(crop or "") if crop else None
    ctitle = (crop or "General Crop").title()

    # ── Crop suitability ──
    suit_header, suit_lines, ph_action, ec_action = "", [], "", ""
    if prof and "__failed__" not in prof:
        lo, hi = prof["ph_range"]
        ok_ph   = (pH is None) or (lo <= pH <= hi)
        ok_ec   = (ec is None) or (ec is None or ec < prof["ec_max"])
        overall = ok_ph and ok_ec
        suit_header = f"{'✅ SUITABLE' if overall else '⚠️ ATTENTION NEEDED'} for {ctitle} cultivation"
        if not ok_ph:
            gap = round(abs((pH or 7.0) - ((lo+hi)/2)), 1)
            if pH and pH < lo:
                ph_action = (f"**pH Correction (Your pH {round(pH,1)} < Target {lo}–{hi}):**\n"
                             f"  → Apply **Agricultural Lime (CaCO₃)**: 200–400 kg/acre\n"
                             f"  → Incorporation: Broadcast and disc 10–15 cm deep, 3–4 weeks before sowing\n"
                             f"  → Recheck pH after 4 weeks. Repeat if needed (max 2 doses/season)\n"
                             f"  → Alternative: **Dolomite lime** 250–350 kg/acre (adds Mg too)")
            else:
                ph_action = (f"**pH Correction (Your pH {round(pH,1)} > Target {lo}–{hi}):**\n"
                             f"  → Apply **Elemental Sulphur**: 50–100 kg/acre (slow, 4–6 week effect)\n"
                             f"  → OR **Gypsum (CaSO₄)**: 300–400 kg/acre (faster, also lowers EC)\n"
                             f"  → Apply and water in well. Check pH again after 3 weeks.")
        if not ok_ec and ec:
            ec_action = (f"**EC/Salinity Correction (Your EC {round(ec,1)} > Max {prof['ec_max']} µS/cm):**\n"
                         f"  → Flood leach with 2 heavy irrigations (50–60 mm each) 5 days apart\n"
                         f"  → Apply **Gypsum**: 400 kg/acre to improve Na displacement\n"
                         f"  → Avoid potassic/chloride fertilizers until EC drops below {prof['ec_max']} µS/cm\n"
                         f"  → Recheck EC after 2 weeks")
    else:
        suit_header = f"Soil type: {soil}  |  pH: {round(pH,1) if pH else 'n/a'}  |  EC: {round(ec,1) if ec else 'n/a'} µS/cm"

    # ── Crop-specific P and K impact ──
    pk_impact = []
    if prof and "__failed__" not in prof:
        if bands.get("P") == "low":  pk_impact.append(f"**Phosphorus impact on {ctitle}:** {prof.get('p_hint','')}")
        if bands.get("K") == "low":  pk_impact.append(f"**Potassium impact on {ctitle}:** {prof.get('k_hint','')}")
        if bands.get("P") == "adequate" and bands.get("K") == "adequate":
            pk_impact.append(f"P and K levels support {ctitle} growth well at current stage.")

    # ── Micronutrients ──
    micro = []
    if pH and pH > 7.5:
        micro.append("**🔒 Zinc/Iron Lockout Risk** (pH > 7.5 causes precipitation)\n"
                     "  → ZnSO₄·7H₂O: 25 kg/ha soil application OR 0.5% foliar spray\n"
                     "  → FeSO₄ foliar: 0.2–0.3% spray every 2 weeks (3 applications)")
    if pH and pH < 5.5:
        micro.append("**☠️ Manganese/Aluminium Toxicity Risk** (pH < 5.5)\n"
                     "  → Lime immediately as priority #1 before any other input\n"
                     "  → Avoid Ammonium Sulphate (acidifying) until pH is corrected")
    if ec and ec > 2000:
        micro.append("**⚗️ Calcium/Boron Displacement** (high EC causes antagonism)\n"
                     "  → Ca-foliar spray: CaNO₃ 0.5% (2–3 sprays)\n"
                     "  → Borax spray: 0.1% at flower initiation")

    # ── Irrigation recommendation based on moisture ──
    irr_note = ""
    if prof and "__failed__" not in prof:
        irr_hint = prof.get("irrigation_hint", "")
        if h is not None:
            if h < 25:
                irr_note = f"💧 **Irrigate Now** — Moisture at {round(h,1)}% is critically low for {ctitle}.\n  → {irr_hint}"
            elif h > 75:
                irr_note = f"🚫 **Skip Irrigation** — Moisture at {round(h,1)}% is excessive for {ctitle}. Ensure drainage.\n  → {irr_hint}"
            else:
                irr_note = f"✅ Moisture OK ({round(h,1)}%) — continue standard schedule.\n  → {irr_hint}"

    # ── Summary line ──
    need   = [nm for nm, bv in bands.items() if bv == "low"]
    nl     = ("Supplement " + " & ".join(need)) if need else "Nutrient levels adequate"
    suffer = []
    if bands.get("P") == "low" or bands.get("K") == "low": suffer.append("yield and fruit quality reduction")
    if bands.get("N") == "low": suffer.append("stunted vegetative growth")
    sl = "Yes — " + "; ".join(suffer) + " expected without correction" if suffer else "No — current profile can support healthy growth"

    # ── Build report ──
    lines = [
        f"## 🌱 {ctitle} — Kronos AI Precision Agronomy Report",
        f"> 📅 {datetime.now().strftime('%d %b %Y, %I:%M %p')}  &nbsp;·&nbsp;  West Bengal  &nbsp;·&nbsp;  {soil} Soil  &nbsp;·&nbsp;  Window: {window_label}",
        "---",
        "### 📊 Sensor Readings",
        "| Parameter | Avg Reading | Status | Crop Impact |",
        "|:----------|------------:|:------:|:------------|",
        f"| 🌡 Temperature | {round(T,1) if T else '—'} °C | {'⚠️ Heat Stress' if T and T > 35 else ('⚠️ Cold Risk' if T and T < 12 else ('✅ Optimal' if T else '⚪ No data'))} | {'Accelerates water loss, enzyme stress' if T and T > 35 else ('Slows growth, risk of frost if <5°C' if T and T < 12 else 'Normal metabolic rate')} |",
        f"| 💧 Moisture | {round(h,1) if h else '—'} %{trend} | {'🏜️ Critically Dry' if h and h < 20 else ('⚠️ Low' if h and h < 30 else ('🌊 Waterlogged' if h and h > 80 else ('✅ Optimal' if h else '⚪ No data')))} | {'Wilting, nutrient uptake failure' if h and h < 20 else ('Reduced uptake efficiency' if h and h < 30 else ('Root asphyxiation, anaerobic conditions' if h and h > 80 else 'Good nutrient transport'))} |",
        f"| ⚡ EC | {round(ec,2) if ec else '—'} µS/cm | {'🔴 Toxic Salinity' if ec and ec > 4000 else ('⚠️ High' if ec and ec > 2000 else ('✅ Good' if ec else '⚪ No data'))} | {'Osmotic stress, cell plasmolysis' if ec and ec > 4000 else ('Reduced water uptake by roots' if ec and ec > 2000 else 'Normal ion absorption')} |",
        f"| 🧪 pH | {round(pH,1) if pH else '—'} | {'🔴 Strongly Acidic' if pH and pH < 5.0 else ('🟠 Acidic' if pH and pH < 5.5 else ('🟡 Alkaline' if pH and pH > 7.8 else ('✅ Optimal' if pH else '⚪ No data')))} | {'Al/Mn toxicity, nutrient lockout' if pH and pH < 5.0 else ('P fixation, reduced Ca/Mg uptake' if pH and pH < 5.5 else ('Zn/Fe/Mn deficiency, P unavailable' if pH and pH > 7.8 else 'Optimal nutrient availability'))} |",
        "---",
        "### 🌿 Crop Suitability Assessment",
        f"**{suit_header}**",
    ]
    if prof and "__failed__" not in prof:
        lo, hi = prof["ph_range"]
        ok_ph   = (pH is None) or (lo <= pH <= hi)
        ok_ec   = (ec is None) or (ec < prof["ec_max"])
        lines += [
            f"| Criterion | Target | Measured | Result |",
            f"|:----------|-------:|---------:|:------:|",
            f"| Soil pH | {lo} – {hi} | {round(pH,1) if pH else '—'} | {'✅' if ok_ph else '❌'} |",
            f"| Soil EC | < {prof['ec_max']} µS/cm | {round(ec,2) if ec else '—'} | {'✅' if ok_ec else '❌'} |",
            f"| Soil Type | Any loamy/well-drained | {soil} | {'✅' if 'loam' in soil.lower() else '🟡'} |",
            "",
            f"*{prof.get('blurb','')}*",
        ]
    if pk_impact: lines += [""] + pk_impact
    if ph_action: lines += ["", ph_action]
    if ec_action: lines += ["", ec_action]
    lines += [
        "---",
        "### 🧬 NPK Status & Detailed Action Plan",
        "| Nutrient | Reading | Band | Priority |",
        "|:---------|--------:|:----:|:--------:|",
        f"| 🟢 Nitrogen (N) | {round(N,0) if N else '—'} mg/kg | {_icon(bands.get('N','unknown'))} | {'🔴 High' if bands.get('N')=='low' else ('🟠 Monitor' if bands.get('N')=='high' else '🟢 Low')} |",
        f"| 🟡 Phosphorus (P) | {round(P,0) if P else '—'} mg/kg | {_icon(bands.get('P','unknown'))} | {'🔴 High' if bands.get('P')=='low' else ('🟠 Monitor' if bands.get('P')=='high' else '🟢 Low')} |",
        f"| 🔵 Potassium (K) | {round(K,0) if K else '—'} mg/kg | {_icon(bands.get('K','unknown'))} | {'🔴 High' if bands.get('K')=='low' else ('🟠 Monitor' if bands.get('K')=='high' else '🟢 Low')} |",
        "",
    ]
    
    # Generate 100% crop-specific fertilizer dosages via Groq
    try:
        if "__failed__" not in (prof or {}):
            ai_prompt = f"""
As an expert agronomist, write a detailed fertilizer action plan for **{ctitle}**.
Current Soil Status:
- Nitrogen: {bands.get('N')} ({N} mg/kg)
- Phosphorus: {bands.get('P')} ({P} mg/kg)
- Potassium: {bands.get('K')} ({K} mg/kg)
- pH: {pH} | EC: {ec} µS/cm | Moisture: {h}%

Write 3 short sections: "#### 🟢 Nitrogen Action", "#### 🟡 Phosphorus Action", and "#### 🔵 Potassium Action".
For any deficient nutrient, provide EXACT chemical fertilizers (with kg/acre), exact timing based on {ctitle} growth stages, and an organic alternative. If adequate, say so. Keep it dense and highly specific to {ctitle}-growing practices in Indian soils. Return ONLY markdown.
"""
            ai_resp = call_groq("Expert Agronomist. Respond in pure markdown.",
                                ai_prompt, max_tokens=1200)
            lines.append(ai_resp["raw"] if ai_resp["status"] == "success"
                         else "*Could not generate dynamic crop dosage.*")
        else:
            lines.append(f"*(AI failed to load specific profile for {ctitle})*")
    except Exception as e:
        print("Groq dosage error:", e)
        lines.append("*Could not generate dynamic crop dosage.*")
    if micro:
        lines += ["---", "### 🔬 Secondary Nutrient & Micronutrient Alerts"] + micro
    if irr_note:
        lines += ["---", "### 💧 Irrigation Recommendation", irr_note]
    lines += [
        "---",
        "### ⚠️ Risk Alerts",
        *[f"- {a}" for a in ctx.get("alerts", ["✅ No alerts"])],
        "---",
        "### 📋 Action Priority Summary",
        f"| Priority | Action | Timing |",
        f"|:--------:|:-------|:-------|",
    ]
    priority = 1
    if ph_action:  lines.append(f"| #{priority} 🔴 Critical | Correct soil pH | This week"); priority += 1
    if ec_action:  lines.append(f"| #{priority} 🔴 Critical | Reduce salinity (leach) | This week"); priority += 1
    if bands.get("N") == "low":  lines.append(f"| #{priority} 🟠 Urgent | Apply {ctitle}-specific N fertilizer (see protocol) | Early growth stages"); priority += 1
    if bands.get("P") == "low":  lines.append(f"| #{priority} 🟠 Urgent | Apply {ctitle}-specific P fertilizer (see protocol) | Basal/Pre-flowering"); priority += 1
    if bands.get("K") == "low":  lines.append(f"| #{priority} 🟠 Urgent | Apply {ctitle}-specific K fertilizer (see protocol) | Fruiting stage"); priority += 1
    if micro:  lines.append(f"| #{priority} 🟡 Important | Micronutrient correction | Within 2 weeks"); priority += 1
    if priority == 1:  lines.append("| ✅ Maintenance | Continue current fertilizer program | Ongoing |")
    lines += [
        "",
        f"> **Bottom line:** {nl}. **Crop risk:** {sl}.",
        "> *Kronos AI v2.2 — Llama 3.3 70B · Open-Meteo · Deterministic Soil Science*"
    ]
    raw = "\n".join(lines)
    return md(raw), raw

# ─────────────────── Weather ───────────────────


def geocode_city(city):
    # Extract just the primary city name (before any comma) for best API match
    primary = city.split(',')[0].strip()
    for attempt_name in [primary, city]:   # try short form first
        try:
            r = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                             params={"name": attempt_name, "count": 1, "language": "en", "format": "json"}, timeout=8)
            r.raise_for_status()
            data = r.json()
            if not data.get("results"): continue
            res = data["results"][0]
            label = f"{res.get('name','')}, {res.get('admin1','')}, {res.get('country','')}".strip(", ")
            return float(res["latitude"]), float(res["longitude"]), label
        except Exception as e:
            print(f"Geocoding error ({attempt_name}): {e}")
    return None


def fetch_forecast(lat, lon, days=14):
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", timeout=12, params={
            "latitude": lat, "longitude": lon, "timezone": "auto",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,windspeed_10m_max",
            "forecast_days": days,
        })
        r.raise_for_status()
        d = r.json().get("daily", {})
        times = d.get("time",[]); tmax = d.get("temperature_2m_max",[]); tmin = d.get("temperature_2m_min",[])
        prcp  = d.get("precipitation_sum",[]); pop = d.get("precipitation_probability_max",[])
        wind  = d.get("windspeed_10m_max",[])
        n = min(len(times), len(tmax), len(tmin), len(prcp), len(pop))
        return [{"date": times[i], "tmax": tmax[i], "tmin": tmin[i],
                 "precip_sum": prcp[i], "pop": pop[i],
                 "wind": wind[i] if i < len(wind) else None}
                for i in range(n)]
    except Exception as e:
        print(f"Forecast error: {e}"); return None


def _find_longest_run(flags, min_len=3):
    best_start = best_len = -1; cur_start = None
    for i, ok in enumerate(flags + [False]):
        if ok and cur_start is None: cur_start = i
        elif (not ok) and cur_start is not None:
            L = i - cur_start
            if L > best_len: best_start, best_len = cur_start, L
            cur_start = None
    return (best_start, best_start + best_len - 1) if best_len >= min_len else None


def derive_weather_signals(daily):
    if not daily: return {"summary": "Weather unavailable.", "signals": [], "windows": {}, "notes": []}
    signals, notes = [], []
    rain_days, heat_days, cool_days, germ_days, comfy = [], [], [], [], []
    total_rain = 0.0
    for d in daily:
        tmax = d["tmax"]; tmin = d["tmin"]; pop = (d["pop"] or 0) / 100.0
        rain = d["precip_sum"] or 0.0; total_rain += rain
        likely_rain = pop >= 0.5 or rain >= 5.0
        if likely_rain: rain_days.append(d["date"])
        if tmax and tmax >= 36: heat_days.append(d["date"])
        if tmin and tmin <= 10: cool_days.append(d["date"])
        is_comfy = tmax and 20 <= tmax <= 32 and not likely_rain
        comfy.append(bool(is_comfy))
        if is_comfy: germ_days.append(d["date"])
    best = _find_longest_run(comfy, min_len=3)
    best_sowing = None
    if best:
        i, j = best; best_sowing = {"start": daily[i]["date"], "end": daily[j]["date"], "days": j-i+1}
        notes.append(f"Best sowing window: {best_sowing['start']} → {best_sowing['end']} ({best_sowing['days']} days)")
    heavy = []
    for k in range(max(0, len(daily)-4)):
        span = daily[k:k+5]
        cnt  = sum(1 for x in span if ((x["pop"] or 0)/100 >= 0.5) or ((x["precip_sum"] or 0) >= 10))
        if cnt >= 2: heavy.append({"start": span[0]["date"], "end": span[-1]["date"], "count": cnt})
    if rain_days:  signals.append("Rain days: " + ", ".join(rain_days[:10]))
    if heat_days:  signals.append("Heat stress days (≥36°C): " + ", ".join(heat_days[:10]))
    if cool_days:  signals.append("Cool nights (≤10°C): " + ", ".join(cool_days[:10]))
    if germ_days:  signals.append("Field-work friendly: " + ", ".join(germ_days[:5]))
    return {"summary": " | ".join(signals) or "No major weather flags.",
            "total_rain_14d": round(total_rain, 1),
            "signals": signals,
            "windows": {"rain_days": rain_days, "heat_days": heat_days,
                        "cool_days": cool_days, "germination_good": germ_days,
                        "best_sowing": best_sowing, "heavy_rain_clusters": heavy},
            "notes": notes}


def build_weather_ctx(prefs):
    ctx = {"available": False, "message": "Weather not configured."}
    lat = prefs.get("lat"); lon = prefs.get("lon"); city = prefs.get("location")
    resolved = None
    if (lat is None or lon is None) and city:
        g = geocode_city(city)
        if g: lat, lon, resolved = g
    if lat is None or lon is None:
        ctx["message"] = "Geocoding failed."; return ctx
    daily   = fetch_forecast(float(lat), float(lon), 14) or []
    signals = derive_weather_signals(daily)
    ctx.update({"available": True, "lat": lat, "lon": lon,
                "location": resolved or city or f"{lat:.3f},{lon:.3f}",
                "crop": prefs.get("crop"), "daily": daily, "signals": signals})
    return ctx


def fetch_seasonal(lat, lon):
    try:
        r = requests.get("https://seasonal-api.open-meteo.com/v1/seasonal", timeout=30, params={
            "latitude": lat, "longitude": lon,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
            "timezone": "auto",
        })
        r.raise_for_status()
        daily = r.json().get("daily", {}); times = daily.get("time", [])
        if not times: return None
        tmax_cols = [v for k, v in daily.items() if k.startswith("temperature_2m_max")]
        tmin_cols = [v for k, v in daily.items() if k.startswith("temperature_2m_min")]
        prcp_cols = [v for k, v in daily.items() if k.startswith("precipitation_sum")]
        def smean(cols, i):
            vals = [float(c[i]) for c in cols if i < len(c) and c[i] is not None]
            return float(np.mean(vals)) if vals else None
        monthly = defaultdict(lambda: {"tmax":[], "tmin":[], "precip":[]})
        for i, ds in enumerate(times):
            try:
                key = datetime.strptime(ds, "%Y-%m-%d").strftime("%Y-%m")
                tm = smean(tmax_cols, i); tn = smean(tmin_cols, i); pr = smean(prcp_cols, i)
                if tm is not None: monthly[key]["tmax"].append(tm)
                if tn is not None: monthly[key]["tmin"].append(tn)
                if pr is not None: monthly[key]["precip"].append(pr)
            except Exception: continue
        result = []
        for key in sorted(monthly.keys())[:6]:
            m = monthly[key]; dt = datetime.strptime(key + "-01", "%Y-%m-%d")
            result.append({"month": key, "month_label": dt.strftime("%B %Y"),
                           "avg_tmax":     round(float(np.mean(m["tmax"])), 1)  if m["tmax"]  else 32.0,
                           "avg_tmin":     round(float(np.mean(m["tmin"])), 1)  if m["tmin"]  else 22.0,
                           "total_precip": round(float(np.sum(m["precip"])), 1) if m["precip"] else 50.0})
        return result or None
    except Exception as e:
        print(f"Seasonal error: {e}"); return None

# ─────────────────── Auto-init weather on startup ───────────────────
def _init_weather():
    global weather_context, weather_prefs
    print("🌤 Auto-loading 14-day Kolkata forecast…")
    weather_prefs   = {"location": DEFAULT_CITY, "lat": DEFAULT_LAT, "lon": DEFAULT_LON, "crop": ""}
    weather_context = build_weather_ctx(weather_prefs)
    if weather_context.get("available"):
        sig  = weather_context.get("signals", {})
        days = len(weather_context.get("daily", []))
        rain = sig.get("total_rain_14d", "?")
        print(f"✅ Weather ready: {days} days, {rain}mm total rain, {DEFAULT_CITY}")
    else:
        print(f"⚠️ Weather init failed: {weather_context.get('message')}")

threading.Thread(target=_init_weather, daemon=True).start()

# ─────────────────── Chat ───────────────────

def is_agri(q):
    terms = ["soil","crop","fertilizer","npk","nitrogen","phosphorus","potassium","humidity",
             "moisture","ph","temperature","agriculture","farm","loamy","clayey","sandy",
             "salinity","ec","conductivity","irrigation","seed","harvest","yield","pesticide",
             "manure","weather","rain","monsoon","sowing","germination","season","water",
             "plant","grow","field","kharif","rabi","disease","pest","weed","spray"]
    return any(t in q.lower() for t in terms)


def weather_snippet_for_prompt():
    if not weather_context or not weather_context.get("available"):
        return "Weather not yet loaded."
    sig  = weather_context.get("signals", {})
    loc  = weather_context.get("location", "")
    crop = weather_context.get("crop") or "field"
    bw   = sig.get("windows", {}).get("best_sowing")
    rain = sig.get("total_rain_14d", "?")
    extra = f" | Best sowing: {bw['start']}→{bw['end']}" if bw else ""
    return (f"14-Day Forecast @ {loc} (crop: {crop}): {sig.get('summary','n/a')}"
            f" | Total 14-day rain: {rain}mm{extra}")


def build_weather_prompt_block(n_days=14):
    if not weather_context.get("available"): return ""
    daily = weather_context.get("daily", [])[:n_days]
    if not daily: return ""
    lines = ["\n14-Day Weather Forecast (use this for all irrigation and timing advice):"]
    for d in daily:
        rain  = "🌧" if (d.get("precip_sum") or 0) > 1 else "☀"
        heat  = " ⚠HEAT" if (d.get("tmax") or 0) >= 36 else ""
        lines.append(f"  {d['date']}: {rain} {d.get('tmax','?')}°C/{d.get('tmin','?')}°C "
                     f"Rain {d.get('precip_sum',0):.1f}mm  {d.get('pop',0)}% chance{heat}")
    sig   = weather_context.get("signals", {})
    notes = sig.get("notes", [])
    if notes: lines.append("  Key signals: " + "; ".join(notes))
    return "\n".join(lines)


def get_chat_response(user_q, language="en-US", force_hours=None, include_weather=False,
                      history=None, date_from=None, date_to=None):
    global cached_analysis, last_analysis_time
    lang_map = {"en-US": "English", "en-IN": "English",
                "hi-IN": "Hindi", "bn-IN": "Bengali"}
    lang = lang_map.get(language, "English")

    # ── Historical range mode: analyse a specific IST date span ──
    if date_from or date_to:
        df, err = read_csvs_between(date_from, date_to)
        if df is None:
            user_prompt = (f"Respond entirely in {lang}.\n"
                           f"(Soil data request for range {date_from or 'start'} → {date_to or 'end'} "
                           f"failed: {err}. Tell the farmer no data exists for that period and suggest "
                           f"an available range.)\n\nFarmer's question: {user_q}")
        else:
            ctx = build_context(df)
            l = ctx.get("latest", {}); b = ctx.get("fert_meta", {}).get("bands", {})
            note = "⚠️ SENSOR DISCONNECTED" if ctx.get("sensor", {}).get("disconnected") else "✅ SENSOR OK"
            soil_ctx = (f"\nHISTORICAL SOIL DATA — window {date_from or 'start'} → {date_to or 'end'} "
                        f"({len(df)} readings) ({note}):"
                        f"\n  Averages over window — Temp={l.get('temperature','n/a')}°C  "
                        f"Moisture={l.get('humidity','n/a')}%  EC={l.get('conductivity','n/a')} µS/cm  pH={l.get('pH','n/a')}"
                        f"\n  N={l.get('nitrogen','n/a')} mg/kg [{b.get('N','?')}]"
                        f"  P={l.get('phosphorus','n/a')} mg/kg [{b.get('P','?')}]"
                        f"  K={l.get('potassium','n/a')} mg/kg [{b.get('K','?')}]"
                        f"\n  Soil type: {ctx.get('soil_type','?')}"
                        f"\n  Risk alerts: {', '.join(ctx.get('alerts',['none']))}")
            wx_block = build_weather_prompt_block(14) if include_weather else weather_snippet_for_prompt()
            user_prompt = (f"Respond entirely in {lang}.\n"
                           f"You are analysing HISTORICAL sensor data from {date_from or 'start'} to "
                           f"{date_to or 'end'}. Base all answers on that window, not today's conditions."
                           f"\n{soil_ctx}\n{wx_block}\n\nFarmer's question: {user_q}")
        return call_groq(SYSTEM_PROMPT, user_prompt, history=history)

    do_fresh = force_hours is not None or not last_analysis_time or \
               (datetime.now(timezone.utc) - last_analysis_time > timedelta(minutes=ANALYSIS_CACHE_MINUTES))

    soil_ctx = ""
    if do_fresh:
        df = read_latest_csvs(force_hours)
        in_window = df is not None and not df.empty
        if force_hours and not in_window:
            # requested window has no rows (sensor offline longer than window)
            # → fall back to most recent available, clearly labelled
            df = read_latest_csvs(None)
        if df is not None and not df.empty:
            ctx = build_context(df)
            cached_analysis = ctx; last_analysis_time = datetime.now(timezone.utc)
            l = ctx.get("latest", {}); b = ctx.get("fert_meta", {}).get("bands", {})
            disc = ctx.get("sensor", {}).get("disconnected")
            note = ("⚠️ SENSOR DISCONNECTED — showing last available reading"
                    if disc else "✅ SENSOR OK")
            scope = (f"last {force_hours:g} hour(s)" if (force_hours and in_window)
                     else ("most recent available (requested window had no data)"
                           if force_hours else "live"))
            soil_ctx = (f"\nSoil Data · scope: {scope} ({note}):"
                        f"\n  Temp={l.get('temperature','n/a')}°C  Moisture={l.get('humidity','n/a')}%"
                        f"  EC={l.get('conductivity','n/a')} µS/cm  pH={l.get('pH','n/a')}"
                        f"\n  N={l.get('nitrogen','n/a')} mg/kg [{b.get('N','?')}]"
                        f"  P={l.get('phosphorus','n/a')} mg/kg [{b.get('P','?')}]"
                        f"  K={l.get('potassium','n/a')} mg/kg [{b.get('K','?')}]"
                        f"\n  Soil type: {ctx.get('soil_type','?')}"
                        f"\n  Risk alerts: {', '.join(ctx.get('alerts',['none']))}")
    elif cached_analysis:
        l = cached_analysis.get("latest", {}); b = cached_analysis.get("fert_meta", {}).get("bands", {})
        soil_ctx = (f"\nCached Soil (< 30 min old): type={cached_analysis.get('soil_type','?')}"
                    f"  N={l.get('nitrogen','?')}[{b.get('N','?')}]"
                    f"  P={l.get('phosphorus','?')}[{b.get('P','?')}]"
                    f"  K={l.get('potassium','?')}[{b.get('K','?')}]")

    wx_block = build_weather_prompt_block(14) if include_weather else weather_snippet_for_prompt()

    user_prompt = f"Respond entirely in {lang}.\n{soil_ctx}\n{wx_block}\n\nFarmer's question: {user_q}"
    if not is_agri(user_q):
        user_prompt += "\n(Note: off-topic question — give a brief helpful answer, then naturally redirect to agricultural assistance.)"
    return call_groq(SYSTEM_PROMPT, user_prompt, history=history)

# ─────────────────── Flask ───────────────────
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024   # 16 MB request cap (disk-fill guard)

# ── Lightweight per-IP rate limiter for LLM/expensive endpoints ──
import collections
from functools import wraps as _wraps
_RATE_BUCKETS = collections.defaultdict(collections.deque)
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "15"))


def _rate_limited() -> bool:
    ip = (request.headers.get("X-Forwarded-For", request.remote_addr or "?")
          ).split(",")[0].strip()
    now = time.time()
    q = _RATE_BUCKETS[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT_PER_MIN:
        return True
    q.append(now)
    return False


def protect_llm(fn):
    """Guards Groq-quota endpoints from hammering (per-IP, sliding 60s)."""
    @_wraps(fn)
    def wrapper(*a, **kw):
        if _rate_limited():
            return jsonify({"status": "error",
                            "message": f"Rate limit reached ({RATE_LIMIT_PER_MIN}/min). Please wait a moment."}), 429
        return fn(*a, **kw)
    return wrapper


@app.after_request
def _sec_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return resp


@app.route("/")
def index():
    # Try loading templates in priority order
    for _name in ["template_kronos.html", "template_apple.html", "template_mobile.html"]:
        _tpl = Path(__file__).parent / _name
        if _tpl.exists():
            return render_template_string(_tpl.read_text(encoding="utf-8"))
    return render_template_string(HTML_TEMPLATE)


@app.route("/dashboard_data")
def dashboard_data():
    df = read_latest_csvs(window_hours=6, allow_historical=True)
    if df is None or df.empty:
        return jsonify({"status": "no_data", "latest": {}, "bands": {}})
    ctx = build_context(df)
    l   = ctx.get("latest", {}); bands = ctx.get("fert_meta", {}).get("bands", {})
    def safe(v, d=1):
        try:
            f = float(v)
            return None if (math.isnan(f) or math.isinf(f)) else round(f, d)
        except Exception:
            return None
    return jsonify({"status": "ok",
                    "latest": {"temperature":  safe(l.get("temperature")),
                                "humidity":     safe(l.get("humidity")),
                                "conductivity": safe(l.get("conductivity"), 0),
                                "pH":           safe(l.get("pH")),
                                "nitrogen":     safe(l.get("nitrogen")),
                                "phosphorus":   safe(l.get("phosphorus")),
                                "potassium":    safe(l.get("potassium"))},
                    "bands":      bands,
                    "soil_type":  ctx.get("soil_type", "unknown"),
                    "sensor_ok":  not ctx.get("sensor", {}).get("disconnected", True),
                    "alerts":     ctx.get("alerts", [])})


@app.route("/weather_status")
def weather_status():
    """Return cached weather so the frontend can render it immediately."""
    if not weather_context.get("available"):
        return jsonify({"status": "loading", "message": weather_context.get("message","Loading…")})
    sig  = weather_context.get("signals", {})
    return jsonify({"status": "ok",
                    "weather":   weather_context,
                    "location":  weather_context.get("location"),
                    "total_rain":sig.get("total_rain_14d"),
                    "summary":   sig.get("summary","")})


@app.route("/chat", methods=["POST"])
@protect_llm
def chat():
    p = request.get_json(silent=True) or {}
    msg = (p.get("message") or "").strip()
    if not msg: return jsonify({"status": "error", "message": "Empty message."}), 400
    try: hrs = float(p["window_hours"]) if p.get("window_hours") not in (None,"","null") else None
    except Exception: hrs = None
    history = p.get("history", [])  # conversation history from frontend
    date_from = (p.get("date_from") or "").strip() or None
    date_to   = (p.get("date_to")   or "").strip() or None
    return jsonify(get_chat_response(
        msg,
        language        = p.get("language", "en-US"),
        force_hours     = hrs,
        include_weather = bool(p.get("include_weather", True)),
        history         = history,
        date_from       = date_from,
        date_to         = date_to,
    ))


@app.route("/analyze", methods=["POST"])
@protect_llm
def analyze():
    p = request.get_json(silent=True) or {}
    try: hrs = int(p["window_hours"]) if p.get("window_hours") not in (None,"","null") else None
    except Exception: hrs = None
    window_map = {1: "Last 1 Hour", 6: "Last 6 Hours", 24: "Last 24 Hours", 168: "Last 1 Week"}
    window_label = window_map.get(hrs, "Latest Reading") if hrs else "Latest Reading"
    df = read_latest_csvs(hrs, allow_historical=True)
    if df is None or df.empty:
        return jsonify({"status": "error",
                        "message": "No CSV data found in data/csv/soil_*.csv — check ESP32 pipeline"})
    ctx = build_context(df)
    global cached_analysis, last_analysis_time
    cached_analysis = ctx; last_analysis_time = datetime.now(timezone.utc)
    crop = (p.get("crop") or weather_prefs.get("crop") or "").strip()
    report_html, report_md = format_advisory(ctx, crop, window_label)
    rid = save_report("live", window_label, crop, report_html, report_md, ctx)
    return jsonify({"status": "success", "message": report_html, "raw": report_md,
                    "report_id": rid,
                    "sensor_disconnected": bool(ctx.get("sensor", {}).get("disconnected", False)),
                    "context": _clean_ctx(ctx)})


@app.route("/analyze_range", methods=["POST"])
@protect_llm
def analyze_range():
    """Analyze soil data for a specific IST date range (from/to as YYYY-MM-DD)."""
    global cached_analysis, last_analysis_time
    p = request.get_json(silent=True) or {}
    date_from = (p.get("from") or "").strip()
    date_to   = (p.get("to") or "").strip()
    crop      = (p.get("crop") or weather_prefs.get("crop") or "").strip()
    df, err = read_csvs_between(date_from, date_to)
    if df is None:
        return jsonify({"status": "error", "message": err})
    ctx = build_context(df)
    cached_analysis = ctx; last_analysis_time = datetime.now(timezone.utc)
    label = f"{date_from or 'earliest'} → {date_to or 'latest'} ({len(df)} readings)"
    report_html, report_md = format_advisory(ctx, crop, label)
    rid = save_report("range", label, crop, report_html, report_md, ctx)
    return jsonify({"status": "success", "message": report_html, "raw": report_md,
                    "report_id": rid, "context": _clean_ctx(ctx),
                    "rows": len(df), "range": label})


@app.route("/csv_dates")
def csv_dates():
    """Return the available date range from CSV files for the date picker."""
    try:
        csv_files = sorted(CSV_DIR.glob("soil_*.csv"))
        if not csv_files:
            return jsonify({"status": "ok", "min": None, "max": None, "files": 0})
        dates = []
        for f in csv_files:
            name = f.stem.replace("soil_", "")
            dates.append(name)
        dates.sort()
        return jsonify({"status": "ok", "min": dates[0], "max": dates[-1], "files": len(dates)})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/plan_weather", methods=["POST"])
@protect_llm
def plan_weather():
    global weather_prefs, weather_context
    p    = request.get_json(silent=True) or {}
    loc  = (p.get("location") or DEFAULT_CITY).strip()
    crop = (p.get("crop") or "").strip()
    lat  = p.get("lat"); lon = p.get("lon")
    weather_prefs = {"location": loc, "lat": lat, "lon": lon, "crop": crop}
    if (lat is None or lon is None) and loc:
        g = geocode_city(loc)
        if g: lat, lon, resolved = g; weather_prefs.update({"lat": lat, "lon": lon, "location": resolved})
    weather_context = build_weather_ctx(weather_prefs)
    if not weather_context.get("available"):
        return jsonify({"status": "error", "message": weather_context.get("message"), "weather": weather_context})
    sig = weather_context.get("signals", {}); w = sig.get("windows", {})
    hints = []
    if w.get("best_sowing"): hints.append(f"Best sowing: {w['best_sowing']['start']}→{w['best_sowing']['end']} ({w['best_sowing']['days']} days).")
    if w.get("heat_days"):   hints.append(f"{len(w['heat_days'])} heat-stress days — plan extra irrigation.")
    if w.get("heavy_rain_clusters"): hints.append("Heavy rain clusters detected — time fertilizer pre/post rain.")
    lines = [f"**📍 Location:** {weather_context.get('location')}",
             f"**🌾 Crop:** {crop or 'unspecified'}",
             f"**🌧 Total 14-Day Rain:** {sig.get('total_rain_14d','?')} mm",
             f"**📋 Summary:** {sig.get('summary','No signal.')}"]
    if hints: lines.append("**💡 Planner Notes:** " + " ".join(hints))
    return jsonify({"status": "success", "message": md("\n".join(lines)), "weather": weather_context})


@app.route("/irrigation_plan", methods=["POST"])
@protect_llm
def irrigation_plan():
    global weather_prefs, weather_context
    p = request.get_json(silent=True) or {}
    loc     = (p.get("location") or "").strip()
    crop_in = (p.get("crop") or "").strip()

    # Re-resolve location/crop if the user changed them since the last forecast
    if crop_in:
        weather_prefs["crop"] = crop_in
    current_loc = str(weather_context.get("location") or weather_prefs.get("location") or "")
    if loc and loc.split(",")[0].strip().lower() not in current_loc.lower():
        g = geocode_city(loc)
        if g:
            weather_prefs.update({"location": g[2], "lat": g[0], "lon": g[1]})
            weather_context = {}

    # Weather not loaded yet (startup race / network hiccup) → build it now
    if not weather_context.get("available"):
        print("🌤 Irrigation requested — loading forecast synchronously…")
        weather_prefs.setdefault("location", DEFAULT_CITY)
        weather_prefs.setdefault("lat", DEFAULT_LAT)
        weather_prefs.setdefault("lon", DEFAULT_LON)
        weather_context = build_weather_ctx(weather_prefs)
    if not weather_context.get("available"):
        return jsonify({"status": "error",
                        "message": "Could not load the weather forecast right now (Open-Meteo may be unreachable). Check your connection and retry."})

    daily = weather_context.get("daily") or []
    if not daily: return jsonify({"status": "error", "message": "No forecast data available."})
    crop     = crop_in or weather_context.get("crop") or weather_prefs.get("crop") or "general crop"
    location = weather_context.get("location", "your field")
    profile  = generate_crop_profile(crop)
    irr_hint = profile.get("irrigation_hint","Apply standard irrigation.") if profile and "__failed__" not in profile else "Apply standard irrigation."
    wx_lines = []
    for d in daily[:14]:
        rain = "🌧" if (d.get("precip_sum") or 0) > 1 else "☀"
        heat = " ⚠HEAT" if (d.get("tmax") or 0) >= 36 else ""
        wx_lines.append(f"  {d['date']}: {rain} {d.get('tmax','?')}°C, {d.get('precip_sum',0):.1f}mm rain, {d.get('pop',0)}% chance{heat}")
    resp = call_groq(SYSTEM_PROMPT,
        f"""Crop: {crop.title()}  |  Location: {location}
Crop Irrigation Profile: {irr_hint}

14-Day Forecast:
{chr(10).join(wx_lines)}

Create a detailed 14-day irrigation schedule:
1. One line per day: Date | Action (Irrigate/Skip/Monitor/Alert) | Amount (mm) | Reason
2. 3-line summary of overall strategy for this crop in this weather
3. 3 Critical Watch points with specific trigger conditions
Format as a clean markdown table + bullets. Be precise.""", max_tokens=1800)
    resp["meta"] = {"crop": crop, "location": location}
    return jsonify(resp)


@app.route("/seasonal_plan", methods=["POST"])
@protect_llm
def seasonal_plan():
    p    = request.get_json(silent=True) or {}
    loc  = (p.get("location") or weather_prefs.get("location") or DEFAULT_CITY).strip()
    crop = (p.get("crop")     or weather_prefs.get("crop") or "general crop").strip()
    lat  = float(p.get("lat") or weather_prefs.get("lat") or DEFAULT_LAT)
    lon  = float(p.get("lon") or weather_prefs.get("lon") or DEFAULT_LON)
    if not (lat and lon):
        g = geocode_city(loc)
        if g: lat, lon, _ = g
        else: lat, lon = DEFAULT_LAT, DEFAULT_LON
    monthly = fetch_seasonal(lat, lon)
    if not monthly:
        return jsonify({"status": "error",
                        "message": "Could not fetch ECMWF SEAS5 seasonal forecast. The free service may be momentarily unavailable — please retry in 60 seconds."})
    profile  = generate_crop_profile(crop)
    irr_hint = profile.get("irrigation_hint","Standard practices apply.") if profile and "__failed__" not in profile else "Standard practices apply."
    monthly_txt = "\n".join(
        f"  📅 **{m['month_label']}**: Max {m['avg_tmax']}°C | Min {m['avg_tmin']}°C | Rain ~{m['total_precip']} mm"
        for m in monthly)
    result = call_groq(SYSTEM_PROMPT, f"""Crop: {crop.title()}
Location: {loc} (West Bengal, India)
Crop Irrigation Profile: {irr_hint}

6-Month ECMWF SEAS5 Seasonal Forecast:
{monthly_txt}

Write a professional 6-month seasonal irrigation and crop management plan.
Structure it EXACTLY as:
## Overall Seasonal Strategy (3 sentences max)
## Month-by-Month Plan
For each month use this format:
### [Month Year]
- **Weather Outlook**: ...
- **Crop Stage**: ...
- **Irrigation**: frequency + mm per event
- **Fertilizer**: what to apply and when
- **Risk Alert**: 1 specific risk with mitigation
## Critical Season Alerts (5 farmer action points)

Be specific: use mm, kg/acre, DAS. Make it actionable.""", max_tokens=2200)
    result["monthly_data"] = monthly
    return jsonify(result)


@app.route("/get_weather_plan")
def get_weather_plan():
    if not weather_context.get("available"):
        return jsonify({"status": "loading", "message": "Weather is still loading, please wait…"})
    return jsonify({"status": "success", "weather": weather_context})


# ─────────────────── Plant Disease Detection (unified) ───────────────────
import sys as _sys
_disease_dir = str(Path(__file__).resolve().parent.parent / "plant_disease_detection")
if _disease_dir not in _sys.path:
    _sys.path.insert(0, _disease_dir)

try:
    from disease_engine import (
        run_diagnostic_pipeline as _run_disease_pipeline,
        allowed_file as _disease_allowed_file,
        get_status as _disease_status,
        get_disease_info as _disease_get_info,
        disease_db as _disease_db,
    )
    _DISEASE_AVAILABLE = True
    print("✅ Disease detection engine loaded")
except Exception as _e:
    _DISEASE_AVAILABLE = False
    print(f"⚠️ Disease engine not available: {_e}")

import uuid as _uuid
from werkzeug.utils import secure_filename as _secure_filename

_disease_upload_dir = Path(__file__).resolve().parent.parent / "plant_disease_detection" / "uploads"
_disease_upload_dir.mkdir(parents=True, exist_ok=True)


@app.route("/api/disease/analyze", methods=["POST"])
@protect_llm
def disease_analyze():
    """Unified disease detection endpoint — accepts image upload."""
    if not _DISEASE_AVAILABLE:
        return jsonify({"status": "error", "message": "Disease detection engine not loaded."}), 503
    if request.content_length and request.content_length > app.config["MAX_CONTENT_LENGTH"]:
        return jsonify({"status": "error", "message": "File too large (max 16MB)."}), 413
    file = request.files.get("img") or request.files.get("file") or request.files.get("image")
    if not file or file.filename == "":
        return jsonify({"status": "error", "message": "No image file provided."}), 400
    if not _disease_allowed_file(file.filename):
        return jsonify({"status": "error", "message": "Allowed: PNG, JPG, JPEG, WebP, BMP"}), 400
    safe_name = _secure_filename(file.filename) or "leaf.jpg"
    temp_filename = f"scan_{_uuid.uuid4().hex[:10]}_{safe_name}"
    save_path = str(_disease_upload_dir / temp_filename)
    file.save(save_path)
    try:
        diagnosis = _run_disease_pipeline(save_path)
        return jsonify({
            "status": diagnosis.get("status", "error"),
            "prediction": diagnosis,
            "image_url": f"/api/disease/image/{temp_filename}",
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/disease/image/<path:filename>")
def disease_serve_image(filename):
    """Serve uploaded disease scan images."""
    return send_from_directory(str(_disease_upload_dir), filename)


@app.route("/api/disease/health")
def disease_health():
    if not _DISEASE_AVAILABLE:
        return jsonify({"status": "unavailable"})
    return jsonify({"status": "ok", **_disease_status()})


@app.route("/api/disease/crops")
def disease_crops():
    if not _DISEASE_AVAILABLE:
        return jsonify({"crops": [], "count": 0})
    crops = list(_disease_db.get("crops", {}).keys())
    return jsonify({"crops": crops, "count": len(crops)})


# ─────────────────── Saved Reports ───────────────────

@app.route("/reports")
def reports_index():
    """List saved advisory reports (newest first)."""
    try:
        limit = int(request.args.get("limit", 50))
    except Exception:
        limit = 50
    return jsonify({"status": "ok", "reports": list_reports(max(1, min(limit, 200)))})


@app.route("/reports/<rid>")
def report_detail(rid):
    """Fetch one saved report (sanitized ids only — no path traversal)."""
    if not rid.replace("_", "").isalnum():
        return jsonify({"status": "error", "message": "Invalid report id."}), 400
    f = REPORTS_DIR / f"report_{rid}.json"
    if not f.exists():
        return jsonify({"status": "error", "message": "Report not found."}), 404
    try:
        return jsonify({"status": "ok", "report": json.loads(f.read_text(encoding="utf-8"))})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/reports/<rid>", methods=["DELETE"])
def report_delete(rid):
    if not rid.replace("_", "").isalnum():
        return jsonify({"status": "error", "message": "Invalid report id."}), 400
    f = REPORTS_DIR / f"report_{rid}.json"
    if f.exists():
        try:
            f.unlink()
            return jsonify({"status": "ok"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
    return jsonify({"status": "error", "message": "Report not found."}), 404


# ─────────────────── Field Heatmap (user's heatmap_flask.py, in-process) ────
# The Flask version is mounted directly onto this app — same templates dir,
# same InfluxDB credentials, no second server needed.
_app_dir = str(Path(__file__).resolve().parent)
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)

_heatmap_mod = None
try:
    import importlib as _importlib
    _heatmap_mod = _importlib.import_module("heatmap_flask")
    app.add_url_rule("/heatmap", "heatmap_page", _heatmap_mod.heatmap_page)
    app.add_url_rule("/download/map/<map_key>", "heatmap_download_map",
                     _heatmap_mod.download_map)
    print("✅ Flask heatmap engine mounted at /heatmap")
except Exception as _e:
    print(f"⚠️ Heatmap engine unavailable: {_e}")


@app.route("/api/heatmap/status")
def heatmap_status_api():
    """Device/GPS state for the Heatmap tab pill (uses the engine's 15s cache)."""
    if _heatmap_mod is None:
        return jsonify({"status": "error", "message": "Heatmap engine unavailable."}), 503
    try:
        live, has_gps, ts, _vals, _params = _heatmap_mod.check_device_health()
        return jsonify({"status": "ok",
                        "live": bool(live),
                        "has_gps": bool(has_gps),
                        "last_reading": ts.isoformat() if ts is not None else None,
                        "stale_sec": _heatmap_mod.STALE_THRESHOLD_SEC})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 503


# ─────────────────── Telemetry time-series ───────────────────

@app.route("/api/sensor_series")
def sensor_series():
    """Historical series for the telemetry charts.
    ?window_hours=6   OR   ?from=YYYY-MM-DD&to=YYYY-MM-DD (IST)"""
    window_hours = request.args.get("window_hours", type=int)
    date_from = (request.args.get("from") or "").strip()
    date_to = (request.args.get("to") or "").strip()

    if date_from or date_to:
        df, err = read_csvs_between(date_from, date_to)
        mode = "range"
        label = f"{date_from or 'start'} → {date_to or 'end'}"
    elif window_hours:
        df = read_latest_csvs(window_hours, allow_historical=True)
        mode = "window"
        label = {1: "Last hour", 6: "Last 6 hours", 24: "Last 24 hours",
                 168: "Last week"}.get(window_hours or 0, f"Last {window_hours} hours")
        err = None if df is not None else "No CSV data found."
    else:
        # LIVE view: show only fresh data from the last 15 minutes — never old
        # history. If nothing arrived within that window (15/10/5 min), start
        # the chart from the most recent valid reading and continue live as new
        # values stream in.
        LIVE_WINDOW_MIN = 15
        df = read_latest_csvs(None)
        if df is not None and not df.empty:
            live_cols = [c for c in ("conductivity", "humidity", "nitrogen",
                                     "phosphorus", "potassium", "pH") if c in df.columns]
            cutoff = pd.Timestamp.utcnow() - pd.Timedelta(minutes=LIVE_WINDOW_MIN)
            recent = df[df["dt"] >= cutoff]
            has_valid = lambda d: bool(len(d)) and d[live_cols].notna().any().any()
            if has_valid(recent):
                df = recent
                mode = "live"
                label = f"Live · last {LIVE_WINDOW_MIN} min"
            else:
                # No fresh data → seed the chart with the last valid reading.
                valid_rows = df[df[live_cols].notna().any(axis=1)] if live_cols else df
                seed = (valid_rows.tail(1) if not valid_rows.empty else df.tail(1))
                df = seed
                mode = "live"
                label = "Live · starting from last reading"
        else:
            mode = "live"
            label = "Live"
        err = None if df is not None and not df.empty else "No CSV data found."

    if df is None or df.empty:
        return jsonify({"status": "error", "message": err or "No data."})

    # If an explicitly selected window contains ONLY disconnect-junk (all
    # channels NaN), widen to most recent available so the dashboard isn't a
    # blank screen. Live mode handles its own fallback above.
    core_cols = [c for c in ("conductivity", "humidity", "nitrogen",
                             "phosphorus", "potassium", "pH") if c in df.columns]
    widened = False
    if core_cols and window_hours and not (date_from or date_to) \
            and not df[core_cols].notna().any().any():
        wider = read_latest_csvs(None)
        if wider is not None and not wider.empty:
            df = wider
            widened = True

    ctx = build_context(df)

    # downsample to a chart-friendly length (keep last row)
    target = 240
    step = max(1, len(df) // target)
    sub = df.iloc[::step]
    if sub.iloc[-1]["dt"] != df.iloc[-1]["dt"]:
        sub = pd.concat([sub, df.iloc[[-1]]])

    times = []
    if len(sub) > 1:
        span_sec = (sub["dt"].iloc[-1] - sub["dt"].iloc[0]).total_seconds()
    else:
        span_sec = 0
    # Live/short windows: time-only labels (no date clutter under the charts).
    # Multi-day windows: day labels only.
    tfmt = "%H:%M" if span_sec <= 86400 else "%d %b"
    times = [t.strftime(tfmt) if hasattr(t, "strftime") else str(t)
             for t in sub["dt"]]
    series = {}
    for col in FIELDS:  # includes temperature, humidity, conductivity, pH, N, P, K
        if col in sub.columns:
            vals = pd.to_numeric(sub[col], errors="coerce")
            series[col] = [None if pd.isna(v) else round(float(v), 2) for v in vals]

    l = ctx.get("latest", {})
    bands = ctx.get("fert_meta", {}).get("bands", {})
    def safe(v, d=1):
        try:
            f = float(v)
            return None if (math.isnan(f) or math.isinf(f)) else round(f, d)
        except Exception:
            return None
    return jsonify({"status": "ok", "mode": mode,
                    "label": label + (" · no valid readings in window — showing most recent data" if widened else ""),
                    "widened": widened,
                    "count": int(len(df)),
                    "times": times, "series": series,
                    "latest": {"temperature": safe(l.get("temperature")),
                               "humidity": safe(l.get("humidity")),
                               "conductivity": safe(l.get("conductivity"), 0),
                               "pH": safe(l.get("pH")),
                               "nitrogen": safe(l.get("nitrogen")),
                               "phosphorus": safe(l.get("phosphorus")),
                               "potassium": safe(l.get("potassium"))},
                    "bands": bands,
                    "soil_type": ctx.get("soil_type", "unknown"),
                    "sensor_ok": not ctx.get("sensor", {}).get("disconnected", True),
                    "alerts": ctx.get("alerts", [])})


# ─────────────────────────────────────────────────────────────────────
#  HTML TEMPLATE
# ─────────────────────────────────────────────────────────────────────
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>Kronos AI – Smart Farm Intelligence</title>
  <meta name="description" content="Kronos AI: real-time soil intelligence, 14-day weather, and AI-powered seasonal irrigation planning for Indian farmers."/>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet"/>
  <style>
    /* ── Tokens ── */
    :root{
      --sb:#0b1f13; --sb2:#112918;
      --brand:#1dbe85; --bd:#12a06e; --bl:#e6f9f3; --bll:#f0fdf8;
      --bg:#f0f4f0; --card:#ffffff; --card2:#f8fbf8;
      --txt:#182818; --mut:#607060; --muted2:#8a9e8a;
      --bdr:#d8e8d8; --bdr2:#e8f0e8;
      --shd:0 2px 12px rgba(0,0,0,.065);
      --shd2:0 4px 24px rgba(0,0,0,.10);
      --rad:14px; --rad2:10px;
      --sw:220px; --cw:0px;
      --red:#ef4444; --amber:#f59e0b; --blue:#3b82f6; --indigo:#6366f1;
    }
    *{box-sizing:border-box;margin:0;padding:0;}
    body{font-family:'Inter',sans-serif;background:var(--bg);color:var(--txt);
         height:100vh;display:grid;grid-template-columns:var(--sw) 1fr;overflow:hidden;}
    ::-webkit-scrollbar{width:4px;} ::-webkit-scrollbar-thumb{background:#c0d0c0;border-radius:8px;}

    /* ── SIDEBAR ── */
    #sidebar{background:var(--sb);display:flex;flex-direction:column;overflow:hidden;
             box-shadow:2px 0 20px rgba(0,0,0,.25);}
    .sb-brand{display:flex;align-items:center;gap:12px;padding:24px 18px 22px;
              border-bottom:1px solid rgba(255,255,255,.06);}
    .sb-logo{width:38px;height:38px;border-radius:11px;object-fit:contain;
             background:#fff;padding:3px;flex-shrink:0;
             box-shadow:0 2px 8px rgba(0,0,0,.3);}
    .sb-name{display:flex;flex-direction:column;}
    .sb-title{font-size:14px;font-weight:800;color:#fff;letter-spacing:.1px;}
    .sb-sub  {font-size:9px;font-weight:500;color:rgba(255,255,255,.35);letter-spacing:.5px;text-transform:uppercase;margin-top:1px;}
    .sb-section{padding:14px 18px 6px;font-size:9px;font-weight:700;color:rgba(255,255,255,.25);
                text-transform:uppercase;letter-spacing:1px;}
    .nav-btn{display:flex;align-items:center;gap:11px;padding:11px 18px;
             color:rgba(255,255,255,.45);font-size:13px;font-weight:500;
             cursor:pointer;border-left:3px solid transparent;transition:all .16s;user-select:none;
             margin:1px 0;}
    .nav-btn svg{width:16px;height:16px;flex-shrink:0;}
    .nav-btn:hover{background:rgba(255,255,255,.055);color:rgba(255,255,255,.82);}
    .nav-btn.active{background:rgba(29,190,133,.14);color:var(--brand);
                    border-left-color:var(--brand);font-weight:600;}
    .nav-badge{margin-left:auto;background:var(--brand);color:#fff;border-radius:20px;
               font-size:9px;font-weight:700;padding:2px 7px;letter-spacing:.3px;}
    .sb-weather-mini{margin:12px 14px;padding:12px 14px;background:rgba(29,190,133,.1);
                     border:1px solid rgba(29,190,133,.2);border-radius:10px;}
    .swm-loc{font-size:10px;font-weight:700;color:var(--brand);margin-bottom:4px;}
    .swm-val{font-size:11px;color:rgba(255,255,255,.55);line-height:1.5;}
    .sb-footer{margin-top:auto;padding:14px 18px;border-top:1px solid rgba(255,255,255,.06);
               display:flex;align-items:center;gap:8px;}
    .dot-live{width:7px;height:7px;border-radius:50%;background:var(--brand);
              box-shadow:0 0 8px var(--brand);animation:pulse 2s ease-in-out infinite;flex-shrink:0;}
    @keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.5;transform:scale(0.8)}}
    .sb-footer-txt{font-size:10px;font-weight:600;color:rgba(255,255,255,.28);line-height:1.4;}

    /* ── MAIN ── */
    #main{display:flex;flex-direction:column;overflow:hidden;}
    .page{display:none;flex-direction:column;flex:1;overflow:hidden;}
    .page.active{display:flex;}

    /* topbar */
    .topbar{display:flex;align-items:center;justify-content:space-between;
            padding:14px 28px;background:var(--card);border-bottom:1px solid var(--bdr);
            flex-shrink:0;box-shadow:0 1px 4px rgba(0,0,0,.04);}
    .topbar-left{display:flex;align-items:center;gap:12px;}
    .topbar h2{font-size:18px;font-weight:800;letter-spacing:-.2px;}
    .topbar-right{display:flex;align-items:center;gap:10px;}
    .tb-chip{display:flex;align-items:center;gap:6px;padding:6px 12px;
             background:var(--bll);border:1px solid var(--bdr2);border-radius:20px;
             font-size:11px;font-weight:600;color:var(--mut);}
    .tb-chip svg{width:13px;height:13px;color:var(--brand);}

    /* scroll */
    .scroll-area{flex:1;overflow-y:auto;padding:22px 28px;display:flex;flex-direction:column;gap:20px;}

    /* card */
    .card{background:var(--card);border:1px solid var(--bdr);border-radius:var(--rad);
          box-shadow:var(--shd);padding:18px 20px;}
    .card-lbl{font-size:10px;font-weight:800;color:var(--muted2);text-transform:uppercase;
              letter-spacing:1px;margin-bottom:14px;}
    .sec-hdr{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;}
    .sec-hdr .card-lbl{margin-bottom:0;}

    /* ── SENSOR GRID ── */
    .sensor-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;}
    .gauge-card{display:flex;flex-direction:column;align-items:center;}
    .gauge-svg{width:100%;max-width:190px;}

    /* npk */
    .npk-row{margin-bottom:14px;} .npk-row:last-child{margin-bottom:0;}
    .npk-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;}
    .npk-left{display:flex;align-items:center;gap:6px;}
    .npk-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;}
    .npk-name{font-size:12px;font-weight:600;}
    .npk-right{display:flex;align-items:baseline;gap:3px;}
    .npk-val{font-size:15px;font-weight:800;} .npk-unit{font-size:10px;color:var(--mut);}
    .npk-band{font-size:9px;font-weight:700;padding:2px 7px;border-radius:10px;margin-left:4px;}
    .band-low{background:#fee2e2;color:#b91c1c;} .band-ok{background:#d1fae5;color:#065f46;} .band-high{background:#fef3c7;color:#92400e;} .band-unk{background:#f1f5f1;color:var(--mut);}
    .bar-track{height:6px;background:#e5ede5;border-radius:8px;overflow:hidden;}
    .bar-fill{height:100%;border-radius:8px;width:0;transition:width 1.2s cubic-bezier(.4,0,.2,1);}
    .bn{background:linear-gradient(90deg,#1dbe85,#059b6a);}
    .bp{background:linear-gradient(90deg,#f59e0b,#d97706);}
    .bk{background:linear-gradient(90deg,#6366f1,#4338ca);}

    /* temp */
    .temp-card{display:flex;flex-direction:column;align-items:center;justify-content:center;
               gap:5px;min-height:155px;position:relative;}
    .temp-num{font-size:52px;font-weight:900;line-height:1;letter-spacing:-2px;}
    .temp-unit{font-size:16px;font-weight:300;color:var(--mut);}
    .temp-label{font-size:9px;font-weight:700;color:var(--muted2);text-transform:uppercase;letter-spacing:.8px;}

    /* status */
    .status-bar{display:flex;align-items:center;gap:9px;padding:10px 16px;
                border-radius:10px;font-size:12px;font-weight:600;}
    .s-ok {background:linear-gradient(90deg,#d1fae5,#e6f9f3);color:#065f46;border:1px solid #a7f3d0;}
    .s-bad{background:linear-gradient(90deg,#fee2e2,#fef2f2);color:#b91c1c;border:1px solid #fca5a5;}
    .s-na {background:var(--bll);color:var(--mut);border:1px solid var(--bdr2);}

    /* weather rows (dashboard) */
    .weather-strip{display:flex;gap:8px;overflow-x:auto;padding-bottom:4px;}
    .wd-card{flex-shrink:0;min-width:82px;background:var(--card);border:1px solid var(--bdr);
             border-radius:12px;padding:11px 8px;display:flex;flex-direction:column;
             align-items:center;gap:4px;font-size:11px;transition:all .18s;cursor:default;}
    .wd-card:hover{border-color:var(--brand);transform:translateY(-2px);box-shadow:0 4px 14px rgba(29,190,133,.15);}
    .wd-day {font-size:9px;font-weight:800;color:var(--mut);text-transform:uppercase;letter-spacing:.5px;}
    .wd-icon{width:22px;height:22px;}
    .wd-temp{font-weight:700;font-size:13px;}
    .wd-rain{color:var(--blue);font-size:10px;font-weight:600;}
    .wd-heat{color:var(--red);font-size:9px;font-weight:700;background:#fee2e2;padding:1px 5px;border-radius:6px;}

    /* action btns */
    .action-row{display:flex;gap:12px;}
    .btn-outline{flex:1;padding:11px 16px;border:2px solid var(--brand);background:transparent;
                 color:var(--brand);border-radius:var(--rad2);font-size:13px;font-weight:700;
                 cursor:pointer;transition:all .18s;font-family:inherit;
                 display:flex;align-items:center;justify-content:center;gap:7px;}
    .btn-outline:hover:not(:disabled){background:var(--bl);transform:translateY(-1px);}
    .btn-solid {flex:1;padding:11px 16px;border:none;background:var(--brand);color:#fff;
                border-radius:var(--rad2);font-size:13px;font-weight:700;cursor:pointer;
                transition:all .18s;font-family:inherit;
                display:flex;align-items:center;justify-content:center;gap:7px;
                box-shadow:0 4px 16px rgba(29,190,133,.35);}
    .btn-solid:hover:not(:disabled){background:var(--bd);transform:translateY(-1px);box-shadow:0 6px 20px rgba(29,190,133,.45);}
    .btn-sm   {padding:8px 14px;font-size:12px;flex:unset;}
    .btn-outline:disabled,.btn-solid:disabled{opacity:.5;cursor:not-allowed;transform:none;box-shadow:none;}

    /* analysis inline */
    #analysis-panel{display:none;}

    /* ── WEATHER PAGE ── */
    .form-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:18px;}
    .f-lbl{display:block;font-size:10px;font-weight:700;color:var(--mut);
           text-transform:uppercase;letter-spacing:.6px;margin-bottom:7px;}
    .f-inp{width:100%;padding:11px 14px;border:1.5px solid var(--bdr);border-radius:var(--rad2);
           font-size:13px;font-family:inherit;color:var(--txt);background:#fff;outline:none;
           transition:border-color .18s;}
    .f-inp:focus{border-color:var(--brand);box-shadow:0 0 0 3px rgba(29,190,133,.12);}
    .fc-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(82px,1fr));gap:9px;}
    .fc-card{background:var(--card);border:1px solid var(--bdr);border-radius:12px;
             padding:11px 7px;display:flex;flex-direction:column;align-items:center;gap:4px;
             font-size:11px;transition:all .18s;}
    .fc-card:hover{border-color:var(--brand);transform:translateY(-2px);}
    .fc-d{font-size:9px;font-weight:800;color:var(--mut);text-transform:uppercase;}
    .fc-t{font-size:14px;font-weight:800;}
    .fc-r{color:var(--blue);font-weight:700;font-size:10px;}
    .fc-heat{font-size:8px;color:var(--red);font-weight:700;background:#fee2e2;padding:1px 4px;border-radius:4px;}
    .signals-block{display:flex;flex-wrap:wrap;gap:7px;margin-top:12px;}
    .signal-chip{padding:5px 12px;border-radius:20px;font-size:11px;font-weight:600;
                 display:flex;align-items:center;gap:5px;}
    .sc-rain  {background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;}
    .sc-heat  {background:#fff7ed;color:#c2410c;border:1px solid #fed7aa;}
    .sc-sow   {background:#f0fdf4;color:#166534;border:1px solid #bbf7d0;}
    .sc-note  {background:#faf5ff;color:#6b21a8;border:1px solid #e9d5ff;}

    /* ── ASSISTANCE TAB ── */
    #pg-assist{background:var(--bg);}
    .assist-layout{display:grid;grid-template-columns:1fr 360px;gap:0;flex:1;overflow:hidden;}
    .assist-chat-area{display:flex;flex-direction:column;overflow:hidden;border-right:1px solid var(--bdr);}
    .chat-msgs{flex:1;overflow-y:auto;padding:20px 24px;display:flex;flex-direction:column;gap:14px;}
    .bubble{max-width:88%;font-size:13px;line-height:1.6;border-radius:16px;padding:11px 15px;animation:fadeUp .25s ease;}
    @keyframes fadeUp{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
    .b-ai  {background:var(--card);color:var(--txt);border-radius:4px 16px 16px 16px;
            align-self:flex-start;border:1px solid var(--bdr2);box-shadow:var(--shd);}
    .b-user{background:var(--brand);color:#fff;border-radius:16px 16px 4px 16px;align-self:flex-end;font-weight:500;}
    .b-ai .md p  {margin-bottom:8px;font-size:13px;line-height:1.65;}
    .b-ai .md h2,.b-ai .md h3{font-size:13px;font-weight:700;margin:12px 0 5px;color:var(--brand);}
    .b-ai .md li {font-size:13px;margin-bottom:5px;}
    .b-ai .md strong{font-weight:700;}
    .b-ai .md table{width:100%;border-collapse:collapse;font-size:12px;margin:8px 0;}
    .b-ai .md th,.b-ai .md td{padding:6px 10px;border:1px solid var(--bdr);text-align:left;}
    .b-ai .md th{background:var(--bll);font-weight:700;}
    .b-ai .md hr{border:none;border-top:1px solid var(--bdr);margin:10px 0;}
    .chat-input-area{padding:14px 20px;border-top:1px solid var(--bdr);background:var(--card);}
    .chat-toolbar{display:flex;align-items:center;gap:8px;margin-bottom:10px;flex-wrap:wrap;}
    .toggle-pill{display:flex;align-items:center;gap:6px;padding:5px 12px;
                 border:1.5px solid var(--bdr);border-radius:20px;cursor:pointer;
                 font-size:11px;font-weight:600;color:var(--mut);transition:all .18s;user-select:none;}
    .toggle-pill:hover{border-color:var(--brand);color:var(--brand);}
    .toggle-pill.on{border-color:var(--brand);background:var(--bl);color:var(--brand);}
    .toggle-pill .pill-dot{width:7px;height:7px;border-radius:50%;background:var(--bdr);transition:background .18s;}
    .toggle-pill.on .pill-dot{background:var(--brand);}
    .lang-sel{padding:5px 10px;border:1.5px solid var(--bdr);border-radius:20px;
              font-family:inherit;font-size:11px;font-weight:600;color:var(--mut);
              outline:none;background:#fff;cursor:pointer;transition:border-color .18s;}
    .lang-sel:focus,.lang-sel:hover{border-color:var(--brand);}
    .chat-row{display:flex;gap:9px;}
    .chat-row input{flex:1;padding:10px 16px;border:1.5px solid var(--bdr);border-radius:24px;
                    font-size:13px;font-family:inherit;outline:none;color:var(--txt);background:var(--bg);
                    transition:all .18s;}
    .chat-row input:focus{border-color:var(--brand);background:#fff;box-shadow:0 0 0 3px rgba(29,190,133,.1);}
    .chat-row input::placeholder{color:#a0b0a0;}
    .send-btn{width:40px;height:40px;border-radius:50%;flex-shrink:0;background:var(--brand);
              color:#fff;border:none;cursor:pointer;transition:all .18s;
              display:flex;align-items:center;justify-content:center;
              box-shadow:0 3px 10px rgba(29,190,133,.35);}
    .send-btn:hover{background:var(--bd);transform:scale(1.08);}

    /* assist sidebar (right panel) */
    .assist-sidebar{display:flex;flex-direction:column;overflow:hidden;background:var(--card);}
    .as-hdr{padding:18px 20px;border-bottom:1px solid var(--bdr);}
    .as-hdr h3{font-size:14px;font-weight:700;margin-bottom:2px;}
    .as-hdr p {font-size:11px;color:var(--mut);}
    .as-scroll{flex:1;overflow-y:auto;padding:16px 16px;}
    .chip-grid{display:flex;flex-direction:column;gap:8px;}
    .q-chip{padding:11px 14px;background:var(--bll);border:1.5px solid var(--bdr2);
            border-radius:10px;font-size:12px;font-weight:600;color:var(--txt);
            cursor:pointer;transition:all .18s;line-height:1.4;}
    .q-chip:hover{border-color:var(--brand);background:var(--bl);color:var(--brand);transform:translateX(3px);}
    .chip-section{font-size:10px;font-weight:800;color:var(--muted2);text-transform:uppercase;
                  letter-spacing:.8px;margin:14px 0 7px;}
    .as-soil-mini{padding:14px;background:var(--card2);border:1px solid var(--bdr2);
                  border-radius:10px;margin-top:4px;}
    .asm-row{display:flex;justify-content:space-between;align-items:center;
             padding:4px 0;border-bottom:1px solid var(--bdr2);font-size:12px;}
    .asm-row:last-child{border-bottom:none;}
    .asm-key{color:var(--mut);font-weight:500;}
    .asm-val{font-weight:700;}

    /* ── MODAL ── */
    #modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:200;
                   display:none;align-items:center;justify-content:center;padding:24px;
                   backdrop-filter:blur(3px);}
    #modal-overlay.open{display:flex;}
    .modal-box{background:var(--card);border-radius:18px;width:100%;max-width:720px;
               max-height:88vh;display:flex;flex-direction:column;
               box-shadow:0 24px 60px rgba(0,0,0,.3);overflow:hidden;}
    .modal-head{display:flex;align-items:center;justify-content:space-between;
                padding:20px 24px;border-bottom:1px solid var(--bdr);flex-shrink:0;
                background:linear-gradient(135deg,var(--bll),#fff);}
    .modal-head h3{font-size:16px;font-weight:800;}
    .modal-close{width:32px;height:32px;border:none;background:var(--bg);border-radius:8px;
                 font-size:20px;color:var(--mut);cursor:pointer;
                 display:flex;align-items:center;justify-content:center;transition:background .18s;}
    .modal-close:hover{background:var(--bdr);}
    .modal-body{flex:1;overflow-y:auto;padding:24px;}

    /* ── MARKDOWN ── */
    .md p      {margin-bottom:10px;line-height:1.72;}
    .md h1,.md h2{font-size:16px;font-weight:800;margin:18px 0 9px;color:var(--txt);}
    .md h3     {font-size:14px;font-weight:700;margin:14px 0 7px;color:var(--brand);}
    .md h4     {font-size:13px;font-weight:700;margin:10px 0 5px;}
    .md ul,.md ol{margin:6px 0 10px 20px;}
    .md li     {margin-bottom:5px;line-height:1.65;}
    .md strong {font-weight:700;}
    .md hr     {border:none;border-top:1px solid var(--bdr);margin:16px 0;}
    .md code   {background:#f0f4f0;padding:2px 6px;border-radius:4px;font-size:12px;}
    .md table  {width:100%;border-collapse:collapse;margin:10px 0;}
    .md th,.md td{padding:8px 12px;border:1px solid var(--bdr);text-align:left;font-size:13px;}
    .md th     {background:var(--bll);font-weight:700;}
    .md blockquote{border-left:3px solid var(--brand);padding:8px 16px;background:var(--bll);
                   border-radius:0 8px 8px 0;margin:10px 0;color:var(--mut);font-style:italic;}

    /* ── WINDOW PILLS ── */
    .win-pill{padding:5px 12px;border:1.5px solid var(--bdr);border-radius:20px;
              font-size:11px;font-weight:700;color:var(--mut);background:#fff;
              cursor:pointer;transition:all .18s;font-family:inherit;}
    .win-pill:hover{border-color:var(--brand);color:var(--brand);}
    .win-pill.active{border-color:var(--brand);background:var(--brand);color:#fff;}

    /* ── LOADER ── */
    .spinner{display:inline-block;width:15px;height:15px;border:2px solid var(--bdr);
             border-top-color:var(--brand);border-radius:50%;animation:spin .7s linear infinite;}
    @keyframes spin{to{transform:rotate(360deg)}}
    .loader-row{display:flex;align-items:center;gap:10px;color:var(--mut);
                font-size:13px;font-weight:500;padding:8px 0;}
  </style>
</head>
<body>

<!-- ═══════════════ SIDEBAR ═══════════════ -->
<nav id="sidebar">
  <div class="sb-brand">
    <img class="sb-logo" src="{{ url_for('static', filename='MY_LOGO.png') }}" alt="Kronos AI">
    <div class="sb-name">
      <span class="sb-title">Kronos AI</span>
      <span class="sb-sub">Farm Intelligence</span>
    </div>
  </div>

  <div class="sb-section">Navigation</div>

  <div class="nav-btn active" data-page="pg-dash" id="nb-dash">
    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"/></svg>
    Dashboard
  </div>

  <div class="nav-btn" data-page="pg-weather" id="nb-weather">
    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z"/></svg>
    Weather &amp; Plan
    <span class="nav-badge" id="wx-badge">14d</span>
  </div>

  <div class="nav-btn" data-page="pg-assist" id="nb-assist">
    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/></svg>
    AI Assistance
  </div>

  <div class="nav-btn" data-page="pg-disease" id="nb-disease">
    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"/></svg>
    Plant Disease
  </div>

  <!-- WEATHER MINI WIDGET -->
  <div class="sb-weather-mini" id="sb-weather-mini">
    <div class="swm-loc" id="swm-loc">📍 Loading Kolkata…</div>
    <div class="swm-val" id="swm-val">Fetching 14-day forecast…</div>
  </div>

  <div class="sb-footer">
    <div class="dot-live"></div>
    <div class="sb-footer-txt">System Live<br>Groq · Llama 3.3 70B</div>
  </div>
</nav>

<!-- ═══════════════ MAIN ═══════════════ -->
<main id="main">

  <!-- ── DASHBOARD ── -->
  <div class="page active" id="pg-dash">
    <div class="topbar" style="flex-wrap:wrap;gap:10px;padding-bottom:12px;">
      <div class="topbar-left" style="flex:1;min-width:200px;flex-direction:column;align-items:flex-start;gap:8px;">
        <h2>Farm Overview</h2>
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;width:100%;">
          <input type="text" id="dash-crop"
            placeholder="🌾  Enter crop name (e.g. Dragon Fruit, Rice, Wheat, Tomato)"
            style="padding:7px 14px;border:1.5px solid var(--bdr);border-radius:22px;
                   font-size:12px;font-family:inherit;outline:none;color:var(--txt);
                   background:#fff;flex:1;min-width:220px;transition:border-color .18s;"
            onfocus="this.style.borderColor='var(--brand)'" onblur="this.style.borderColor='var(--bdr)'"/>
          <div style="display:flex;gap:4px;" id="win-group">
            <button class="win-pill active" data-hrs="">Latest</button>
            <button class="win-pill" data-hrs="1">1h Avg</button>
            <button class="win-pill" data-hrs="6">6h Avg</button>
            <button class="win-pill" data-hrs="24">24h Avg</button>
            <button class="win-pill" data-hrs="168">1 Week</button>
          </div>
        </div>
      </div>
      <div class="topbar-right">
        <div class="tb-chip">
          <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
          <span id="topbar-date">—</span>
        </div>
        <div class="tb-chip" id="tb-soil-chip">
          <svg fill="currentColor" viewBox="0 0 24 24"><circle cx="12" cy="12" r="6"/></svg>
          <span>Awaiting sensor</span>
        </div>
      </div>
    </div>


    <div class="scroll-area">
      <!-- Status banner -->
      <div id="sensor-status" class="status-bar s-na">
        <svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0"/></svg>
        Connecting to sensor…
      </div>

      <!-- Sensor grid -->
      <div>
        <div class="sec-hdr">
          <span class="card-lbl">Soil Sensor · Field A</span>
          <span style="font-size:11px;color:var(--mut)" id="dash-soil-type"></span>
        </div>
        <div class="sensor-grid">

          <!-- MOISTURE GAUGE -->
          <div class="card gauge-card">
            <div class="card-lbl">Soil Moisture</div>
            <svg viewBox="0 0 210 130" class="gauge-svg">
              <defs>
                <linearGradient id="mg" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%"   stop-color="#1dbe85"/>
                  <stop offset="100%" stop-color="#059b6a"/>
                </linearGradient>
              </defs>
              <path d="M18 112 A 91 91 0 0 1 192 112" fill="none" stroke="#e0ebe0" stroke-width="14" stroke-linecap="round"/>
              <path id="m-fill" d="M18 112 A 91 91 0 0 1 192 112" fill="none" stroke="url(#mg)"
                    stroke-width="14" stroke-linecap="round"
                    stroke-dasharray="286" stroke-dashoffset="286" style="transition:stroke-dashoffset 1.2s ease"/>
              <line id="m-needle" x1="105" y1="112" x2="105" y2="30"
                    stroke="#182818" stroke-width="2.5" stroke-linecap="round"
                    transform="rotate(-90,105,112)" style="transition:transform 1.2s ease"/>
              <circle cx="105" cy="112" r="7" fill="#182818"/>
              <text id="m-val" x="105" y="96" text-anchor="middle" font-size="28" font-weight="800"
                    fill="#182818" font-family="Inter,sans-serif">—%</text>
              <text x="18"  y="126" text-anchor="middle" font-size="9" fill="#aabcaa" font-family="Inter">0</text>
              <text x="192" y="126" text-anchor="middle" font-size="9" fill="#aabcaa" font-family="Inter">100</text>
            </svg>
          </div>

          <!-- NPK -->
          <div class="card">
            <div class="card-lbl">NPK Nutrients</div>
            <div class="npk-row">
              <div class="npk-top">
                <div class="npk-left"><div class="npk-dot" style="background:#1dbe85"></div><span class="npk-name">Nitrogen</span><span class="npk-band band-unk" id="band-n">—</span></div>
                <div class="npk-right"><span class="npk-val" id="npk-n">—</span><span class="npk-unit"> mg/kg</span></div>
              </div>
              <div class="bar-track"><div class="bar-fill bn" id="bar-n"></div></div>
            </div>
            <div class="npk-row">
              <div class="npk-top">
                <div class="npk-left"><div class="npk-dot" style="background:#f59e0b"></div><span class="npk-name">Phosphorus</span><span class="npk-band band-unk" id="band-p">—</span></div>
                <div class="npk-right"><span class="npk-val" id="npk-p">—</span><span class="npk-unit"> mg/kg</span></div>
              </div>
              <div class="bar-track"><div class="bar-fill bp" id="bar-p"></div></div>
            </div>
            <div class="npk-row">
              <div class="npk-top">
                <div class="npk-left"><div class="npk-dot" style="background:#6366f1"></div><span class="npk-name">Potassium</span><span class="npk-band band-unk" id="band-k">—</span></div>
                <div class="npk-right"><span class="npk-val" id="npk-k">—</span><span class="npk-unit"> mg/kg</span></div>
              </div>
              <div class="bar-track"><div class="bar-fill bk" id="bar-k"></div></div>
            </div>
          </div>

          <!-- pH GAUGE -->
          <div class="card gauge-card">
            <div class="card-lbl">Soil pH</div>
            <svg viewBox="0 0 210 130" class="gauge-svg">
              <defs>
                <linearGradient id="phg" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%"   stop-color="#ef4444"/>
                  <stop offset="32%"  stop-color="#f59e0b"/>
                  <stop offset="62%"  stop-color="#84cc16"/>
                  <stop offset="100%" stop-color="#1dbe85"/>
                </linearGradient>
              </defs>
              <path d="M18 112 A 91 91 0 0 1 192 112" fill="none" stroke="#e0ebe0" stroke-width="14" stroke-linecap="round"/>
              <path d="M18 112 A 91 91 0 0 1 192 112" fill="none" stroke="url(#phg)" stroke-width="14" stroke-linecap="round" opacity=".22"/>
              <path id="ph-fill" d="M18 112 A 91 91 0 0 1 192 112" fill="none" stroke="url(#phg)"
                    stroke-width="14" stroke-linecap="round"
                    stroke-dasharray="286" stroke-dashoffset="286" style="transition:stroke-dashoffset 1.2s ease"/>
              <line id="ph-needle" x1="105" y1="112" x2="105" y2="30"
                    stroke="#182818" stroke-width="2.5" stroke-linecap="round"
                    transform="rotate(-90,105,112)" style="transition:transform 1.2s ease"/>
              <circle cx="105" cy="112" r="7" fill="#182818"/>
              <text id="ph-val" x="105" y="96" text-anchor="middle" font-size="28" font-weight="800"
                    fill="#182818" font-family="Inter,sans-serif">—</text>
              <text x="18"  y="126" text-anchor="middle" font-size="9" fill="#ef4444" font-family="Inter">Acid</text>
              <text x="192" y="126" text-anchor="middle" font-size="9" fill="#1dbe85" font-family="Inter">Alk.</text>
            </svg>
          </div>

          <!-- TEMP + EC -->
          <div class="card temp-card">
            <div class="card-lbl" style="align-self:flex-start">Temperature</div>
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="1.5">
              <path stroke-linecap="round" stroke-linejoin="round" d="M9 9a3 3 0 116 0v4.586l1.707 1.707A1 1 0 0116 17H8a1 1 0 01-.707-1.707L9 13.586V9z"/>
              <path stroke-linecap="round" d="M9 7h6"/>
            </svg>
            <div style="display:flex;align-items:baseline;gap:3px;">
              <span class="temp-num" id="temp-val">—</span><span class="temp-unit">°C</span>
            </div>
            <span class="temp-label">Soil Temp</span>
            <div style="margin-top:8px;font-size:11px;color:var(--mut);">
              EC: <strong id="ec-val">—</strong> µS/cm
            </div>
          </div>
        </div>
      </div>

      <!-- WEATHER STRIP -->
      <div>
        <div class="sec-hdr">
          <span class="card-lbl">14-Day Forecast · <span id="dash-wx-loc">Kolkata</span></span>
          <span style="font-size:11px;color:var(--mut)" id="dash-wx-rain"></span>
        </div>
        <div class="weather-strip" id="dash-weather">
          <div class="loader-row"><div class="spinner"></div> Fetching forecast…</div>
        </div>
      </div>

      <!-- Inline analysis -->
      <div class="card md" id="analysis-panel" style="display:none;"></div>

      <!-- Action buttons -->
      <div class="action-row">
        <button class="btn-outline" id="analyze-btn">
          <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/></svg>
          Soil Analysis
        </button>
        <button class="btn-solid" id="report-btn">
          <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
          6-Month Season Plan
        </button>
      </div>
    </div>
  </div>

  <!-- ── WEATHER & PLAN ── -->
  <div class="page" id="pg-weather">
    <div class="topbar">
      <h2>Weather &amp; Irrigation</h2>
      <div class="topbar-right">
        <span id="wx-loc-badge" class="tb-chip">📍 Kolkata</span>
      </div>
    </div>
    <div class="scroll-area">
      <div class="card">
        <div class="card-lbl" style="margin-bottom:16px">Farm Configuration</div>
        <div class="form-grid">
          <div>
            <label class="f-lbl">City / Region</label>
            <input class="f-inp" id="wp-loc" type="text" value="Kolkata, West Bengal" placeholder="e.g. Kolkata">
          </div>
          <div>
            <label class="f-lbl">Your Crop</label>
            <input class="f-inp" id="wp-crop" type="text" placeholder="e.g. Rice, Dragon Fruit, Tomato">
          </div>
        </div>
        <div class="action-row">
          <button class="btn-outline btn-sm" id="wp-fc-btn">📡 Refresh 14-Day Forecast</button>
          <button class="btn-solid  btn-sm" id="wp-irr-btn">💧 14-Day Irrigation Plan</button>
          <button class="btn-solid  btn-sm" id="wp-seas-btn">🗓 6-Month Plan</button>
        </div>
      </div>

      <div class="card" id="fc-card" style="display:none;">
        <div class="sec-hdr">
          <span class="card-lbl">14-Day Forecast</span>
          <span style="font-size:11px;color:var(--mut)" id="fc-rain-total"></span>
        </div>
        <div class="fc-grid" id="fc-grid"></div>
        <div class="signals-block" id="fc-signals"></div>
      </div>

      <div class="card" id="irr-card" style="display:none;">
        <div class="card-lbl" style="margin-bottom:14px">14-Day Irrigation Schedule</div>
        <div class="md" id="irr-output"></div>
      </div>

      <div class="card" id="seas-card" style="display:none;">
        <div class="sec-hdr">
          <span class="card-lbl">6-Month Seasonal Irrigation Plan</span>
          <span style="font-size:10px;font-weight:600;color:var(--brand)">ECMWF SEAS5 · Groq Llama 3.3</span>
        </div>
        <div class="md" id="seas-output"></div>
      </div>
    </div>
  </div>

  <!-- ── AI ASSISTANCE ── -->
  <div class="page" id="pg-assist">
    <div class="topbar">
      <h2>AI Assistance</h2>
      <div class="topbar-right">
        <div class="tb-chip">
          <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/></svg>
          Llama 3.3 70B
        </div>
      </div>
    </div>
    <div class="assist-layout">
      <!-- Chat area -->
      <div class="assist-chat-area">
        <div class="chat-msgs" id="assist-msgs">
          <div class="bubble b-ai">
            <div class="md">
              <p>👋 Hello! I'm <strong>Kronos AI</strong>, your agricultural intelligence assistant powered by Llama 3.3 70B.</p>
              <p>I have access to your <strong>live soil sensor data</strong> and the <strong>14-day Kolkata weather forecast</strong>. Ask me anything!</p>
              <p>Try asking: <em>"What fertilizer should I apply now?"</em> or <em>"Plan my irrigation for next week."</em></p>
            </div>
          </div>
        </div>
        <div class="chat-input-area">
          <div class="chat-toolbar">
            <div class="toggle-pill on" id="wx-toggle" title="Include 14-day weather in AI responses">
              <div class="pill-dot"></div>
              🌤 14-Day Weather
            </div>
            <div class="toggle-pill" id="live-toggle" title="Force fresh sensor data read">
              <div class="pill-dot"></div>
              📡 Live Sensor
            </div>
            <select class="lang-sel" id="lang-sel">
              <option value="en-US">🇬🇧 English</option>
              <option value="hi-IN">🇮🇳 Hindi</option>
              <option value="bn-IN">🇧🇩 Bengali</option>
            </select>
          </div>
          <div class="chat-row">
            <input type="text" id="assist-input" placeholder="Ask about soil, crops, weather, fertilizer…" autocomplete="off"/>
            <button class="send-btn" id="assist-send">
              <svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>
            </button>
          </div>
        </div>
      </div>

      <!-- Assist sidebar -->
      <div class="assist-sidebar">
        <div class="as-hdr">
          <h3>Quick Actions</h3>
          <p>Tap to ask instantly</p>
        </div>
        <div class="as-scroll">
          <div class="chip-section">🌱 Soil & Nutrients</div>
          <div class="chip-grid">
            <div class="q-chip" data-q="Run a complete soil analysis and tell me what to do right now.">📊 Full Soil Analysis</div>
            <div class="q-chip" data-q="What fertilizer should I apply today based on my current NPK levels?">💊 Fertilizer Advice</div>
            <div class="q-chip" data-q="My soil has high EC, what should I do?">⚗ Fix High EC / Salinity</div>
            <div class="q-chip" data-q="How do I correct my soil pH?">🧪 Adjust pH</div>
          </div>
          <div class="chip-section">🌧 Weather & Irrigation</div>
          <div class="chip-grid">
            <div class="q-chip" data-q="Based on the 14-day weather forecast, plan my irrigation schedule for the next 2 weeks.">💧 14-Day Irrigation Plan</div>
            <div class="q-chip" data-q="Are there any good sowing windows in the next 14 days based on the weather?">🌱 Best Sowing Windows</div>
            <div class="q-chip" data-q="What operations should I avoid on rainy days this week?">🌧 Rain Day Planning</div>
            <div class="q-chip" data-q="How should I handle heat stress days above 36°C in my field?">🔥 Heat Stress Risk</div>
          </div>
          <div class="chip-section">🌾 Crop Management</div>
          <div class="chip-grid">
            <div class="q-chip" data-q="What pests and diseases should I watch for this season in West Bengal?">🐛 Pest & Disease Watch</div>
            <div class="q-chip" data-q="Give me a complete seasonal crop calendar for West Bengal.">📅 Crop Calendar</div>
            <div class="q-chip" data-q="What are the best crops to grow now given the current weather?">🌿 Best Crop Choice</div>
          </div>
          <!-- Live soil mini -->
          <div class="chip-section">📡 Live Readings</div>
          <div class="as-soil-mini">
            <div class="asm-row"><span class="asm-key">Temperature</span><span class="asm-val" id="asm-temp">—°C</span></div>
            <div class="asm-row"><span class="asm-key">Moisture</span><span class="asm-val" id="asm-hum">—%</span></div>
            <div class="asm-row"><span class="asm-key">pH</span><span class="asm-val" id="asm-ph">—</span></div>
            <div class="asm-row"><span class="asm-key">EC</span><span class="asm-val" id="asm-ec">— µS/cm</span></div>
            <div class="asm-row"><span class="asm-key">N / P / K</span><span class="asm-val" id="asm-npk">— / — / —</span></div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- ── PLANT DISEASE DETECTION ── -->
  <div class="page" id="pg-disease">
    <div class="topbar">
      <h2>🌿 Plant Disease Detection</h2>
      <div class="topbar-right">
        <div class="tb-chip">🔬 Integrated Scanner</div>
      </div>
    </div>
    <div style="padding:24px;max-width:800px;margin:0 auto;">
      <div style="text-align:center;margin-bottom:24px;">
        <p style="color:var(--txt-dim);font-size:14px;line-height:1.6;">
          Upload a photo of a plant leaf to identify diseases, get treatment advice, and prevention tips.<br>
          <span style="color:var(--brand);">30+ Indian crops</span> · <span style="color:var(--brand);">150+ diseases</span> · <span style="color:var(--brand);">AI-Powered</span>
        </p>
      </div>
      <div id="disease-upload-zone" style="background:var(--card);border:2px dashed var(--bdr);border-radius:12px;padding:48px 24px;text-align:center;cursor:pointer;transition:all .3s;" onmouseover="this.style.borderColor='var(--brand)'" onmouseout="this.style.borderColor='var(--bdr)'">
        <div style="font-size:42px;margin-bottom:12px;">📷</div>
        <div style="font-size:16px;font-weight:600;margin-bottom:6px;">Drop a leaf image here</div>
        <div style="color:var(--txt-dim);font-size:13px;">or click to browse — PNG, JPG, WebP — Max 16 MB</div>
        <input type="file" id="disease-file" accept="image/*" style="position:absolute;top:0;left:0;width:100%;height:100%;opacity:0;cursor:pointer;" onchange="handleDiseaseFile(this)">
      </div>
      <div id="disease-preview" style="display:none;text-align:center;margin-top:20px;">
        <img id="disease-img" src="" style="max-width:100%;max-height:350px;border-radius:12px;border:2px solid var(--bdr);" />
        <br>
        <button onclick="analyzeDisease()" id="disease-analyze-btn" style="margin-top:14px;padding:12px 32px;background:var(--brand);color:#fff;border:none;border-radius:10px;font-size:15px;font-weight:600;cursor:pointer;display:inline-flex;align-items:center;gap:8px;">
          🔍 Analyze Plant
        </button>
      </div>
      <div id="disease-results" style="margin-top:24px;"></div>
    </div>
  </div>

</main>

<!-- ═══════════════ MODAL ═══════════════ -->
<div id="modal-overlay">
  <div class="modal-box">
    <div class="modal-head">
      <h3>🗓 6-Month Seasonal Irrigation Plan</h3>
      <button class="modal-close" id="modal-close">×</button>
    </div>
    <div class="modal-body md" id="modal-body">
      <div class="loader-row"><div class="spinner"></div> Fetching ECMWF SEAS5 forecast &amp; generating plan…</div>
    </div>
  </div>
</div>

<script>
/* ═══════ STATE ═══════ */
const DEFAULT_LAT=22.5726, DEFAULT_LON=88.3639;
let curLat=DEFAULT_LAT, curLon=DEFAULT_LON, curLoc='Kolkata';
let wxLoaded=false, liveData={};

/* ═══════ UTILS ═══════ */
function esc(s){return(s||'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));}
function wxIcon(tmax,precip,size=20){
  const c=size;
  if((precip||0)>10) return`<svg width="${c}" height="${c}" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 16.58A5 5 0 0 0 18 7h-1.26A8 8 0 1 0 4 15.25"/><line x1="8" y1="19" x2="8" y2="21"/><line x1="12" y1="19" x2="12" y2="21"/><line x1="16" y1="19" x2="16" y2="21"/></svg>`;
  if((precip||0)>1) return`<svg width="${c}" height="${c}" viewBox="0 0 24 24" fill="none" stroke="#60a5fa" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.5 19H9a7 7 0 0 1-.09-14 5 5 0 0 1 9.9 1.5 4.5 4.5 0 0 1 .69 12.5"/><line x1="12" y1="19" x2="12" y2="21"/></svg>`;
  if((tmax||0)>=36) return`<svg width="${c}" height="${c}" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/></svg>`;
  return`<svg width="${c}" height="${c}" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/></svg>`;
}

/* ═══════ DATE ═══════ */
document.getElementById('topbar-date').textContent=
  new Date().toLocaleDateString('en-IN',{weekday:'short',day:'numeric',month:'short',year:'numeric'});

/* ═══════ NAV ═══════ */
document.querySelectorAll('.nav-btn[data-page]').forEach(btn=>{
  btn.addEventListener('click',()=>{
    document.querySelectorAll('.nav-btn').forEach(b=>b.classList.remove('active'));
    document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(btn.dataset.page).classList.add('active');
  });
});

/* ═══════ GAUGES ═══════ */
const ARC=286;
function setMoisture(pct){
  pct=Math.min(100,Math.max(0,pct||0));
  document.getElementById('m-fill').style.strokeDashoffset=ARC*(1-pct/100);
  document.getElementById('m-needle').setAttribute('transform',`rotate(${(pct/100*180)-90},105,112)`);
  document.getElementById('m-val').textContent=pct.toFixed(0)+'%';
}
function setPH(ph){
  const v=parseFloat(ph)||7,pct=Math.min(100,Math.max(0,(v-4)/5*100));
  document.getElementById('ph-fill').style.strokeDashoffset=ARC*(1-pct/100);
  document.getElementById('ph-needle').setAttribute('transform',`rotate(${(pct/100*180)-90},105,112)`);
  document.getElementById('ph-val').textContent=v.toFixed(1);
}
function bandClass(b){return{low:'band-low',adequate:'band-ok',high:'band-high'}[b]||'band-unk';}
function bandLabel(b){return{low:'LOW',adequate:'OK',high:'HIGH'}[b]||'—';}
function setNPK(n,p,k,bands){
  [['n',n,250,'bar-n'],['p',p,25,'bar-p'],['k',k,125,'bar-k']].forEach(([id,val,max,bar])=>{
    const v=parseFloat(val)||0;
    document.getElementById('npk-'+id).textContent=isNaN(v)?'—':v.toFixed(0);
    setTimeout(()=>{document.getElementById(bar).style.width=Math.min(100,v/max*100)+'%';},80);
  });
  if(bands){
    ['n','p','k'].forEach(id=>{
      const b=bands[id.toUpperCase()];
      const el=document.getElementById('band-'+id);
      el.className='npk-band '+bandClass(b);
      el.textContent=bandLabel(b);
    });
  }
}

/* ═══════ DASHBOARD DATA REFRESH ═══════ */
async function refreshData(){
  try{
    const r=await fetch('/dashboard_data');
    const d=await r.json();
    if(d.status==='ok'){
      const l=d.latest;
      liveData=l;
      setMoisture(l.humidity); setPH(l.pH);
      setNPK(l.nitrogen,l.phosphorus,l.potassium,d.bands);
      document.getElementById('temp-val').textContent=l.temperature!=null?l.temperature.toFixed(1):'—';
      document.getElementById('ec-val').textContent=l.conductivity!=null?l.conductivity.toFixed(2):'—';
      document.getElementById('dash-soil-type').textContent='Soil: '+(d.soil_type||'');
      // assist sidebar mini
      document.getElementById('asm-temp').textContent=(l.temperature!=null?l.temperature.toFixed(1):'—')+'°C';
      document.getElementById('asm-hum').textContent=(l.humidity!=null?l.humidity.toFixed(0):'—')+'%';
      document.getElementById('asm-ph').textContent=l.pH!=null?l.pH.toFixed(1):'—';
      document.getElementById('asm-ec').textContent=(l.conductivity!=null?l.conductivity.toFixed(2):'—')+' µS/cm';
      document.getElementById('asm-npk').textContent=`${l.nitrogen!=null?l.nitrogen.toFixed(0):'—'} / ${l.phosphorus!=null?l.phosphorus.toFixed(0):'—'} / ${l.potassium!=null?l.potassium.toFixed(0):'—'}`;
      const ss=document.getElementById('sensor-status');
      const tc=document.getElementById('tb-soil-chip');
      if(d.sensor_ok){
        ss.className='status-bar s-ok';
        ss.innerHTML='<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/></svg> Sensor connected — data live';
        tc.style.color='#065f46'; tc.querySelector('span').textContent='Sensor OK';
      }else{
        ss.className='status-bar s-bad';
        ss.innerHTML='<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01"/></svg> Warning: Sensor appears disconnected — check connection';
        tc.querySelector('span').textContent='Sensor Disconnected';
      }
    }
  }catch(e){}
}

/* ═══════ WEATHER INIT (auto-loads from server cache) ═══════ */
async function loadWeatherFromCache(){
  try{
    const r=await fetch('/weather_status');
    const d=await r.json();
    if(d.status==='ok'&&d.weather?.daily){
      renderDashWeather(d.weather.daily, d.weather.location, d.weather.signals?.total_rain_14d);
      curLat=d.weather.lat; curLon=d.weather.lon; curLoc=d.weather.location;
      updateSidebarWeather(d.weather);
      wxLoaded=true;
    }else{
      // Server still loading, retry after 2s
      setTimeout(loadWeatherFromCache, 2000);
    }
  }catch(e){setTimeout(loadWeatherFromCache,3000);}
}

function renderDashWeather(daily,loc,totalRain){
  const c=document.getElementById('dash-weather');
  document.getElementById('dash-wx-loc').textContent=loc||'Kolkata';
  if(totalRain!=null) document.getElementById('dash-wx-rain').textContent=`Total 14d rain: ${totalRain} mm`;
  c.innerHTML='';
  (daily||[]).slice(0,14).forEach(day=>{
    const dt=new Date(day.date);
    const dn=dt.toLocaleDateString('en-US',{weekday:'short'});
    const dd=dt.getDate();
    const heat=(day.tmax||0)>=36;
    c.innerHTML+=`<div class="wd-card">
      <div class="wd-day">${dn} ${dd}</div>
      <div class="wd-icon">${wxIcon(day.tmax,day.precip_sum,22)}</div>
      <div class="wd-temp">${Math.round(day.tmax||0)}°C</div>
      <div class="wd-rain">💧${day.pop||0}%</div>
      ${heat?'<div class="wd-heat">HEAT</div>':''}
    </div>`;
  });
  wxLoaded=true;
}

function updateSidebarWeather(wx){
  document.getElementById('swm-loc').textContent='📍 '+wx.location;
  const sig=wx.signals||{};
  const days=wx.daily||[];
  const rain=sig.total_rain_14d||'?';
  const heat=(sig.windows?.heat_days||[]).length;
  const rainD=(sig.windows?.rain_days||[]).length;
  document.getElementById('swm-val').textContent=
    `🌡 ${days[0]?.tmax||'?'}°C today  🌧 ${rain}mm / 14d\n${rainD} rain days${heat?' · '+heat+' heat days':''}`;
  document.getElementById('wx-loc-badge').textContent='📍 '+wx.location;
}

/* ======= WINDOW SELECTOR (event delegation) ======= */
let selWinHrs = '';
document.getElementById('win-group').addEventListener('click', function(e){
  const btn = e.target.closest('.win-pill');
  if(!btn) return;
  document.querySelectorAll('.win-pill').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  selWinHrs = btn.dataset.hrs || '';
  refreshData();
});

/* ======= ANALYZE BUTTON ======= */
document.getElementById('analyze-btn').addEventListener('click', async function(e){
  e.preventDefault(); // prevent any weird form submission behavior
  const btn   = document.getElementById('analyze-btn');
  const panel = document.getElementById('analysis-panel');
  if(!btn || !panel) return;
  const crop = (document.getElementById('dash-crop')?.value || '').trim();
  const hrs  = selWinHrs ? parseInt(selWinHrs) : null;
  
  btn.disabled = true;
  btn.textContent = 'Analyzing…';
  
  // ensure panel is visible immediately
  panel.style.display = 'block';
  panel.style.opacity = '1';
  panel.innerHTML = '<div class="loader-row" style="padding:20px;font-weight:bold;color:var(--brand);"><div class="spinner"></div> Generating crop-specific analysis... (please wait approx 5-10 seconds for Llama 3.3 70B)...</div>';
  panel.scrollIntoView({behavior:'smooth', block:'center'});

  try{
    const r = await fetch('/analyze', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({window_hours: hrs, crop: crop})
    });
    
    const d = await r.json();
    
    if(d.status === 'success'){
      panel.innerHTML = d.message;
      if(d.context?.latest){
        const l = d.context.latest;
        setMoisture(l.humidity); setPH(l.pH);
        setNPK(l.nitrogen, l.phosphorus, l.potassium, d.context?.fert_meta?.bands);
      }
    } else {
      panel.innerHTML = '<p style="color:var(--red);padding:20px;font-weight:bold;border:2px solid var(--red);border-radius:10px;">Server Error: ' + (d.message||'Failed') + '</p>';
    }
  } catch(err){
    panel.innerHTML = '<p style="color:var(--red);padding:20px;font-weight:bold;border:2px solid var(--red);border-radius:10px;">Network/JS Error: ' + err.message + '</p>';
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/></svg> Soil Analysis';
    // ensure it scrolls to the result!
    panel.scrollIntoView({behavior:'smooth', block:'start'});
  }
});

/* ═══════ SEASONAL PLAN MODAL ═══════ */
const modal=document.getElementById('modal-overlay'), modalBody=document.getElementById('modal-body');
document.getElementById('report-btn').addEventListener('click',async()=>{
  modal.classList.add('open');
  modalBody.innerHTML='<div class="loader-row"><div class="spinner"></div> Fetching ECMWF SEAS5 6-month forecast &amp; generating plan with Llama 3.3 70B…</div>';
  const loc=document.getElementById('wp-loc')?.value||'Kolkata, West Bengal';
  const crop=document.getElementById('wp-crop')?.value||'general crop';
  try{
    const r=await fetch('/seasonal_plan',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({location:loc,crop,lat:curLat,lon:curLon})});
    const d=await r.json();
    modalBody.innerHTML=d.status==='success'?d.message:`<p style="color:var(--red)">${esc(d.message)}</p>`;
  }catch(e){modalBody.innerHTML='<p style="color:var(--red)">Failed to generate plan.</p>';}
});
document.getElementById('modal-close').addEventListener('click',()=>modal.classList.remove('open'));
modal.addEventListener('click',e=>{if(e.target===modal)modal.classList.remove('open');});

/* ═══════ WEATHER PAGE ═══════ */
document.getElementById('wp-fc-btn').addEventListener('click',async()=>{
  const btn=document.getElementById('wp-fc-btn');
  const loc=document.getElementById('wp-loc').value.trim()||'Kolkata';
  btn.disabled=true; btn.textContent='Loading…';
  const card=document.getElementById('fc-card'); const grid=document.getElementById('fc-grid');
  card.style.display='block';
  grid.innerHTML='<div class="loader-row"><div class="spinner"></div> Fetching 14-day forecast…</div>';
  try{
    const r=await fetch('/plan_weather',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({location:loc,crop:document.getElementById('wp-crop').value.trim(),lat:curLat,lon:curLon})});
    const d=await r.json();
    if(d.status==='success'&&d.weather?.daily){
      curLat=d.weather.lat; curLon=d.weather.lon; curLoc=d.weather.location;
      updateSidebarWeather(d.weather);
      grid.innerHTML='';
      const rain=d.weather.signals?.total_rain_14d;
      document.getElementById('fc-rain-total').textContent=rain!=null?`Total: ${rain} mm rainfall`:'';
      d.weather.daily.forEach(day=>{
        const dt=new Date(day.date);
        const dn=dt.toLocaleDateString('en-US',{weekday:'short',day:'numeric'});
        const heat=(day.tmax||0)>=36;
        grid.innerHTML+=`<div class="fc-card">
          <div class="fc-d">${dn}</div>
          <div>${wxIcon(day.tmax,day.precip_sum,22)}</div>
          <div class="fc-t">${Math.round(day.tmax||0)}°C</div>
          <div class="fc-r">💧${day.pop||0}%</div>
          ${day.precip_sum>0?`<div style="font-size:9px;color:#60a5fa">${day.precip_sum.toFixed(1)}mm</div>`:''}
          ${heat?'<div class="fc-heat">HEAT</div>':''}
        </div>`;
      });
      // signals chips
      const sc=document.getElementById('fc-signals'); sc.innerHTML='';
      const sig=d.weather.signals||{};const w=sig.windows||{};
      if(w.rain_days?.length)   sc.innerHTML+=`<span class="signal-chip sc-rain">🌧 ${w.rain_days.length} rain days</span>`;
      if(w.heat_days?.length)   sc.innerHTML+=`<span class="signal-chip sc-heat">🔥 ${w.heat_days.length} heat days</span>`;
      if(w.best_sowing)         sc.innerHTML+=`<span class="signal-chip sc-sow">🌱 Best sowing: ${w.best_sowing.start}→${w.best_sowing.end}</span>`;
      if(sig.notes?.length)     sig.notes.forEach(n=>sc.innerHTML+=`<span class="signal-chip sc-note">💡 ${esc(n)}</span>`);
      renderDashWeather(d.weather.daily, d.weather.location, rain);
      wxLoaded=true;
    }else{grid.innerHTML=`<p style="color:var(--red)">${esc(d.message||'Error')}</p>`;}
  }catch(e){grid.innerHTML='<p style="color:var(--red)">Forecast request failed.</p>';}
  finally{btn.disabled=false; btn.textContent='📡 Refresh 14-Day Forecast';}
});

document.getElementById('wp-irr-btn').addEventListener('click',async()=>{
  const btn=document.getElementById('wp-irr-btn');
  btn.disabled=true; btn.textContent='Generating…';
  const icard=document.getElementById('irr-card'); const iout=document.getElementById('irr-output');
  icard.style.display='block';
  iout.innerHTML='<div class="loader-row"><div class="spinner"></div> Building 14-day irrigation plan with Llama 3.3…</div>';
  icard.scrollIntoView({behavior:'smooth'});
  try{
    const r=await fetch('/irrigation_plan',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    const d=await r.json();
    iout.innerHTML=d.status==='success'?d.message:`<p style="color:var(--red)">${esc(d.message)}</p>`;
  }catch(e){iout.innerHTML='<p style="color:var(--red)">Failed to generate plan.</p>';}
  finally{btn.disabled=false; btn.textContent='💧 14-Day Irrigation Plan';}
});

document.getElementById('wp-seas-btn').addEventListener('click',async()=>{
  const btn=document.getElementById('wp-seas-btn');
  const loc=document.getElementById('wp-loc').value.trim()||'Kolkata';
  const crop=document.getElementById('wp-crop').value.trim()||'general crop';
  btn.disabled=true; btn.textContent='Generating…';
  const scard=document.getElementById('seas-card'); const sout=document.getElementById('seas-output');
  scard.style.display='block';
  sout.innerHTML='<div class="loader-row"><div class="spinner"></div> Fetching ECMWF SEAS5 &amp; generating 6-month plan…</div>';
  scard.scrollIntoView({behavior:'smooth'});
  try{
    const r=await fetch('/seasonal_plan',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({location:loc,crop,lat:curLat,lon:curLon})});
    const d=await r.json();
    sout.innerHTML=d.status==='success'?d.message:`<p style="color:var(--red)">${esc(d.message)}</p>`;
  }catch(e){sout.innerHTML='<p style="color:var(--red)">Failed.</p>';}
  finally{btn.disabled=false; btn.textContent='🗓 6-Month Plan';}
});

/* ═══════ ASSIST CHAT ═══════ */
const assistMsgs=document.getElementById('assist-msgs');
const assistInput=document.getElementById('assist-input');
const assistSend=document.getElementById('assist-send');
const wxToggle=document.getElementById('wx-toggle');
const liveToggle=document.getElementById('live-toggle');
const langSel=document.getElementById('lang-sel');

wxToggle.addEventListener('click',()=>wxToggle.classList.toggle('on'));
liveToggle.addEventListener('click',()=>liveToggle.classList.toggle('on'));

function addMsg(html,role){
  const d=document.createElement('div');
  d.className=`bubble b-${role}`;
  d.innerHTML=role==='ai'?`<div class="md">${html}</div>`:esc(html);
  assistMsgs.appendChild(d);
  assistMsgs.scrollTop=assistMsgs.scrollHeight;
  return d;
}

async function sendAssist(msgOverride){
  const msg=(msgOverride||assistInput.value).trim();
  if(!msg)return;
  assistInput.value='';
  addMsg(msg,'user');
  const loader=addMsg('<span style="display:flex;align-items:center;gap:8px"><span class="spinner"></span>Thinking…</span>','ai');
  const useWeather=wxToggle.classList.contains('on');
  const useLive=liveToggle.classList.contains('on');
  try{
    const body={message:msg,language:langSel.value,include_weather:useWeather};
    if(useLive) body.window_hours=1;
    const r=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const data=await r.json();
    loader.remove();
    addMsg(data.status==='success'?data.message:esc(data.message||'Error.'),'ai');
  }catch(e){loader.remove();addMsg('Connection error — is the server running?','ai');}
}

assistSend.addEventListener('click',()=>sendAssist());
assistInput.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();sendAssist();}});

// Quick chips
document.querySelectorAll('.q-chip').forEach(chip=>{
  chip.addEventListener('click',()=>{
    // switch to assist tab
    document.querySelectorAll('.nav-btn').forEach(b=>b.classList.remove('active'));
    document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
    document.getElementById('nb-assist').classList.add('active');
    document.getElementById('pg-assist').classList.add('active');
    sendAssist(chip.dataset.q);
  });
});

/* ═══════ PLANT DISEASE DETECTION ═══════ */
let diseaseFile = null;

const diseaseUploadZone = document.getElementById('disease-upload-zone');
if (diseaseUploadZone) {
  diseaseUploadZone.addEventListener('dragover', e=>{e.preventDefault();diseaseUploadZone.style.borderColor='var(--brand)';});
  diseaseUploadZone.addEventListener('dragleave', ()=>{diseaseUploadZone.style.borderColor='var(--bdr)';});
  diseaseUploadZone.addEventListener('drop', e=>{
    e.preventDefault();diseaseUploadZone.style.borderColor='var(--bdr)';
    if(e.dataTransfer.files.length) handleDiseaseFile({files:e.dataTransfer.files});
  });
}

function handleDiseaseFile(input) {
  const file = input.files ? input.files[0] : null;
  if(!file) return;
  diseaseFile = file;
  const reader = new FileReader();
  reader.onload = e => {
    document.getElementById('disease-img').src = e.target.result;
    document.getElementById('disease-preview').style.display = 'block';
    document.getElementById('disease-upload-zone').style.display = 'none';
    document.getElementById('disease-results').innerHTML = '';
  };
  reader.readAsDataURL(file);
}

async function analyzeDisease() {
  if(!diseaseFile) return;
  const btn = document.getElementById('disease-analyze-btn');
  btn.disabled = true; btn.innerHTML = '<span class="spinner" style="display:inline-block;width:16px;height:16px;border:2px solid rgba(255,255,255,.3);border-top-color:#fff;border-radius:50%;animation:spin .8s linear infinite;"></span> Analyzing…';

  const formData = new FormData();
  formData.append('image', diseaseFile);

  try {
    // Use the unified disease detection endpoint
    const res = await fetch('/api/disease/analyze', { method:'POST', body: formData });
    const resp = await res.json();
    // The endpoint wraps prediction in {status, prediction, image_url}
    const data = resp.prediction || resp;
    renderDiseaseResults(data);
  } catch(err) {
    document.getElementById('disease-results').innerHTML = '<div style="background:var(--card);border:1px solid var(--bdr);border-radius:10px;padding:20px;color:var(--err);">❌ Analysis failed: ' + err.message + '</div>';
  } finally {
    btn.disabled = false; btn.innerHTML = '🔍 Analyze Plant';
  }
}

async function analyzeWithGroqVision(dataUri) {
  const res = await fetch('/chat', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({
      message: `You are a plant pathology expert. Analyze this plant image and respond ONLY in JSON:\n{\n  "is_plant": true/false,\n  "crop": "crop name",\n  "disease": "disease name",\n  "confidence": "high|medium|low",\n  "severity": "mild|moderate|severe",\n  "description": "brief description",\n  "treatment": { "organic": "...", "chemical": "..." },\n  "prevention": "...",\n  "safe_to_consume": true/false\n}\n\nImage data: ${dataUri.substring(0, 50)}...`,
      include_weather: false
    })
  });
  const j = await res.json();
  try {
    const text = j.reply || j.message || '';
    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if(jsonMatch) return JSON.parse(jsonMatch[0]);
    return { is_plant:false, description: text };
  } catch(e) {
    return { is_plant:false, description: j.reply || 'Could not parse analysis.' };
  }
}

function renderDiseaseResults(data) {
  const el = document.getElementById('disease-results');
  if(!data.is_plant && data.status !== 'success') {
    el.innerHTML = `<div style="background:var(--card);border:1px solid var(--bdr);border-radius:10px;padding:20px;">
      <div style="font-size:18px;font-weight:700;margin-bottom:8px;">⚠️ Could Not Identify Plant</div>
      <p style="color:var(--txt-dim);">${data.message || data.error || 'Try uploading a clear photo of a leaf.'}</p>
    </div>`;
    return;
  }
  const isHealthy = (data.disease||'').toLowerCase().includes('healthy');
  const severityColor = isHealthy ? 'var(--green)' : (data.severity==='severe'?'var(--err)':'var(--yellow)');
  const t = data.treatment || {};
  el.innerHTML = `
    <div style="background:var(--card);border:1px solid var(--bdr);border-radius:10px;padding:20px;margin-bottom:12px;">
      <div style="display:flex;align-items:center;gap:14px;">
        <div style="font-size:32px;">${isHealthy?'✅':'⚠️'}</div>
        <div>
          <div style="font-size:18px;font-weight:700;">${isHealthy?'Plant Looks Healthy!':data.disease}</div>
          <div style="color:var(--txt-dim);font-size:13px;margin-top:2px;">Crop: <b>${data.crop||'Unknown'}</b> ${data.severity?'| Severity: '+data.severity:''}</div>
          <div style="display:flex;gap:6px;margin-top:6px;flex-wrap:wrap;">
            <span style="padding:3px 10px;border-radius:14px;font-size:11px;font-weight:600;background:${isHealthy?'rgba(16,185,129,.12)':'rgba(239,68,68,.12)'};color:${isHealthy?'var(--green)':'var(--err)'};">${isHealthy?'✓ Healthy':'⚠ Diseased'}</span>
            ${data.confidence?'<span style="padding:3px 10px;border-radius:14px;font-size:11px;font-weight:600;background:rgba(59,130,246,.12);color:#3b82f6;">'+data.confidence+'</span>':''}
            ${data.source?'<span style="padding:3px 10px;border-radius:14px;font-size:11px;font-weight:600;background:rgba(139,92,246,.12);color:#8b5cf6;">'+(data.source==='gemini_vision'?'🤖 Gemini':'🧠 CNN')+'</span>':''}
          </div>
        </div>
      </div>
    </div>
    ${data.description?'<div style="background:var(--card);border:1px solid var(--bdr);border-radius:10px;padding:16px;margin-bottom:12px;"><b style="font-size:13px;color:var(--txt-dim);">📋 Description</b><p style="margin-top:6px;font-size:14px;line-height:1.6;">'+data.description+'</p></div>':''}
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;">
      ${t.organic?'<div style="background:var(--card);border:1px solid var(--bdr);border-radius:10px;padding:14px;"><b style="font-size:12px;color:var(--green);">🌿 Organic Treatment</b><p style="margin-top:6px;font-size:13px;line-height:1.6;">'+t.organic+'</p></div>':''}
      ${t.chemical?'<div style="background:var(--card);border:1px solid var(--bdr);border-radius:10px;padding:14px;"><b style="font-size:12px;color:#3b82f6;">🧪 Chemical Treatment</b><p style="margin-top:6px;font-size:13px;line-height:1.6;">'+t.chemical+'</p></div>':''}
      ${data.prevention?'<div style="background:var(--card);border:1px solid var(--bdr);border-radius:10px;padding:14px;"><b style="font-size:12px;color:var(--yellow);">🛡 Prevention</b><p style="margin-top:6px;font-size:13px;line-height:1.6;">'+data.prevention+'</p></div>':''}
      ${data.safe_to_consume!==null&&data.safe_to_consume!==undefined?'<div style="background:var(--card);border:1px solid var(--bdr);border-radius:10px;padding:14px;"><b style="font-size:12px;color:var(--txt-dim);">🍽 Safe to Consume?</b><p style="margin-top:6px;font-size:14px;font-weight:600;color:'+(data.safe_to_consume?'var(--green)':'var(--err)')+';">'+(data.safe_to_consume?'✅ Yes — wash properly':'❌ No — do not consume')+'</p></div>':''}
    </div>
  `;
}

/* ═══════ INIT ═══════ */
setTimeout(()=>{setMoisture(0);setPH(7);},300);
loadWeatherFromCache();          // auto-init from server-side cache
refreshData();
setInterval(refreshData,30000);  // poll sensor every 30s
</script>
</body>
</html>"""

if __name__ == "__main__":
    print("🚀 Kronos AI v2.2 — http://localhost:5050")
    app.run(host="0.0.0.0", port=5050, debug=False)
