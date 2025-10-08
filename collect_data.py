# collect_data.py (with detailed logging)
import os
import requests
from sqlalchemy import create_engine, text
from datetime import datetime
import time

# These secrets will be provided securely by GitHub Actions
WAQI_TOKEN = os.environ.get("WAQI_TOKEN")
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")
SUPABASE_CONNECTION_STRING = os.environ.get("SUPABASE_CONNECTION_STRING")

# Expanded list of locations on the Western Line
LOCATIONS = {
    "Colaba": {"waqi_id": "colaba", "lat": 18.906, "lon": 72.813},
    "Worli": {"waqi_id": "worli", "lat": 19.017, "lon": 72.816},
    "Bandra": {"waqi_id": "bandra", "lat": 19.063, "lon": 72.835},
    "Andheri": {"waqi_id": "mumbai-andheri", "lat": 19.119, "lon": 72.846},
    "Malad": {"waqi_id": "malad-west", "lat": 19.189, "lon": 72.846},
    "Kandivali": {"waqi_id": "mumbai-kandivali-west", "lat": 19.206, "lon": 72.843},
    "Borivali": {"waqi_id": "mumbai-borivali-east", "lat": 19.232, "lon": 72.868},
}

def fetch_live_data(area_name, config):
    print(f"\nAttempting to fetch data for {area_name}...")
    waqi_url = f"https://api.waqi.info/feed/@{config['waqi_id']}/?token={WAQI_TOKEN}"
    weather_url = f"http://api.openweathermap.org/data/2.5/weather?lat={config['lat']}&lon={config['lon']}&appid={OPENWEATHER_API_KEY}&units=metric"
    
    try:
        print(f"--> Calling WAQI API for {area_name}...")
        waqi_res = requests.get(waqi_url, timeout=15).json()
        print(f"<-- WAQI API call for {area_name} SUCCEEDED.")

        if waqi_res.get("status") != "ok":
            print(f"!!! WAQI API Error: {waqi_res.get('data')}")
            return None

        print(f"--> Calling OpenWeatherMap API for {area_name}...")
        weather_res = requests.get(weather_url, timeout=15).json()
        print(f"<-- OpenWeatherMap API call for {area_name} SUCCEEDED.")

        if weather_res.get("cod") != 200:
            print(f"!!! OpenWeatherMap API Error: {weather_res.get('message')}")
            return None

        iaqi = waqi_res["data"]["iaqi"]
        return {
            "timestamp": datetime.utcnow(),
            "area_name": area_name,
            "aqi": waqi_res["data"]["aqi"],
            "pm25": iaqi.get("pm25", {}).get("v"),
            "pm10": iaqi.get("pm10", {}).get("v"),
            "no2": iaqi.get("no2", {}).get("v"),
            "o3": iaqi.get("o3", {}).get("v"),
            "co": iaqi.get("co", {}).get("v"),
            "temperature": weather_res["main"]["temp"],
            "humidity": weather_res["main"]["humidity"],
        }
    except Exception as e:
        print(f"!!! A critical error occurred while fetching data for {area_name}: {e}")
        return None

def store_data(data_points):
    print("\nConnecting to Supabase database...")
    engine = create_engine(SUPABASE_CONNECTION_STRING)
    with engine.connect() as connection:
        print("--> Creating table if it doesn't exist...")
        connection.execute(text("""
        CREATE TABLE IF NOT EXISTS city_metrics (
            id SERIAL PRIMARY KEY, timestamp TIMESTAMPTZ, area_name VARCHAR(255),
            aqi FLOAT, pm25 FLOAT, pm10 FLOAT, no2 FLOAT, o3 FLOAT, co FLOAT,
            temperature FLOAT, humidity FLOAT
        );
        """))
        print("<-- Table check complete.")
        
        insert_count = 0
        for dp in data_points:
            if dp:
                connection.execute(
                    text("""
                    INSERT INTO city_metrics (timestamp, area_name, aqi, pm25, pm10, no2, o3, co, temperature, humidity)
                    VALUES (:ts, :area, :aqi, :pm25, :pm10, :no2, :o3, :co, :temp, :hum)
                    """),
                    { "ts": dp["timestamp"], "area": dp["area_name"], "aqi": dp["aqi"], "pm25": dp["pm25"], "pm10": dp["pm10"], "no2": dp["no2"], "o3": dp["o3"], "co": dp["co"], "temp": dp["temperature"], "hum": dp["humidity"] }
                )
                insert_count += 1
        connection.commit()
    print(f"Successfully stored {insert_count} data points.")

if __name__ == "__main__":
    print("Starting data collection process...")
    if not all([WAQI_TOKEN, OPENWEATHER_API_KEY, SUPABASE_CONNECTION_STRING]):
        print("!!! FATAL ERROR: One or more environment variables (secrets) are missing.")
    else:
        all_data = []
        for area, config in LOCATIONS.items():
            data_point = fetch_live_data(area, config)
            all_data.append(data_point)
            time.sleep(2)
        
        if any(dp is not None for dp in all_data):
            store_data(all_data)
        else:
            print("No data was fetched from any API. Nothing to store.")
    print("Data collection process finished.")