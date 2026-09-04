import os, pathlib, time, hashlib, warnings, calendar, io, base64
from datetime import datetime, timezone, time as dt_time
from functools import lru_cache
from flask import Flask, render_template, request, redirect, url_for, send_file
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
from matplotlib.colors import Normalize, LinearSegmentedColormap
import matplotlib as mpl
import matplotlib.pyplot as plt
from PIL import Image, ImageFilter
from shapely.geometry import MultiPoint
from matplotlib.path import Path as MplPath
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None
try:
    from influxdb_client.client.warnings import MissingPivotFunction
    warnings.filterwarnings("ignore", category=MissingPivotFunction)
except ImportError:
    pass

# Load .env
for d in [pathlib.Path.cwd(), pathlib.Path(__file__).parent, pathlib.Path(__file__).parent.parent]:
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

# ─── Flask App ─────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.urandom(24)

# ─── Constants (IDENTICAL to original) ─────────────────────────────────────
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
VARIOGRAM_MODELS = ["spherical", "gaussian", "exponential", "linear"]

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

# ─── TTL Cache (replaces @st.cache_data) ───────────────────────────────────
class _TTLCache:
    def __init__(self):
        self._store = {}
    def get(self, key, ttl):
        if key in self._store:
            val, ts = self._store[key]
            if time.time() - ts < ttl:
                return val
            del self._store[key]
        return None
    def set(self, key, val):
        self._store[key] = (val, time.time())

_health_cache = _TTLCache()
_data_cache = _TTLCache()
_kriging_cache = _TTLCache()
_map_cache = {}  # map_key -> map_html string

# ─── Utility Functions (IDENTICAL) ─────────────────────────────────────────
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
        v_str = f"{val:.2f}" if val != 0 else "\u2014"
        cards.append(f'<div class="pk"><div class="pl">{label}</div><div class="pv">{v_str}</div></div>')
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

# ─── Credentials (env only, no st.secrets) ─────────────────────────────────
INFLUX_URL = os.getenv("INFLUXDB_URL")
INFLUX_TOKEN = os.getenv("INFLUXDB_TOKEN")
INFLUX_ORG = os.getenv("INFLUXDB_ORG")
INFLUX_BUCKET = os.getenv("INFLUXDB_BUCKET")

# ─── InfluxDB Client (singleton) ───────────────────────────────────────────
_client = None
def get_client():
    global _client
    if _client is None:
        _client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, timeout=60000)
    return _client

def _normalize_df(result) -> pd.DataFrame:
    if isinstance(result, list):
        return pd.concat(result, ignore_index=True) if result else pd.DataFrame()
    return result

# ─── Health Check ──────────────────────────────────────────────────────────
def check_device_health():
    cached = _health_cache.get("health", HEALTH_CHECK_TTL)
    if cached is not None:
        return cached
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
        result = (False, False, None, {}, [])
        _health_cache.set("health", result)
        return result
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
    return (is_live, has_gps, ts, vals, params_avail)

def load_data(range_start, range_stop):
    cache_key = make_hash_key(range_start, range_stop)
    cached = _data_cache.get(cache_key, DATA_CACHE_TTL)
    if cached is not None:
        return cached
    client = get_client()
    api = client.query_api()
    if range_stop:
        range_clause = f'range(start: time(v: "{range_start}"), stop: time(v: "{range_stop}"))'
    else:
        range_clause = f"range(start: {range_start})"
    query = f'from(bucket: "{INFLUX_BUCKET}")|> {range_clause}|> filter(fn: (r) => r["_measurement"] == "soil_data")|> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")'
    result = retry_query(lambda: api.query_data_frame(query))
    df = _normalize_df(result)
    if df.empty:
        _data_cache.set(cache_key, df)
        return df
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    # ESP32 doesn't always transmit these fields — guarantee they exist so
    # downstream selections never KeyError on windows where they're absent.
    for col in ("soil_valid", "calibration_confidence", "latitude", "longitude"):
        if col not in df.columns:
            df[col] = np.nan
    if "soil_valid" in df.columns:
        df = df[df["soil_valid"].isna() | (df["soil_valid"] == 1)]
    _data_cache.set(cache_key, df)
    return df

def compute_kriging_with_data(lons, lats, values, model, n, nl):
    cache_key = make_hash_key(lons.tobytes(), lats.tobytes(), values.tobytes(), model, n, nl)
    cached = _kriging_cache.get(cache_key, KRIGING_CACHE_TTL)
    if cached is not None:
        return cached
    pad = 0.22
    dx = max((lons.max() - lons.min()) * pad, 5e-4)
    dy = max((lats.max() - lats.min()) * pad, 5e-4)
    glon = np.linspace(lons.min() - dx, lons.max() + dx, n)
    glat = np.linspace(lats.min() - dy, lats.max() + dy, n)
    try:
        ok = OrdinaryKriging(lons, lats, values, variogram_model=model, verbose=False,
                             enable_plotting=False, pseudo_inv=True, coordinates_type="geographic", nlags=nl)
    except TypeError:
        ok = OrdinaryKriging(lons, lats, values, variogram_model=model, verbose=False,
                             enable_plotting=False, pseudo_inv=True, nlags=nl)
    try:
        res = ok.execute("grid", glon, glat, exact_values=False) + (glon, glat)
    except TypeError:
        res = ok.execute("grid", glon, glat) + (glon, glat)
    _kriging_cache.set(cache_key, res)
    return res

@app.route("/")
def index():
    return redirect(url_for("heatmap_page"))

@app.route("/heatmap")
def heatmap_page():
    if not all([INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET]):
        return render_template("heatmap.html", error_msg="Missing InfluxDB credentials in .env",
                               branch="no_data", theme="dark", time_range_labels=list(TIME_RANGES),
                               selected_range="N/A", is_custom=False, show_controls=False,
                               param_labels=PARAM_LABELS, parameters=PARAMETERS, status_cls="of",
                               status_text="ERROR", latest_reading="Configure .env",
                               warning_msg="", info_msg="", last_known_vals={}, sensor_vals={},
                               start_date="", start_time="", end_date="", end_time="")

    theme = request.args.get("theme", "dark")
    range_label = request.args.get("time_range", "Last 4 hours")
    target = request.args.get("target", "nitrogen")
    vario_model = request.args.get("variogram", "spherical")
    try: nlags = int(request.args.get("nlags", 6))
    except: nlags = 6
    try: grid_res = int(request.args.get("grid_res", 120))
    except: grid_res = 120
    try: opacity = float(request.args.get("opacity", 0.6))
    except: opacity = 0.6
    show_pts = request.args.get("show_pts") == "1"
    cmap_choice = request.args.get("cmap", "Auto")
    try: gamma = float(request.args.get("gamma", 1.0))
    except: gamma = 1.0
    try: blur_r = int(request.args.get("blur_r", 2))
    except: blur_r = 2

    is_custom = range_label == "Custom range"
    start_date = request.args.get("start_date", datetime.now().strftime("%Y-%m-%d"))
    start_time_v = request.args.get("start_time", "00:00")
    end_date = request.args.get("end_date", datetime.now().strftime("%Y-%m-%d"))
    end_time_v = request.args.get("end_time", datetime.now().strftime("%H:%M"))

    if is_custom:
        try:
            range_start = datetime.combine(
                datetime.strptime(start_date, "%Y-%m-%d").date(),
                dt_time.fromisoformat(start_time_v), tzinfo=timezone.utc
            ).isoformat().replace("+00:00", "Z")
            range_stop = datetime.combine(
                datetime.strptime(end_date, "%Y-%m-%d").date(),
                dt_time.fromisoformat(end_time_v), tzinfo=timezone.utc
            ).isoformat().replace("+00:00", "Z")
            if range_stop <= range_start:
                return render_template("heatmap.html", error_msg="End time must be after start time.",
                                       branch="no_data", theme=theme, time_range_labels=list(TIME_RANGES),
                                       selected_range=range_label, is_custom=True, show_controls=False,
                                       param_labels=PARAM_LABELS, parameters=PARAMETERS, status_cls="of",
                                       status_text="ERROR", latest_reading="", warning_msg="", info_msg="",
                                       last_known_vals={}, sensor_vals={}, start_date=start_date,
                                       start_time=start_time_v, end_date=end_date, end_time=end_time_v)
        except Exception:
            range_start, range_stop, is_custom = "-4h", None, False
    else:
        range_start = f"-{TIME_RANGES.get(range_label, '4h')}"
        range_stop = None

    try:
        device_live, has_gps, health_ts, health_vals, health_params = check_device_health()
    except Exception:
        device_live, has_gps, health_ts, health_vals, health_params = False, False, None, {}, []

    health_age = (pd.Timestamp.now(tz="UTC") - health_ts).total_seconds() / 60 if health_ts else float("inf")
    status_text = "LIVE" if (device_live and has_gps) else ("LIVE - NO GPS" if device_live else "OFFLINE")
    status_cls = "sp lv" if device_live else "sp of"
    latest_reading = f"{health_ts.strftime('%Y-%m-%d %H:%M:%S UTC')} - {health_age:.1f} min ago" if health_ts else "No recent reading"

    try:
        df = load_data(range_start, range_stop)
    except Exception as e:
        return render_template("heatmap.html", error_msg=f"Data load error: {e}",
                               branch="no_data", theme=theme, time_range_labels=list(TIME_RANGES),
                               selected_range=range_label, is_custom=is_custom, show_controls=False,
                               param_labels=PARAM_LABELS, parameters=PARAMETERS, status_cls=status_cls,
                               status_text=status_text, latest_reading=latest_reading,
                               warning_msg="", info_msg="", last_known_vals={}, sensor_vals={},
                               start_date=start_date, start_time=start_time_v, end_date=end_date, end_time=end_time_v)

    if df.empty:
        wmsg = f"Live device but no data in <strong>{range_label}</strong>." if device_live else "Device appears <strong>offline</strong>."
        lk = health_vals if health_vals else {}
        return render_template("heatmap.html", branch="no_data", theme=theme,
                               time_range_labels=list(TIME_RANGES), selected_range=range_label,
                               is_custom=is_custom, show_controls=False, param_labels=PARAM_LABELS,
                               parameters=PARAMETERS, status_cls=status_cls, status_text=status_text,
                               latest_reading=latest_reading, warning_msg=wmsg, error_msg="",
                               info_msg="", last_known_vals=lk, sensor_vals={},
                               start_date=start_date, start_time=start_time_v, end_date=end_date, end_time=end_time_v)

    gps_df = df.dropna(subset=["latitude", "longitude"]).copy() if {"latitude", "longitude"}.issubset(df.columns) else pd.DataFrame()
    if gps_df.empty:
        avail = [c for c in PARAMETERS if c in df.columns]
        latest = df.sort_values("_time").iloc[-1] if "_time" in df.columns else df.iloc[-1]
        svals = {p: pd.to_numeric(latest.get(p), errors="coerce") for p in avail}
        svals = {p: v for p, v in svals.items() if pd.notna(v)}
        imsg = f"Sensor readings but <strong>no GPS</strong> in {range_label}." if device_live else "Device <strong>offline</strong>, no GPS."
        return render_template("heatmap.html", branch="no_gps", theme=theme,
                               time_range_labels=list(TIME_RANGES), selected_range=range_label,
                               is_custom=is_custom, show_controls=False, param_labels=PARAM_LABELS,
                               parameters=PARAMETERS, status_cls=status_cls, status_text=status_text,
                               latest_reading=latest_reading, warning_msg="", error_msg="",
                               info_msg=imsg, last_known_vals={}, sensor_vals=svals,
                               range_caption=f"{range_label}: {len(df)} readings",
                               start_date=start_date, start_time=start_time_v, end_date=end_date, end_time=end_time_v)
    latest_gps = gps_df.sort_values("_time").iloc[-1] if "_time" in gps_df.columns else gps_df.iloc[-1]
    latest_loc = [float(latest_gps["latitude"]), float(latest_gps["longitude"])]
    selected_vals = pd.to_numeric(gps_df[target], errors="coerce").dropna()
    if selected_vals.empty:
        return render_template("heatmap.html", error_msg=f"No {PARAM_LABELS[target].lower()} readings.", branch="no_data", theme=theme, time_range_labels=list(TIME_RANGES), selected_range=range_label, is_custom=is_custom, show_controls=False, param_labels=PARAM_LABELS, parameters=PARAMETERS, status_cls=status_cls, status_text=status_text, latest_reading=latest_reading, warning_msg="", info_msg="", last_known_vals={}, sensor_vals={}, start_date=start_date, start_time=start_time_v, end_date=end_date, end_time=end_time_v)
    reading_count = len(selected_vals)
    sub_df = gps_df[["latitude", "longitude", target, "calibration_confidence"]].dropna()
    sub_df = sub_df.groupby(["latitude", "longitude"], as_index=False).agg({target: "mean", "calibration_confidence": "mean"})
    if len(sub_df) < 4:
        return render_template("heatmap.html", error_msg="Need >= 4 GPS points.", branch="no_data", theme=theme, time_range_labels=list(TIME_RANGES), selected_range=range_label, is_custom=is_custom, show_controls=False, param_labels=PARAM_LABELS, parameters=PARAMETERS, status_cls=status_cls, status_text=status_text, latest_reading=latest_reading, warning_msg="", info_msg="", last_known_vals={}, sensor_vals={}, start_date=start_date, start_time=start_time_v, end_date=end_date, end_time=end_time_v)
    lons, lats, values = sub_df["longitude"].values, sub_df["latitude"].values, sub_df[target].values
    if np.ptp(values) < 1e-10:
        return render_template("heatmap.html", error_msg=f"All {target} values identical.", branch="no_data", theme=theme, time_range_labels=list(TIME_RANGES), selected_range=range_label, is_custom=is_custom, show_controls=False, param_labels=PARAM_LABELS, parameters=PARAMETERS, status_cls=status_cls, status_text=status_text, latest_reading=latest_reading, warning_msg="", info_msg="", last_known_vals={}, sensor_vals={}, start_date=start_date, start_time=start_time_v, end_date=end_date, end_time=end_time_v)
    try:
        kriged_z, sserm, grid_lon, grid_lat = compute_kriging_with_data(lons, lats, values, vario_model, grid_res, nlags)
    except Exception as e:
        return render_template("heatmap.html", error_msg=f"Kriging failed: {e}", branch="no_data", theme=theme, time_range_labels=list(TIME_RANGES), selected_range=range_label, is_custom=is_custom, show_controls=False, param_labels=PARAM_LABELS, parameters=PARAMETERS, status_cls=status_cls, status_text=status_text, latest_reading=latest_reading, warning_msg="", info_msg="", last_known_vals={}, sensor_vals={}, start_date=start_date, start_time=start_time_v, end_date=end_date, end_time=end_time_v)
    vmin_q, vmax_q = float(selected_vals.quantile(0.02)), float(selected_vals.quantile(0.98))
    if vmax_q <= vmin_q:
        vmin_q, vmax_q = float(selected_vals.min()), float(selected_vals.max())
        if vmax_q <= vmin_q: vmin_q, vmax_q = vmin_q - 0.5, vmax_q + 0.5
    kriged_z = np.clip(np.asarray(kriged_z, dtype=np.float32), vmin_q, vmax_q)
    norm = Normalize(vmin=vmin_q, vmax=vmax_q)
    normed = np.clip(norm(kriged_z), 0.0, 1.0).astype(np.float32)
    if gamma != 1.0:
        np.power(normed, float(gamma), out=normed, where=~np.isnan(normed))
        normed = np.nan_to_num(normed, nan=0.0)
    colormap = resolve_cmap(cmap_choice, target)
    rgba = colormap(normed)
    mask_arr = np.ones_like(normed, dtype=bool)
    try:
        pts = list(zip(lons.tolist(), lats.tolist()))
        buffer_deg = min(max(np.ptp(lons), np.ptp(lats)) * 0.06, 0.005)
        poly = MultiPoint(pts).convex_hull.buffer(buffer_deg)
        gx, gy = np.meshgrid(grid_lon, grid_lat)
        from matplotlib.path import Path as MplPath
        poly_path = MplPath(np.array(poly.exterior.coords))
        mask_arr = poly_path.contains_points(np.vstack([gx.ravel(), gy.ravel()]).T).reshape(gx.shape)
    except Exception: pass
    rgba[:, :, 3] *= edge_fade(rgba.shape[0], rgba.shape[1], 0.14)
    rgba[:, :, 3] *= mask_arr.astype(np.float32)
    rgba = np.flipud(rgba)
    rgba_u8 = (np.clip(rgba, 0, 1) * 255).astype(np.uint8)
    img = Image.fromarray(rgba_u8, mode="RGBA")
    if blur_r > 0: img = img.filter(ImageFilter.GaussianBlur(radius=blur_r))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    img_uri = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode(chr(97)+chr(115)+chr(99)+chr(105)+chr(105))}"
    map_tiles = "CartoDB dark_matter" if theme == "dark" else "CartoDB positron"
    m = folium.Map(location=latest_loc, zoom_start=min(18 if max(np.ptp(lons), np.ptp(lats)) < 0.001 else 16, 20), tiles=map_tiles, zoom_control=True, scrollWheelZoom=True, dragging=True)
    folium.raster_layers.ImageOverlay(image=img_uri, bounds=[[float(grid_lat.min()), float(grid_lon.min())], [float(grid_lat.max()), float(grid_lon.max())]], opacity=opacity, zindex=1).add_to(m)
    next_sample = None
    try:
        fv = sserm.ravel(); fm = mask_arr.ravel()
        valid = np.where(fm & ~np.isnan(fv))[0]
        if valid.size > 0:
            topk = min(500, valid.size)
            top = valid[np.argsort(-fv[valid])[:topk]]
            clat, clon = gy.ravel()[top], gx.ravel()[top]
            dists = np.sqrt((clat[:, None] - lats[None, :]) ** 2 + (clon[:, None] - lons[None, :]) ** 2)
            scores = fv[top] * dists.min(axis=1)
            best = np.argmax(scores)
            bp = (float(clat[best]), float(clon[best]))
            next_sample = bp
            folium.Marker(location=bp, icon=folium.Icon(color="lightblue", icon="star"), tooltip="Next best sample").add_to(m)
    except Exception: pass
    ms = ({"radius": 5, "color": "#ffffffaa", "weight": 1.2, "fill": True, "fill_color": "#34c759", "fill_opacity": 0.85} if show_pts else {"radius": 12, "color": "transparent", "weight": 0, "opacity": 0, "fill": True, "fill_color": "transparent", "fill_opacity": 0})
    for _, r in sub_df.iterrows():
        folium.CircleMarker(location=[r["latitude"], r["longitude"]], tooltip=folium.Tooltip(f"<div><b>{PARAM_LABELS[target]}</b>: {r[target]:.2f}</div>", sticky=True), **ms).add_to(m)
    map_html = m.get_root().render()
    map_key = hashlib.md5(map_html.encode()).hexdigest()[:12]
    _map_cache[map_key] = map_html
    if len(_map_cache) > 20:                     # keep memory bounded
        _map_cache.pop(next(iter(_map_cache)), None)
    map_b64 = base64.b64encode(map_html.encode("utf-8")).decode("ascii")
    map_src = f"data:text/html;base64,{map_b64}"
    gradient_css = cmap_gradient_css(colormap)
    ml = PARAM_LABELS[target]
    cnames = ["Auto"] + list(CMAP_SPECS.keys()) + ["viridis", "YlGnBu"]
    return render_template("heatmap.html", branch="full_map", theme=theme,
                           time_range_labels=list(TIME_RANGES), selected_range=range_label,
                           is_custom=is_custom, show_controls=True, param_labels=PARAM_LABELS,
                           parameters=PARAMETERS, variogram_models=VARIOGRAM_MODELS,
                           target=target, vario_model=vario_model, nlags=nlags, grid_res=grid_res,
                           opacity=opacity, show_pts=show_pts, cmap_names=cnames,
                           cmap_choice=cmap_choice, gamma=gamma, blur_r=blur_r,
                           status_cls=status_cls, status_text=status_text, latest_reading=latest_reading,
                           error_msg="", warning_msg="", info_msg="",
                           next_sample=next_sample, map_src=map_src, map_key=map_key,
                           gradient_css=gradient_css, metric_label=ml,
                           reading_count=reading_count, max_val=float(selected_vals.max()),
                           min_val=float(selected_vals.min()), mean_val=float(selected_vals.mean()),
                           vmin_q=vmin_q, vmax_q=vmax_q,
                           start_date=start_date, start_time=start_time_v,
                           end_date=end_date, end_time=end_time_v)


@app.route("/download/map/<map_key>")
def download_map(map_key):
    map_html = _map_cache.get(map_key)
    if not map_html:
        return "Map expired, please regenerate", 404
    return send_file(io.BytesIO(map_html.encode("utf-8")), mimetype="text/html",
                     as_attachment=True, download_name="kronos_heatmap.html")


if __name__ == "__main__":
    print("Starting KRONOS Heatmap on http://localhost:5051")
    app.run(host="0.0.0.0", port=5051, debug=False)
