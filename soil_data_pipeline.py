import os, time, csv, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from influxdb_client import InfluxDBClient

# ---------- Config ----------
MEASUREMENT = "soil_data"
POLL_INTERVAL_SEC = 1   # poll every ~1s
FIELDS = ["conductivity","humidity","nitrogen","phosphorus","potassium","pH","temperature","latitude","longitude"]

CSV_DIR = Path("data/csv")
PARQUET_DIR = Path("data/parquet")
STATE_DIR = Path("data/state")
STATE_FILE = STATE_DIR / "last_ts.state"

WRITE_CSV = True
WRITE_PARQUET = True

# ---------- Timezones ----------
IST = timezone(timedelta(hours=5, minutes=30))

def iso_ist(dt: datetime) -> str:
    """Convert datetime to ISO string in IST (+05:30)."""
    return dt.astimezone(IST).isoformat()

def from_iso_ist(s: str) -> datetime:
    """Parse ISO string with +05:30 back to aware datetime in IST."""
    return datetime.fromisoformat(s).astimezone(IST)

# ---------- Setup ----------
load_dotenv()
INFLUXDB_URL   = os.getenv("INFLUXDB_URL")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN")
INFLUXDB_ORG   = os.getenv("INFLUXDB_ORG")
INFLUXDB_BUCKET= os.getenv("INFLUXDB_BUCKET")

if not all([INFLUXDB_URL, INFLUXDB_TOKEN, INFLUXDB_ORG, INFLUXDB_BUCKET]):
    print("Missing InfluxDB env vars. Check your .env.", file=sys.stderr)
    sys.exit(1)

for d in (CSV_DIR, PARQUET_DIR, STATE_DIR):
    d.mkdir(parents=True, exist_ok=True)

client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
query_api = client.query_api()

# ---------- State ----------
def read_last_ts() -> datetime | None:
    if STATE_FILE.exists():
        s = STATE_FILE.read_text().strip()
        if s:
            try:
                return from_iso_ist(s)
            except Exception:
                pass
    return None

def write_last_ts(ts: datetime):
    STATE_FILE.write_text(iso_ist(ts))

def ensure_csv_header(csv_path: Path):
    expected_header = ["time"] + FIELDS
    if not csv_path.exists():
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(expected_header)
    else:
        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                first_line = f.readline().strip().split(",")
            if first_line != expected_header:
                df = pd.read_csv(csv_path)
                for fld in FIELDS:
                    if fld not in df.columns:
                        df[fld] = None
                cols = [c for c in expected_header if c in df.columns]
                df = df[cols]
                df.to_csv(csv_path, index=False, encoding="utf-8")
        except Exception:
            pass

# ---------- Data fetch ----------
def fetch_since(since: datetime | None):
    """Return tidy rows (dicts) since 'since' (exclusive)."""
    if since is None:
        start_iso = iso_ist(datetime.now(IST) - timedelta(minutes=5))  # bootstrap 5 mins
    else:
        start_iso = iso_ist(since + timedelta(milliseconds=1))

    cols_flux = ", ".join(f'"{f}"' for f in FIELDS)
    flux = f'''
from(bucket: "{INFLUXDB_BUCKET}")
  |> range(start: time(v: "{start_iso}"))
  |> filter(fn: (r) => r._measurement == "{MEASUREMENT}")
  |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> keep(columns: ["_time", {cols_flux}])
  |> sort(columns: ["_time"])
'''
    tables = query_api.query(flux, org=INFLUXDB_ORG)

    rows = []
    for table in tables:
        for rec in table.records:
            vals = rec.values
            ts_iso = vals["_time"].astimezone(IST).isoformat()
            row = {"time": ts_iso}
            for f in FIELDS:
                row[f] = vals.get(f)
            rows.append(row)
    return rows

# ---------- Writers ----------
def append_csv_by_day(rows: list[dict]) -> int:
    written = 0
    buckets: dict[str, list[dict]] = {}
    for r in rows:
        day = r["time"][:10]
        buckets.setdefault(day, []).append(r)

    for day, batch in buckets.items():
        csv_path = CSV_DIR / f"soil_{day}.csv"
        ensure_csv_header(csv_path)
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            for r in batch:
                w.writerow([r["time"]] + [r.get(k) for k in FIELDS])
                written += 1
    return written

def write_parquet_partitioned(rows: list[dict]) -> int:
    if not rows:
        return 0
    df = pd.DataFrame(rows)
    df["day"] = df["time"].str.slice(0, 10)
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_to_dataset(
        table,
        root_path=str(PARQUET_DIR),
        partition_cols=["day"]
    )
    return len(rows)

# ---------- Main loop ----------
def main():
    last_ts = read_last_ts()
    print(f"Starting stream. Last saved ts: {last_ts if last_ts else 'None (bootstrap recent)'}")

    while True:
        started = time.time()
        try:
            rows = fetch_since(last_ts)
            if rows:
                for r in rows:
                    print("NEW DATA:", r)  # <-- real-time print in IST

                if WRITE_CSV:
                    append_csv_by_day(rows)
                if WRITE_PARQUET:
                    write_parquet_partitioned(rows)

                last_ts = from_iso_ist(rows[-1]["time"])
                write_last_ts(last_ts)
        except Exception as e:
            print(f"[ERROR] {e}", file=sys.stderr)

        elapsed = time.time() - started
        to_sleep = max(0.2, POLL_INTERVAL_SEC - elapsed)
        time.sleep(to_sleep)

if __name__ == "__main__":
    main()
