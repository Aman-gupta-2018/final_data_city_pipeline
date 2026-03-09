import os, requests, time
from sqlalchemy import create_engine, text
from datetime import datetime

OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")
SUPABASE_CONNECTION_STRING = os.environ.get("SUPABASE_CONNECTION_STRING")

LOCATIONS = {
    "Colaba": {"lat": 18.906, "lon": 72.813},
    "Worli": {"lat": 19.017, "lon": 72.816},
    "Bandra": {"lat": 19.063, "lon": 72.835},
    "Andheri": {"lat": 19.119, "lon": 72.846},
    "Malad": {"lat": 19.189, "lon": 72.846},
    "Borivali": {"lat": 19.232, "lon": 72.868},
    "Kandivali": {"lat": 19.206, "lon": 72.843},
    "Kaman Road": {"lat": 19.336, "lon": 72.919}, 
    "Vasai": {"lat": 19.391, "lon": 72.839},
    "Bhiwandi": {"lat": 19.296, "lon": 73.063}
}

def fetch_live_data(area_name, config):
    pollution_url = f"http://api.openweathermap.org/data/2.5/air_pollution?lat={config['lat']}&lon={config['lon']}&appid={OPENWEATHER_API_KEY}"
    weather_url = f"http://api.openweathermap.org/data/2.5/weather?lat={config['lat']}&lon={config['lon']}&appid={OPENWEATHER_API_KEY}&units=metric"
    try:
        p_res = requests.get(pollution_url, timeout=15).json()
        w_res = requests.get(weather_url, timeout=15).json()
        p_data = p_res["list"][0]["components"]
        w_data = w_res["main"]
        return {
            "timestamp": datetime.utcnow(), "area_name": area_name,
            "pm25": p_data.get("pm2_5"), "pm10": p_data.get("pm10"),
            "no2": p_data.get("no2"), "o3": p_data.get("o3"), "co": p_data.get("co"),
            "temperature": w_data["temp"], "humidity": w_data["humidity"]
        }
    except Exception as e:
        print(f"Error fetching {area_name}: {e}")
        return None

def store_data(data_points):
    engine = create_engine(SUPABASE_CONNECTION_STRING)
    # Filter out None results from failed API calls
    valid_points = [dp for dp in data_points if dp is not None]
    
    insert_sql = text("""
        INSERT INTO city_metrics 
            (timestamp, area_name, pm25, pm10, no2, o3, co, temperature, humidity) 
        VALUES 
            (:ts, :area, :pm25, :pm10, :no2, :o3, :co, :temp, :hum)
        ON CONFLICT (timestamp, area_name) DO NOTHING
    """)

    with engine.connect() as conn:
        for dp in valid_points:
            try:
                conn.execute(insert_sql, {
                    "ts": dp["timestamp"], "area": dp["area_name"], 
                    "pm25": dp["pm25"], "pm10": dp["pm10"], 
                    "no2": dp["no2"], "o3": dp["o3"], "co": dp["co"], 
                    "temp": dp["temperature"], "hum": dp["humidity"]
                })
            except Exception as e:
                print(f"Database error for {dp['area_name']}: {e}")
        conn.commit()

if __name__ == "__main__":
    results = [fetch_live_data(name, cfg) for name, cfg in LOCATIONS.items()]
    store_data(results)
