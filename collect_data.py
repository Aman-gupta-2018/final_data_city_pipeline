"""
collect_data.py  —  Mumbai Air Intelligence
FIXED: Uses WAQI for real ground-sensor pollution and OpenWeatherMap for weather.
"""

import os
import time
import logging
import requests
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from typing import Optional

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")
WAQI_TOKEN          = os.environ.get("WAQI_TOKEN")
SUPABASE_CONN_STR   = os.environ.get("SUPABASE_CONNECTION_STRING")

LOCATIONS = {
    "Colaba":     {"lat": 18.906, "lon": 72.813},
    "Worli":      {"lat": 19.017, "lon": 72.816},
    "Bandra":     {"lat": 19.063, "lon": 72.835},
    "Andheri":    {"lat": 19.119, "lon": 72.846},
    "Malad":      {"lat": 19.189, "lon": 72.846},
    "Borivali":   {"lat": 19.232, "lon": 72.868},
    "Kandivali":  {"lat": 19.206, "lon": 72.843},
    "Kurla":      {"lat": 19.073, "lon": 72.880},  
    "Sion":       {"lat": 19.039, "lon": 72.861},  
    "Powai":      {"lat": 19.117, "lon": 72.906},  
    "Kaman Road": {"lat": 19.336, "lon": 72.919},
    "Vasai":      {"lat": 19.391, "lon": 72.839},
    "Bhiwandi":   {"lat": 19.296, "lon": 73.063},
}

API_RETRIES   = 3
RETRY_DELAY_S = 5
RATE_LIMIT_S  = 1.5 

VALID_BOUNDS = {
    "pm25": (0, 600), "pm10": (0, 900), "no2": (0, 500), 
    "o3": (0, 500), "co": (0, 15000), "temperature": (5, 50), "humidity": (0, 100),
}

def _get_with_retry(url: str, retries: int = API_RETRIES) -> dict:
    """GET JSON with retry + backoff. Raises on final failure."""
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            log.warning("Attempt %d/%d failed for %s — %s", attempt, retries, url[:60], exc)
            if attempt < retries:
                time.sleep(RETRY_DELAY_S)
    raise RuntimeError(f"All {retries} attempts failed for {url[:60]}")

def validate(value, key: str):
    """Return value if within bounds, else None (stored as NULL)."""
    if value is None: return None
    try:
        v = float(value)
        lo, hi = VALID_BOUNDS.get(key, (None, None))
        if lo is not None and not (lo <= v <= hi): 
            log.warning("  ⚠ %s=%.2f out of bounds [%s, %s] → storing NULL", key, v, lo, hi)
            return None
        return v
    except (ValueError, TypeError):
        return None

def fetch_dual_api_data(area_name: str, config: dict) -> Optional[dict]:
    """Fetches pollution from WAQI and weather from OpenWeatherMap."""
    waqi_url = f"https://api.waqi.info/feed/geo:{config['lat']};{config['lon']}/?token={WAQI_TOKEN}"
    owm_url  = f"http://api.openweathermap.org/data/2.5/weather?lat={config['lat']}&lon={config['lon']}&appid={OPENWEATHER_API_KEY}&units=metric"

    try:
        # 1. Get Pollution Data (WAQI)
        waqi_res = _get_with_retry(waqi_url)
        time.sleep(RATE_LIMIT_S)
        
        # 2. Get Weather Data (OWM)
        owm_res = _get_with_retry(owm_url)
        time.sleep(RATE_LIMIT_S)

        w_data = waqi_res.get("data", {}).get("iaqi", {}) if waqi_res.get("status") == "ok" else {}
        weather = owm_res.get("main", {})

        record = {
            "timestamp":   datetime.now(timezone.utc),
            "area_name":   area_name,
            "pm25":        validate(w_data.get("pm25", {}).get("v"), "pm25"),
            "pm10":        validate(w_data.get("pm10", {}).get("v"), "pm10"),
            "no2":         validate(w_data.get("no2", {}).get("v"), "no2"),
            "o3":          validate(w_data.get("o3", {}).get("v"), "o3"),
            "co":          validate(w_data.get("co", {}).get("v"), "co"),
            "temperature": validate(weather.get("temp"), "temperature"),
            "humidity":    validate(weather.get("humidity"), "humidity"),
        }
        
        log.info(
            "  ✓ %-12s  PM2.5=%-6s  PM10=%-6s  Temp=%-5s  Humidity=%s",
            area_name,
            f"{record['pm25']:.1f}" if record["pm25"] is not None else "NULL",
            f"{record['pm10']:.1f}" if record["pm10"] is not None else "NULL",
            f"{record['temperature']:.1f}" if record["temperature"] is not None else "NULL",
            f"{record['humidity']:.0f}" if record["humidity"] is not None else "NULL",
        )
        return record

    except Exception as exc:
        log.error("  ✗ %-12s  FAILED — %s", area_name, exc)
        return None

def store_data(data_points: list) -> None:
    """
    Upsert records. ON CONFLICT DO NOTHING prevents duplicates if the
    GitHub Actions workflow runs slightly late and overlaps with itself.
    Requires a UNIQUE constraint on (timestamp, area_name) in Supabase.
    """
    engine = create_engine(SUPABASE_CONN_STR)
    valid  = [dp for dp in data_points if dp is not None]

    if not valid:
        log.error("No valid data points to store — check API key and connectivity.")
        return

    insert_sql = text("""
        INSERT INTO city_metrics
            (timestamp, area_name, pm25, pm10, no2, o3, co, temperature, humidity)
        VALUES
            (:ts, :area, :pm25, :pm10, :no2, :o3, :co, :temp, :hum)
        ON CONFLICT (timestamp, area_name) DO NOTHING
    """)

    with engine.connect() as conn:
        stored = 0
        for dp in valid:
            try:
                result = conn.execute(insert_sql, {
                    "ts": dp["timestamp"], "area": dp["area_name"], "pm25": dp["pm25"],
                    "pm10": dp["pm10"], "no2": dp["no2"], "o3": dp["o3"],
                    "co": dp["co"], "temp": dp["temperature"], "hum": dp["humidity"]
                })
                if result.rowcount > 0:
                    stored += 1
            except Exception as exc:
                log.error("  DB error for %s — %s", dp["area_name"], exc)
        conn.commit()

    log.info("Stored %d/%d records (%d skipped as duplicates).",
             stored, len(valid), len(valid) - stored)

if __name__ == "__main__":
    if not OPENWEATHER_API_KEY or not WAQI_TOKEN or not SUPABASE_CONN_STR:
        raise EnvironmentError("Missing API keys or Database string in environment variables.")

    log.info("Starting dual-API data collection...")
    results = []
    for name, cfg in LOCATIONS.items():
        results.append(fetch_dual_api_data(name, cfg))
        
    store_data(results)
    log.info("Collection complete.")