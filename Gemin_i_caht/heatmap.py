import os
import pathlib
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import pandas as pd
import numpy as np
from influxdb_client import InfluxDBClient
from influxdb_client.rest import ApiException
try:
    from urllib3.exceptions import HTTPError as Urllib3Error
except ImportError:
    Urllib3Error = Exception
from pykrige.ok import OrdinaryKriging
import folium
from streamlit_folium import st_folium
from matplotlib.colors import Normalize, LinearSegmentedColormap
import matplotlib as mpl
import matplotlib.pyplot as plt
import io
import base64
import calendar
import warnings
from datetime import datetime, time as dt_time, timezone
from PIL import Image, ImageFilter
import time
from influxdb_client.client.warnings import MissingPivotFunction
from streamlit.errors import StreamlitSecretNotFoundError
from shapely.geometry import MultiPoint
from matplotlib.path import Path as MplPath
from functools import lru_cache
import hashlib

# Load environment variables from .env in current or parent dirs
_env_dirs = [pathlib.Path.cwd(), pathlib.Path(__file__).parent, pathlib.Path(__file__).parent.parent]
for d in _env_dirs:
    env_file = d / ".env"
    if env_file.exists():
        if load_dotenv is not None:
            load_dotenv(dotenv_path=env_file, override=False)
        else:
            try:
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip().strip("'\"")
                        if k not in os.environ:
                            os.environ[k] = v
            except Exception:
                pass

warnings.filterwarnings("ignore", category=MissingPivotFunction)

# ─── Constants ──────────────────────────────────────────────────────────────
PARAMETERS = ("nitrogen", "phosphorus", "potassium", "pH",
              "conductivity", "humidity", "temperature")
NUMERIC_COLS = PARAMETERS + ("soil_valid", "calibration_confidence", "latitude", "longitude")
TIME_RANGES = {
    "Last 5 minutes": "5m", "Last 10 minutes": "10m", "Last 15 minutes": "15m",
    "Last 30 minutes": "30m", "Last 60 minutes": "1h", "Last 2 hours": "2h",
    "Last 4 hours": "4h", "Last 12 hours": "12h", "Last 24 hours": "24h",
    "Last 2 days": "2d", "Last 3 days": "3d", "Last 5 days": "5d",
    "Last 7 days": "7d", "Last 30 days": "30d", "Last 90 days": "90d",
}
STALE_THRESHOLD_SEC = 20
HEALTH_CHECK_TTL = 15
DATA_CACHE_TTL = 60
KRIGING_CACHE_TTL = 300
PARAM_LABELS = {p: "SOIL MOISTURE" if p == "humidity" else p.upper() for p in PARAMETERS}

CMAP_SPECS = {
    "Emerald Glow": ["#030a06", "#064e3b", "#059669", "#34d399", "#a7f3d0", "#d1fae5"],
    "Solar Flare":  ["#0a2524", "#155e75", "#0f766e", "#2dd4bf", "#bef264", "#f0fdf4"],
    "Violet Pulse": ["#07030a", "#4c1d95", "#7c3aed", "#a78bfa", "#c4b5fd", "#ede9fe"],
    "Ocean Deep":   ["#03070a", "#0c4a6e", "#0284c7", "#38bdf8", "#7dd3fc", "#e0f2fe"],
    "Infrared":     ["#062b2b", "#115e59", "#0f766e", "#2dd4bf", "#99f6e4", "#ecfeff"],
    "Acid":         ["#030a07", "#065f46", "#0d9488", "#2dd4bf", "#5eead4", "#ccfbf1"],
    "Plasma Core":  ["#0a0307", "#701a75", "#c026d3", "#e879f9", "#f0abfc", "#fae8ff"],
}
AUTO_CMAPS = {
    "nitrogen": "Emerald Glow", "potassium": "Violet Pulse",
    "phosphorus": "Solar Flare", "humidity": "Ocean Deep",
    "temperature": "Infrared", "pH": "Acid", "conductivity": "Plasma Core",
}

# ─── Page Config ───────────────────────────────────────────────────────────
st.set_page_config(page_title="KRONOS", layout="wide", page_icon="◆", initial_sidebar_state="expanded")
st_autorefresh(interval=15000, limit=None, key="kronos_live_refresh")

# ─── Theme State Management ────────────────────────────────────────────────
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = True

def toggle_theme():
    st.session_state.dark_mode = not st.session_state.dark_mode

# ─── Dynamic CSS (Apple Liquid Glass) ──────────────────────────────────────
def get_css(dark_mode: bool) -> str:
    if dark_mode:
        theme_vars = """
        --bg: #000000;
        --glass-bg: rgba(255, 255, 255, 0.06);
        --glass-bg-hover: rgba(255, 255, 255, 0.1);
        --glass-border: rgba(255, 255, 255, 0.12);
        --glass-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
        --text: #ffffff;
        --text-2: rgba(255, 255, 255, 0.65);
        --text-3: rgba(255, 255, 255, 0.4);
        --input-bg: rgba(0, 0, 0, 0.3);
        --input-border: rgba(255, 255, 255, 0.08);
        --chart-grid: rgba(255, 255, 255, 0.05);
        --chart-tick: rgba(255, 255, 255, 0.4);
        --tooltip-bg: rgba(40, 40, 40, 0.8);
        --tooltip-border: rgba(255, 255, 255, 0.1);
        --orb-1: rgba(52, 199, 89, 0.4);
        --orb-2: rgba(0, 122, 255, 0.3);
        --orb-3: rgba(88, 86, 214, 0.2);
        --map-tiles: #000000;
        --accent: #34c759;
        color-scheme: dark;
        """
    else:
        theme_vars = """
        --bg: #f5f5f7;
        --glass-bg: rgba(255, 255, 255, 0.6);
        --glass-bg-hover: rgba(255, 255, 255, 0.8);
        --glass-border: rgba(0, 0, 0, 0.08);
        --glass-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
        --text: #1d1d1f;
        --text-2: #6e6e73;
        --text-3: #aeaeb2;
        --input-bg: rgba(0, 0, 0, 0.05);
        --input-border: rgba(0, 0, 0, 0.08);
        --chart-grid: rgba(0, 0, 0, 0.05);
        --chart-tick: rgba(0, 0, 0, 0.4);
        --tooltip-bg: rgba(255, 255, 255, 0.8);
        --tooltip-border: rgba(0, 0, 0, 0.1);
        --orb-1: rgba(52, 199, 89, 0.2);
        --orb-2: rgba(0, 122, 255, 0.15);
        --orb-3: rgba(88, 86, 214, 0.1);
        --map-tiles: #ffffff;
        --accent: #34c759;
        color-scheme: light;
        """

    return f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
    :root {{{theme_vars}}}
    
    #MainMenu, footer, [data-testid="stAppDeployButton"], [data-testid="stDeployButton"], .stDeployButton {{ display:none !important }}
    
    .stApp {{
        background: 
            radial-gradient(600px circle at 10% 10%, var(--orb-1), transparent 40%),
            radial-gradient(500px circle at 90% 90%, var(--orb-2), transparent 40%),
            radial-gradient(400px circle at 50% 50%, var(--orb-3), transparent 40%),
            var(--bg);
        background-attachment: fixed;
        color: var(--text);
        transition: background 0.3s ease, color 0.3s ease;
    }}
    
    [data-testid="stSidebar"] {{
        background: var(--glass-bg) !important;
        backdrop-filter: blur(40px) saturate(180%) !important;
        -webkit-backdrop-filter: blur(40px) saturate(180%) !important;
        border-right: 1px solid var(--glass-border) !important;
        transition: background 0.3s ease;
    }}
    
    .block-container {{ padding-top: 2rem; padding-bottom: 3.2rem; max-width: 1640px }}
    
    /* Liquid Glass Cards & Metrics */
    [data-testid="stMetric"] {{
        background: var(--glass-bg);
        backdrop-filter: blur(40px) saturate(180%);
        -webkit-backdrop-filter: blur(40px) saturate(180%);
        border: 1px solid var(--glass-border);
        border-radius: 24px;
        padding: 16px 20px !important;
        box-shadow: var(--glass-shadow), inset 0 1px 1px rgba(255,255,255,0.1);
        transition: transform 0.2s ease, background 0.2s ease;
    }}
    [data-testid="stMetric"]:hover {{ background: var(--glass-bg-hover); transform: translateY(-2px); }}
    [data-testid="stMetricValue"] {{ font-family: 'JetBrains Mono', monospace; font-size: 1.4rem !important; font-weight: 600; color: var(--text) !important }}
    [data-testid="stMetricLabel"] {{ font-family: 'Inter', sans-serif; font-size: 0.7rem !important; font-weight: 600; color: var(--text-3) !important; text-transform: uppercase; letter-spacing: 0.05em }}
    
    /* iOS Form Controls */
    .stSelectbox > div > div, .stMultiSelect > div > div {{
        background: var(--input-bg) !important;
        border: 1px solid var(--input-border) !important;
        border-radius: 14px !important;
        color: var(--text) !important;
        font-family: 'Inter', sans-serif !important;
        backdrop-filter: blur(20px);
        box-shadow: none !important;
    }}
    .stSelectbox > div > div:hover {{ border-color: var(--accent) !important }}
    
    [data-baseweb="menu"] {{
        background: var(--tooltip-bg) !important;
        backdrop-filter: blur(40px) saturate(180%);
        -webkit-backdrop-filter: blur(40px) saturate(180%);
        border: 1px solid var(--tooltip-border) !important;
        border-radius: 14px !important;
        box-shadow: var(--glass-shadow) !important;
    }}
    [data-baseweb="menu"] li {{ color: var(--text) !important }}
    [data-baseweb="menu"] li:hover {{ background: var(--input-bg) !important }}
    
    [data-baseweb="slider"] > div > div {{ background: var(--input-bg) !important }}
    [data-baseweb="slider"] > div > div > div {{ background: var(--accent) !important }}
    [data-baseweb="slider"] div[role="slider"] {{
        background: #fff !important; border: 2px solid var(--accent) !important;
        box-shadow: 0 0 0 3px rgba(52, 199, 89, 0.16), 0 2px 8px rgba(0,0,0,0.2) !important;
    }}
    
    /* iOS Toggle Switch */
    [data-testid="stToggleButton"] {{
        background: var(--glass-bg) !important;
        border: 1px solid var(--glass-border) !important;
        border-radius: 14px !important;
        backdrop-filter: blur(20px);
    }}
    [data-testid="stToggleButton"]:hover {{ background: var(--glass-bg-hover) !important }}
    
    /* Custom UI Elements */
    .glass-card {{
        background: var(--glass-bg);
        backdrop-filter: blur(40px) saturate(180%);
        -webkit-backdrop-filter: blur(40px) saturate(180%);
        border: 1px solid var(--glass-border);
        border-radius: 24px;
        padding: 24px;
        box-shadow: var(--glass-shadow), inset 0 1px 1px rgba(255,255,255,0.1);
        margin-bottom: 16px;
    }}
    
    .brand {{ display: flex; align-items: center; gap: 16px; margin-bottom: 4px }}
    .brand h1 {{
        margin: 0; font-family: 'Inter', sans-serif; font-size: 2rem; font-weight: 700;
        letter-spacing: -0.02em; line-height: 1; color: var(--text);
    }}
    
    .accent-line {{ position: relative; width: 100%; height: 2px; margin: 12px 0 16px; background: var(--glass-border); overflow: hidden }}
    .accent-line::before {{ content: ''; position: absolute; left: 0; top: 50%; width: 7px; height: 7px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 12px var(--accent); transform: translateY(-50%) }}
    .accent-line::after {{ content: ''; position: absolute; top: -3px; left: -18%; width: 18%; height: 8px; border-radius: 50%; background: linear-gradient(90deg, transparent, var(--accent), transparent); filter: blur(2px); animation: sweep 3s ease-in-out infinite }}
    @keyframes sweep {{ 0% {{ left: -18%; opacity: 0 }} 10% {{ opacity: 1 }} 90% {{ opacity: 1 }} 100% {{ left: 100%; opacity: 0 }} }}
    
    .status-pill {{
        display: inline-flex; align-items: center; gap: 8px; padding: 6px 14px;
        background: rgba(52, 199, 89, 0.15); border: 1px solid rgba(52, 199, 89, 0.3);
        border-radius: 14px; color: var(--accent); font-family: 'Inter', sans-serif;
        font-size: 0.75rem; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase;
        backdrop-filter: blur(20px) saturate(150%); -webkit-backdrop-filter: blur(20px) saturate(150%);
    }}
    .status-dot {{ width: 8px; height: 8px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 0 3px rgba(52, 199, 89, 0.2), 0 0 10px var(--accent); animation: pulse 2s ease-in-out infinite }}
    .status-offline {{ background: rgba(255, 159, 10, 0.15); border-color: rgba(255, 159, 10, 0.3); color: #ff9f0a }}
    .status-offline .status-dot {{ background: #ff9f0a; box-shadow: 0 0 0 3px rgba(255, 159, 10, 0.2), 0 0 10px #ff9f0a; animation: none }}
    @keyframes pulse {{ 0%, 100% {{ opacity: 1 }} 50% {{ opacity: 0.4 }} }}
    
    .latest-reading {{ display: inline-block; margin-bottom: 16px; padding: 6px 12px; background: var(--input-bg); border: 1px solid var(--input-border); border-radius: 8px; color: var(--text-2); font-family: 'JetBrains Mono', monospace; font-size: 0.75rem }}
    
    .liquid-glass-alert {{ position: relative; overflow: hidden; margin: 12px 0; padding: 16px 20px 16px 24px; background: var(--glass-bg); backdrop-filter: blur(40px) saturate(180%); -webkit-backdrop-filter: blur(40px) saturate(180%); border: 1px solid var(--glass-border); border-radius: 16px; box-shadow: var(--glass-shadow); color: var(--text); font-family: 'Inter', sans-serif; font-size: 0.9rem; line-height: 1.5 }}
    .liquid-glass-alert::before {{ content: ''; position: absolute; inset: 0 auto 0 0; width: 4px; background: var(--accent); box-shadow: 0 0 12px var(--accent) }}
    .liquid-glass-alert strong {{ color: var(--accent); font-weight: 700 }}
    
    .cb-container {{ margin-top: 12px; padding: 16px; background: var(--glass-bg); backdrop-filter: blur(40px) saturate(180%); -webkit-backdrop-filter: blur(40px) saturate(180%); border: 1px solid var(--glass-border); border-radius: 16px; box-shadow: var(--glass-shadow) }}
    .cb-label {{ font-family: 'Inter', sans-serif; font-size: 0.7rem; font-weight: 600; color: var(--text-3); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px }}
    .cb-strip {{ height: 10px; border-radius: 5px; box-shadow: inset 0 1px 1px rgba(255,255,255,0.1), 0 2px 4px rgba(0,0,0,0.1) }}
    .cb-ticks {{ display: flex; justify-content: space-between; margin-top: 6px; font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; font-weight: 600; color: var(--text-2) }}
    
    .stButton > button, .stDownloadButton > button {{
        background: var(--glass-bg) !important; border: 1px solid var(--glass-border) !important;
        border-radius: 14px !important; color: var(--text) !important;
        font-family: 'Inter', sans-serif !important; font-weight: 500 !important;
        backdrop-filter: blur(20px) saturate(150%); -webkit-backdrop-filter: blur(20px) saturate(150%);
        transition: all 0.2s ease;
    }}
    .stButton > button:hover, .stDownloadButton > button:hover {{
        background: var(--accent) !important; color: #ffffff !important; border-color: var(--accent) !important;
    }}
    
    .stInfo, .stSuccess, .stWarning, .stError {{
        background: var(--glass-bg) !important; backdrop-filter: blur(40px) saturate(180%);
        -webkit-backdrop-filter: blur(40px) saturate(180%);
        border: 1px solid var(--glass-border) !important; border-radius: 16px !important;
        color: var(--text) !important;
    }}
    .stInfo p, .stSuccess p, .stWarning p, .stError p {{ color: var(--text) !important }}
    
    .nogps-param-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 12px; margin-top: 12px }}
    .nogps-param-card {{ background: var(--input-bg); border: 1px solid var(--input-border); border-radius: 16px; padding: 16px; transition: transform 0.2s, border-color 0.2s }}
    .nogps-param-card:hover {{ transform: translateY(-2px); border-color: var(--accent) }}
    .nogps-param-label {{ font-family: 'Inter', sans-serif; font-size: 0.65rem; font-weight: 600; color: var(--text-3); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px }}
    .nogps-param-value {{ font-family: 'JetBrains Mono', monospace; font-size: 1.25rem; font-weight: 600; color: var(--text) }}
    
    /* Folium Map Styling */
    .element-container .folium-map {{
        border-radius: 24px; overflow: hidden;
        border: 1px solid var(--glass-border);
        box-shadow: var(--glass-shadow);
    }}
    
    ::-webkit-scrollbar {{ width: 6px; height: 6px }}
    ::-webkit-scrollbar-track {{ background: transparent }}
    ::-webkit-scrollbar-thumb {{ background: var(--input-border); border-radius: 3px }}
    ::-webkit-scrollbar-thumb:hover {{ background: var(--text-3) }}
    </style>
    """

st.markdown(get_css(st.session_state.dark_mode), unsafe_allow_html=True)

# ─── Utility Functions ─────────────────────────────────────────────────────
def make_hash_key(*args) -> str:
    return hashlib.md5(str(args).encode()).hexdigest()

@lru_cache(maxsize=8)
def get_colormap(name: str) -> LinearSegmentedColormap:
    if name in CMAP_SPECS:
        return LinearSegmentedColormap.from_list(name, CMAP_SPECS[name], N=256)
    try:
        return plt.get_cmap(name)
    except (ValueError, KeyError):
        return plt.get_cmap("viridis")

def resolve_cmap(choice: str, metric: str) -> LinearSegmentedColormap:
    key = choice if choice != "Auto" else AUTO_CMAPS.get(metric, "Emerald Glow")
    return get_colormap(key)

def edge_fade(ny: int, nx: int, frac: float = 0.32) -> np.ndarray:
    if ny < 2 or nx < 2:
        return np.ones((ny, nx), dtype=np.float32)
    cy, cx = ny / 2.0, nx / 2.0
    y, x = np.ogrid[:ny, :nx]
    d = np.sqrt(((x - cx) / cx) ** 2 + ((y - cy) / cy) ** 2)
    t = np.clip((d - (1.0 - frac)) / frac, 0.0, 1.0)
    return (1.0 - t * t * (3.0 - 2.0 * t)).astype(np.float32)

def build_param_cards(vals: dict) -> str:
    cards = []
    for param, val in vals.items():
        label = PARAM_LABELS.get(param, param.upper())
        v_str = f"{val:.2f}" if val != 0 else "—"
        v_cls = "nogps-param-value" if val != 0 else "nogps-param-value nogps-param-na"
        cards.append(f'<div class="nogps-param-card"><div class="nogps-param-label">{label}</div><div class="{v_cls}">{v_str}</div></div>')
    return "".join(cards)

def cmap_gradient_css(cmap, n: int = 14) -> str:
    hexes = [mpl.colors.rgb2hex(cmap(i / (n - 1))) for i in range(n)]
    return f"linear-gradient(90deg, {', '.join(hexes)})"

def retry_query(query_fn, retries: int = 3, base_delay: float = 1.0):
    for attempt in range(retries):
        try:
            return query_fn()
        except (Urllib3Error, TimeoutError, ConnectionError):
            if attempt < retries - 1:
                time.sleep(base_delay * (2 ** attempt))
            raise

# ─── Credentials ───────────────────────────────────────────────────────────
def _get_credential(key: str) -> str | None:
    try:
        if "default" in st.secrets and key in st.secrets["default"]:
            return str(st.secrets["default"][key])
        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.getenv(key)

INFLUX_URL = _get_credential("INFLUXDB_URL")
INFLUX_TOKEN = _get_credential("INFLUXDB_TOKEN")
INFLUX_ORG = _get_credential("INFLUXDB_ORG")
INFLUX_BUCKET = _get_credential("INFLUXDB_BUCKET")

if not all([INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET]):
    st.error("## Missing InfluxDB Credentials")
    st.markdown("Please configure your credentials in `.streamlit/secrets.toml` or in the root `.env` file:")
    st.code('[default]\nINFLUXDB_URL    = "https://us-east-1-1.aws.cloud2.influxdata.com"\nINFLUXDB_TOKEN  = "<YOUR_TOKEN>"\nINFLUXDB_ORG    = "Kronos"\nINFLUXDB_BUCKET = "Soil Monitoring"', language="toml")
    st.stop()

# ─── InfluxDB Client ───────────────────────────────────────────────────────
@st.cache_resource
def get_client() -> InfluxDBClient:
    return InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, timeout=60000)

def _normalize_df(result) -> pd.DataFrame:
    if isinstance(result, list):
        return pd.concat(result, ignore_index=True) if result else pd.DataFrame()
    return result

# ─── Health Check ──────────────────────────────────────────────────────────
@st.cache_data(ttl=HEALTH_CHECK_TTL)
def check_device_health() -> tuple:
    client = get_client()
    api = client.query_api()
    query = f'''from(bucket: "{INFLUX_BUCKET}")
    |> range(start: -2m)
    |> filter(fn: (r) => r["_measurement"] == "soil_data")
    |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
    |> sort(columns: ["_time"], desc: true)
    |> limit(n: 1)'''
    
    result = retry_query(lambda: api.query_data_frame(query))
    df = _normalize_df(result)
    
    if df.empty:
        return False, False, None, {}, []
    
    ts = pd.to_datetime(df["_time"].iloc[0], utc=True)
    age = (pd.Timestamp.now(tz="UTC") - ts).total_seconds()
    
    params_avail = [c for c in PARAMETERS if c in df.columns]
    vals = pd.to_numeric(df[params_avail].iloc[0], errors="coerce").fillna(0).to_dict() if params_avail else {}
    
    is_live = 0 <= age <= STALE_THRESHOLD_SEC
    has_gps = bool(
        {"latitude", "longitude"}.issubset(df.columns)
        and pd.notna(df["latitude"].iloc[0])
        and pd.notna(df["longitude"].iloc[0])
    )
    
    return is_live, has_gps, ts, vals, params_avail

try:
    device_live, has_gps, health_ts, health_vals, health_params = check_device_health()
except (ApiException, Urllib3Error, TimeoutError, ConnectionError):
    device_live, has_gps, health_ts, health_vals, health_params = False, False, None, {}, []

health_age = (pd.Timestamp.now(tz="UTC") - health_ts).total_seconds() / 60 if health_ts else float("inf")

# ─── Time Range Selector ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown("#### Time Range")
    range_label = st.selectbox("Compare readings from", list(TIME_RANGES) + ["Custom range"], index=7, key="time_range_selection")
    
    if range_label == "Custom range":
        now = datetime.now().astimezone()
        years, months = list(range(2020, now.year + 2)), list(range(1, 13))
        fmt_month = lambda v: calendar.month_name[v]
        
        with st.columns(2)[0]: start_yr = st.selectbox("Start year", years, index=len(years) - 2)
        with st.columns(2)[1]: start_mo = st.selectbox("Start month", months, index=now.month - 1, format_func=fmt_month)
        start_dt = st.date_input("Start date", datetime(start_yr, start_mo, 1).date(), key=f"sd_{start_yr}_{start_mo}")
        start_tm = st.time_input("Start time", dt_time(0, 0))
        
        with st.columns(2)[0]: end_yr = st.selectbox("End year", years, index=len(years) - 2)
        with st.columns(2)[1]: end_mo = st.selectbox("End month", months, index=now.month - 1, format_func=fmt_month)
        end_dt = st.date_input("End date", datetime(end_yr, end_mo, calendar.monthrange(end_yr, end_mo)[1]).date(), key=f"ed_{end_yr}_{end_mo}")
        end_tm = st.time_input("End time", now.time().replace(microsecond=0))
        
        range_start = datetime.combine(start_dt, start_tm, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        range_stop = datetime.combine(end_dt, end_tm, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        
        if range_stop <= range_start:
            st.error("End time must be after start time.")
            st.stop()
    else:
        range_start = f"-{TIME_RANGES[range_label]}"
        range_stop = None
    
    st.markdown(f'<div class="cb-container" style="margin-top: 16px;"><div class="cb-label">Active Range</div><div style="color: var(--text); font-weight: 600;">{range_label}</div></div>', unsafe_allow_html=True)
    if st.button("Refresh now", key="manual_refresh", use_container_width=True):
        st.rerun()

# ─── Header ────────────────────────────────────────────────────────────────
status_text = "LIVE" if (device_live and has_gps) else ("LIVE · NO GPS" if device_live else "OFFLINE")
status_cls = "status-pill" if (device_live and has_gps) else ("status-pill status-gps" if device_live else "status-pill status-offline")
latest_reading_text = f"{health_ts.strftime('%Y-%m-%d %H:%M:%S UTC')} · {health_age:.1f} minutes ago" if health_ts else "No recent reading"

st.markdown(f'''
<div class="glass-card">
    <div class="brand">
        <h1>KRONOS</h1>
        <div class="{status_cls}"><div class="status-dot"></div>{status_text}</div>
    </div>
    <div class="accent-line"></div>
    <div class="latest-reading">Latest reading: {latest_reading_text}</div>
</div>
''', unsafe_allow_html=True)

# Theme Toggle Switch positioned top right
_, col_toggle = st.columns([8, 2])
with col_toggle:
    st.toggle("Dark Mode", value=st.session_state.dark_mode, key="theme_switch", on_change=toggle_theme)

# ─── Data Loading ──────────────────────────────────────────────────────────
@st.cache_data(ttl=DATA_CACHE_TTL)
def load_data(range_start: str, range_stop: str | None) -> pd.DataFrame:
    client = get_client()
    api = client.query_api()
    range_clause = f'range(start: time(v: "{range_start}"), stop: time(v: "{range_stop}"))' if range_stop else f"range(start: {range_start})"
    query = f'''from(bucket: "{INFLUX_BUCKET}")|> {range_clause}|> filter(fn: (r) => r["_measurement"] == "soil_data")|> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")'''
    
    result = retry_query(lambda: api.query_data_frame(query))
    df = _normalize_df(result)
    
    if df.empty:
        return df
    
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    
    if "soil_valid" in df.columns:
        df = df[df["soil_valid"].isna() | (df["soil_valid"] == 1)]
    
    return df

try:
    df = load_data(range_start, range_stop)
except ApiException as e:
    st.error(f"InfluxDB error ({getattr(e, 'status', 'unknown')}): {e}")
    st.stop()
except (Urllib3Error, TimeoutError, ConnectionError):
    st.error("Could not reach InfluxDB. Check your connection.")
    st.stop()

# ─── Branch 1: No Data ─────────────────────────────────────────────────────
if df.empty:
    if device_live:
        st.markdown(f'<div class="liquid-glass-alert"><strong>Live device</strong> actively transmitting (last reading {health_age:.1f} min ago), but no data falls within <strong>{range_label}</strong>. Try a wider time range.</div>', unsafe_allow_html=True)
    else:
        st.warning(f"No readings in the last {STALE_THRESHOLD_SEC}s and no data in selected range. Device appears **offline**.")
    
    if device_live and not has_gps and health_vals:
        st.markdown(f'<div class="glass-card"><h3 style="color: var(--text); font-family: Inter, sans-serif; font-size: 1.1rem; margin-bottom: 8px;">Last Known Reading</h3><div class="nogps-param-grid">{build_param_cards(health_vals)}</div></div>', unsafe_allow_html=True)
        cols = st.columns(min(len(health_vals), 4))
        for i, (p, v) in enumerate(health_vals.items()):
            with cols[i % len(cols)]:
                st.metric(f"Latest · {PARAM_LABELS[p]}", f"{v:.2f}" if v != 0 else "—")
    st.stop()

# ─── Branch 2: No GPS ──────────────────────────────────────────────────────
available_params = [c for c in PARAMETERS if c in df.columns]
gps_df = df.dropna(subset=["latitude", "longitude"]).copy() if {"latitude", "longitude"}.issubset(df.columns) else pd.DataFrame()

if gps_df.empty:
    latest = df.sort_values("_time").iloc[-1] if "_time" in df.columns else df.iloc[-1]
    msg = ("Sensor readings received, but no **GPS coordinates** in **{r}**. Check GPS module." if device_live 
           else f"Data exists in {range_label} ({len(df)} readings) but device appears **offline** and no GPS found.")
    (st.info if device_live else st.warning)(msg.format(r=range_label))
    
    if "_time" in df.columns:
        st.caption(f"{range_label}: {pd.to_datetime(df['_time']).min():%Y-%m-%d %H:%M} to {pd.to_datetime(df['_time']).max():%Y-%m-%d %H:%M} · {len(df)} readings")
    
    if available_params:
        vals = {p: pd.to_numeric(latest.get(p), errors="coerce") for p in available_params}
        vals = {p: v for p, v in vals.items() if pd.notna(v)}
        st.markdown(f'<div class="glass-card"><h3 style="color: var(--text); font-family: Inter, sans-serif; font-size: 1.1rem; margin-bottom: 8px;">Latest Sensor Readings</h3><div class="nogps-param-grid">{build_param_cards(vals)}</div></div>', unsafe_allow_html=True)
    st.stop()

# ─── Branch 3: Full Map Experience ─────────────────────────────────────────
latest_gps = gps_df.sort_values("_time").iloc[-1] if "_time" in gps_df.columns else gps_df.iloc[-1]
latest_loc = [float(latest_gps["latitude"]), float(latest_gps["longitude"])]

# ─── Sidebar Controls ─────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("#### Parameters")
    st.markdown('<div style="height: 8px;"></div>', unsafe_allow_html=True)
    
    target = st.selectbox("Soil Parameter", list(PARAMETERS), format_func=lambda x: PARAM_LABELS[x], key="target_metric")
    metric_label = PARAM_LABELS[target]
    vario_model = st.selectbox("Variogram Model", ["spherical", "gaussian", "exponential", "linear"])
    
    st.markdown("#### Variogram")
    nlags = st.slider("Variogram lags", 4, 20, 6, step=1)
    
    st.markdown("#### Appearance")
    grid_res = st.slider("Resolution", 50, 300, 120, step=10)
    opacity = st.slider("Opacity", 0.3, 1.0, 0.6, step=0.05)
    show_pts = st.checkbox("Show sample points", value=False)
    
    cmap_names = ["Auto"] + list(CMAP_SPECS.keys()) + ["viridis", "YlGnBu"]
    cmap_choice = st.selectbox("Color Palette", cmap_names, index=0)
    
    gamma = st.slider("Contrast (γ)", 0.3, 2.5, 1.0, step=0.1)
    blur_r = st.slider("Softness", 0, 6, 2, step=1)

# ─── Prepare Data ──────────────────────────────────────────────────────────
selected_vals = pd.to_numeric(gps_df[target], errors="coerce").dropna()
if selected_vals.empty:
    st.error(f"No {metric_label.lower()} readings in selected range.")
    st.stop()

reading_count = len(selected_vals)
sub_df = gps_df[["latitude", "longitude", target, "calibration_confidence"]].dropna()
sub_df = sub_df.groupby(["latitude", "longitude"], as_index=False).agg({target: "mean", "calibration_confidence": "mean"})

if len(sub_df) < 4:
    st.error("Need at least 4 unique GPS-tagged points for Kriging.")
    st.stop()

lons, lats, values = sub_df["longitude"].values, sub_df["latitude"].values, sub_df[target].values

if len(np.unique(np.column_stack([lons, lats]), axis=0)) < 3:
    st.error("Need ≥ 3 unique GPS locations.")
    st.stop()
if np.ptp(values) < 1e-10:
    st.error(f"All {target} values are identical.")
    st.stop()

# ─── Kriging Computation ───────────────────────────────────────────────────
@st.cache_data(ttl=KRIGING_CACHE_TTL, show_spinner=False)
def compute_kriging(data_hash: str, model: str, n: int, nl: int) -> tuple:
    pad = 0.22
    dx, dy = max((lons.max() - lons.min()) * pad, 5e-4), max((lats.max() - lats.min()) * pad, 5e-4)
    glon = np.linspace(lons.min() - dx, lons.max() + dx, n)
    glat = np.linspace(lats.min() - dy, lats.max() + dy, n)
    
    try:
        ok = OrdinaryKriging(lons, lats, values, variogram_model=model, verbose=False, enable_plotting=False, pseudo_inv=True, coordinates_type="geographic", nlags=nl)
    except TypeError:
        ok = OrdinaryKriging(lons, lats, values, variogram_model=model, verbose=False, enable_plotting=False, pseudo_inv=True, nlags=nl)
    
    try:
        return ok.execute("grid", glon, glat, exact_values=False) + (glon, glat)
    except TypeError:
        return ok.execute("grid", glon, glat) + (glon, glat)

with st.spinner("Computing kriging surface…"):
    try:
        data_key = make_hash_key(lons.tobytes(), lats.tobytes(), values.tobytes())
        kriged_z, sserm, grid_lon, grid_lat = compute_kriging(data_key, vario_model, grid_res, nlags)
    except (np.linalg.LinAlgError, ValueError) as e:
        st.error(f"Kriging failed: {e}")
        st.stop()
    except RuntimeError as e:
        st.error(str(e))
        st.stop()

# ─── Render Heatmap ────────────────────────────────────────────────────────
vmin_q, vmax_q = float(selected_vals.quantile(0.02)), float(selected_vals.quantile(0.98))
if vmax_q <= vmin_q:
    vmin_q, vmax_q = float(selected_vals.min()), float(selected_vals.max())
    if vmax_q <= vmin_q:
        vmin_q, vmax_q = vmin_q - 0.5, vmax_q + 0.5

kriged_z = np.clip(np.asarray(kriged_z, dtype=np.float32), vmin_q, vmax_q)
norm = Normalize(vmin=vmin_q, vmax=vmax_q)
normed = np.clip(norm(kriged_z), 0.0, 1.0).astype(np.float32)

if gamma != 1.0:
    np.power(normed, float(gamma), out=normed, where=~np.isnan(normed))
    normed = np.nan_to_num(normed, nan=0.0)

colormap = resolve_cmap(cmap_choice, target)
rgba = colormap(normed)

mask = np.ones_like(normed, dtype=bool)
try:
    pts = list(zip(lons.tolist(), lats.tolist()))
    buffer_deg = min(max(np.ptp(lons), np.ptp(lats)) * 0.06, 0.005)
    poly = MultiPoint(pts).convex_hull.buffer(buffer_deg)
    gx, gy = np.meshgrid(grid_lon, grid_lat)
    poly_path = MplPath(np.array(poly.exterior.coords))
    mask = poly_path.contains_points(np.vstack([gx.ravel(), gy.ravel()]).T).reshape(gx.shape)
except Exception:
    pass

rgba[:, :, 3] *= edge_fade(rgba.shape[0], rgba.shape[1], 0.14)
rgba[:, :, 3] *= mask.astype(np.float32)
rgba = np.flipud(rgba)
rgba_u8 = (np.clip(rgba, 0, 1) * 255).astype(np.uint8)

img = Image.fromarray(rgba_u8, mode="RGBA")
if blur_r > 0:
    img = img.filter(ImageFilter.GaussianBlur(radius=blur_r))

buf = io.BytesIO()
img.save(buf, format="PNG", optimize=True)
img_uri = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"
del buf, rgba, rgba_u8, img

# ─── Build Map (Dynamic Theme Tiles) ───────────────────────────────────────
map_tiles = "CartoDB dark_matter" if st.session_state.dark_mode else "CartoDB positron"
m = folium.Map(location=latest_loc, zoom_start=min(18 if max(np.ptp(lons), np.ptp(lats)) < 0.001 else 16, 20), 
               tiles=map_tiles, zoom_control=True, scrollWheelZoom=True, dragging=True)

tooltip_bg = "rgba(40, 40, 40, 0.8)" if st.session_state.dark_mode else "rgba(255, 255, 255, 0.8)"
tooltip_color = "#ffffff" if st.session_state.dark_mode else "#1d1d1f"
tooltip_border = "rgba(255, 255, 255, 0.1)" if st.session_state.dark_mode else "rgba(0, 0, 0, 0.1)"

m.get_root().header.add_child(folium.Element(f"""<style>
.leaflet-control-zoom a {{
    background: {tooltip_bg} !important; color: {tooltip_color} !important;
    border: 1px solid {tooltip_border} !important; backdrop-filter: blur(20px);
    transition: all 0.15s;
}}
.leaflet-control-zoom a:hover {{
    background: rgba(52, 199, 89, 0.18) !important; color: #34c759 !important;
    border-color: rgba(52, 199, 89, 0.2) !important;
}}
.leaflet-control-attribution {{ background: {tooltip_bg} !important; color: var(--text-3) !important; backdrop-filter: blur(4px) }}
.leaflet-container {{ background: var(--map-tiles) !important; }}
.leaflet-tooltip.glass-tooltip {{
    padding: 0 !important; overflow: hidden; color: {tooltip_color} !important;
    background: {tooltip_bg} !important; border: 1px solid {tooltip_border} !important;
    border-radius: 14px !important; box-shadow: 0 8px 24px rgba(0,0,0,0.2) !important;
    backdrop-filter: blur(40px) saturate(180%); -webkit-backdrop-filter: blur(40px) saturate(180%);
}}
.glass-tooltip-content {{ min-width: 104px; padding: 10px 14px }}
.glass-tooltip-label {{ display: block; margin-bottom: 3px; color: var(--accent); font: 600 9px/1.1 Inter,sans-serif; letter-spacing: 0.1em; text-transform: uppercase }}
.glass-tooltip-value {{ font: 600 18px/1.1 'JetBrains Mono',monospace; color: {tooltip_color} }}
</style>"""))

folium.raster_layers.ImageOverlay(
    image=img_uri,
    bounds=[[float(grid_lat.min()), float(grid_lon.min())], [float(grid_lat.max()), float(grid_lon.max())]],
    opacity=opacity, zindex=1
).add_to(m)

# ─── Next Best Sample Point ────────────────────────────────────────────────
try:
    flat_var = sserm.ravel()
    flat_mask = mask.ravel()
    valid = np.where(flat_mask & ~np.isnan(flat_var))[0]
    if valid.size > 0:
        topk = min(500, valid.size)
        top = valid[np.argsort(-flat_var[valid])[:topk]]
        clat, clon = gy.ravel()[top], gx.ravel()[top]
        dists = np.sqrt((clat[:, None] - lats[None, :]) ** 2 + (clon[:, None] - lons[None, :]) ** 2)
        scores = flat_var[top] * dists.min(axis=1)
        best = np.argmax(scores)
        best_pt = (float(clat[best]), float(clon[best]))
        folium.Marker(location=best_pt, icon=folium.Icon(color="lightblue", icon="star"), tooltip="Recommended next sample").add_to(m)
        
        with st.sidebar:
            st.markdown("#### Next Best Sample")
            st.markdown(f"""
            <div style="background: var(--input-bg); border: 1px solid var(--input-border); border-radius: 12px; padding: 12px; font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; color: var(--text);">
                <div style="color: var(--text-3); font-size: 0.7rem; margin-bottom: 4px;">LATITUDE</div>
                <div>{best_pt[0]:.6f}</div>
                <div style="color: var(--text-3); font-size: 0.7rem; margin-top: 8px; margin-bottom: 4px;">LONGITUDE</div>
                <div>{best_pt[1]:.6f}</div>
            </div>
            """, unsafe_allow_html=True)
except Exception:
    pass

# ─── Sample Markers ────────────────────────────────────────────────────────
marker_style = ({"radius": 5, "color": "#ffffffaa", "weight": 1.2, "fill": True, "fill_color": "#34c759", "fill_opacity": 0.85} if show_pts
                else {"radius": 12, "color": "transparent", "weight": 0, "opacity": 0, "fill": True, "fill_color": "transparent", "fill_opacity": 0})

for _, r in sub_df.iterrows():
    folium.CircleMarker(
        location=[r["latitude"], r["longitude"]],
        tooltip=folium.Tooltip(f'<div class="glass-tooltip-content"><span class="glass-tooltip-label">{metric_label}</span><span class="glass-tooltip-value">{r[target]:.2f}</span></div>', sticky=True, className="glass-tooltip"),
        **marker_style
    ).add_to(m)

# ─── Render Layout ─────────────────────────────────────────────────────────
st_folium(m, width=None, height=600)
map_html = m.get_root().render().encode("utf-8")

c_bar, c_sp, c1, c2, c3, c4 = st.columns([2.6, 0.4, 1, 1, 1, 1])

with c_bar:
    st.markdown(f'''<div class="cb-container"><div class="cb-label">{metric_label} · {vario_model} · {grid_res}×{grid_res} · γ {gamma} · {range_label}</div><div class="cb-strip" style="background:{cmap_gradient_css(colormap)};"></div><div class="cb-ticks"><span>{vmin_q:.2f}</span><span>{(vmin_q + vmax_q) / 2:.2f}</span><span>{vmax_q:.2f}</span></div></div>''', unsafe_allow_html=True)
    dl, _ = st.columns([1, 4])
    with dl:
        st.download_button("⬇  Download Map", data=map_html, file_name=f"kronos_{'soil_moisture' if target == 'humidity' else target}.html", mime="text/html")

with c1: st.metric(f"Samples", f"{reading_count}")
with c2: st.metric(f"Max", f"{selected_vals.max():.2f}")
with c3: st.metric(f"Min", f"{selected_vals.min():.2f}")
with c4: st.metric(f"Mean", f"{selected_vals.mean():.2f}")