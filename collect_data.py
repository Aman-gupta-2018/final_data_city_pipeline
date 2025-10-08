# collect_data.py (Final Corrected Version - Data will no longer be deleted)
import os
import requests
from sqlalchemy import create_engine, text
from datetime import datetime
import time

OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")
SUPABASE_CONNECTION_STRING = os.environ.get("SUPABASE_CONNECTION_STRING")

LOCATIONS = {
    "Colaba": {"lat": 18.906, "lon": 72.813},
    "Worli": {"lat": 19.017, "lon": 72.816},
    "Bandra": {"lat": 19.063, "lon": 72.835},
    "Andheri": {"lat": 19.119, "lon": 72.846},
    "Malad": {"lat": 19.189, "lon": 72.846},
}

def fetch_live_data(area_name, config):
    print(f"\nFetching data for {area_name} from OpenWeatherMap...")
    pollution_url = f"http://api.openweathermap.org/data/2.5/air_pollution?lat={config['lat']}&lon={config['lon']}&appid={OPENWEATHER_API_KEY}"
    weather_url = f"http://api.openweathermap.org/data/2.5/weather?lat={config['lat']}&lon={config['lon']}&appid={OPENWEATHER_API_KEY}&units=metric"
    
    try:
        pollution_res = requests.get(pollution_url, timeout=15).json()
        weather_res = requests.get(weather_url, timeout=15).json()

        if "list" not in pollution_res or weather_res.get("cod") != 200:
            print(f"!!! API Error for {area_name}, skipping.")
            return None
        print(f"<-- API calls for {area_name} SUCCEEDED.")
        
        p_data = pollution_res["list"][0]["components"]
        w_data = weather_res["main"]

        return {
            "timestamp": datetime.utcnow(), "area_name": area_name,
            "aqi": None, # We will calculate this later
            "pm25": p_data.get("pm2_5"), "pm10": p_data.get("pm10"),
            "no2": p_data.get("no2"), "o3": p_data.get("o3"),
            "co": p_data.get("co"), "temperature": w_data["temp"],
            "humidity": w_data["humidity"],
        }
    except Exception as e:
        print(f"!!! A critical error occurred for {area_name}: {e}")
        return None

def store_data(data_points):
    print("\nConnecting to Supabase to store data...")
    engine = create_engine(SUPABASE_CONNECTION_STRING)
    with engine.connect() as connection:
        # This line CREATES the table but will NOT delete it if it already exists
        connection.execute(text("""
        CREATE TABLE IF NOT EXISTS city_metrics (
            id SERIAL PRIMARY KEY, timestamp TIMESTAMPTZ, area_name VARCHAR(255),
            aqi FLOAT, pm25 FLOAT, pm10 FLOAT, no2 FLOAT, o3 FLOAT, co FLOAT,
            temperature FLOAT, humidity FLOAT
        );
        """))
        insert_count = 0
        for dp in data_points:
            if dp and dp.get("pm25") is not None:
                connection.execute(
                    text("""INSERT INTO city_metrics (timestamp, area_name, aqi, pm25, pm10, no2, o3, co, temperature, humidity) VALUES (:ts, :area, :aqi, :pm25, :pm10, :no2, :o3, :co, :temp, :hum)"""),
                    { "ts": dp["timestamp"], "area": dp["area_name"], "aqi": dp["aqi"], "pm25": dp["pm25"], "pm10": dp["pm10"], "no2": dp["no2"], "o3": dp["o3"], "co": dp["co"], "temp": dp["temperature"], "hum": dp["humidity"] }
                )
                insert_count += 1
        connection.commit()
    print(f"✅ Successfully stored {insert_count} data points.")

if __name__ == "__main__":
    all_data = []
    for area, config in LOCATIONS.items():
        all_data.append(fetch_live_data(area, config))
        time.sleep(2)
    
    if any(dp is not None for dp in all_data):
        store_data(all_data)
    else:
        print("No valid data was fetched.")
    print("Data collection process finished.")