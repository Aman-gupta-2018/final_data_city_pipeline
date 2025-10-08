# app.py (Final version with self-calculated AQI)
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import plotly.express as px
import plotly.graph_objects as go

# --- Page Configuration ---
st.set_page_config(page_title="Mumbai Air Quality Dashboard", layout="wide")

# --- Custom CSS for Professional UI ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    body { font-family: 'Inter', sans-serif; }
    .main { background-color: #0D1117; }
    .st-emotion-cache-z5fcl4 { border-radius: 12px; }
    .stSelectbox { border-radius: 8px; }
    h1, h2, h3 { color: #C9D1D9 !important; }
    .custom-card { background: #161B22; border: 1px solid #30363D; border-radius: 12px; padding: 25px; margin-bottom: 1.5rem; }
    .aqi-display { text-align: left; }
    .aqi-value { font-size: 5rem; font-weight: 700; line-height: 1; }
    .aqi-level { font-size: 1.5rem; font-weight: 600; margin-top: -10px; }
    .aqi-pm25 { font-size: 1rem; color: #8B949E; }
    .gauge-bar { display: flex; width: 100%; height: 10px; border-radius: 5px; overflow: hidden; margin-top: 15px; }
    .gauge-segment { flex-grow: 1; }
    .metric-box { text-align: center; background-color: #0D1117; border-radius: 8px; padding: 1rem; border: 1px solid #30363D; }
    .metric-value { font-size: 1.5rem; font-weight: 600; }
    .metric-label { font-size: 0.8rem; color: #8B949E; text-transform: uppercase; }
</style>
""", unsafe_allow_html=True)

# --- Helper Functions ---
def pm25_to_us_aqi(pm25):
    if pd.isna(pm25): return None
    if pm25 < 0: return 0
    if pm25 > 1000: return 500 # Cap at max
    
    if 0.0 <= pm25 <= 12.0: return ((50 - 0) / (12.0 - 0.0)) * (pm25 - 0.0) + 0
    elif 12.1 <= pm25 <= 35.4: return ((100 - 51) / (35.4 - 12.1)) * (pm25 - 12.1) + 51
    elif 35.5 <= pm25 <= 55.4: return ((150 - 101) / (55.4 - 35.5)) * (pm25 - 35.5) + 101
    elif 55.5 <= pm25 <= 150.4: return ((200 - 151) / (150.4 - 55.5)) * (pm25 - 55.5) + 151
    elif 150.5 <= pm25 <= 250.4: return ((300 - 201) / (250.4 - 150.5)) * (pm25 - 150.5) + 201
    elif 250.5 <= pm25 <= 350.4: return ((400 - 301) / (350.4 - 250.5)) * (pm25 - 250.5) + 301
    else: return ((500 - 401) / (500.4 - 350.5)) * (pm25 - 350.5) + 401

def get_aqi_status(aqi_val):
    if pd.isna(aqi_val): return "#8B949E", "Unknown"
    if aqi_val <= 50: return "#22c55e", "Good"
    if aqi_val <= 100: return "#facc15", "Moderate"
    if aqi_val <= 150: return "#f97316", "Unhealthy for Sensitive"
    if aqi_val <= 200: return "#ef4444", "Unhealthy"
    if aqi_val <= 300: return "#a855f7", "Very Unhealthy"
    return "#7f1d1d", "Hazardous"

@st.cache_resource
def get_db_engine():
    return create_engine(st.secrets["SUPABASE_CONNECTION_STRING"])

@st.cache_data(ttl=600)
def fetch_data():
    df = pd.read_sql("SELECT * FROM city_metrics ORDER BY timestamp DESC LIMIT 2000", get_db_engine(), parse_dates=['timestamp'])
    df['timestamp'] = df['timestamp'].dt.tz_convert('Asia/Kolkata')
    # Calculate the US AQI from the PM2.5 value
    df['aqi'] = df['pm25'].apply(pm25_to_us_aqi)
    return df

# --- Main Dashboard UI ---
df = fetch_data()
st.title("🏙️ Mumbai Air Quality Dashboard")

if df.empty:
    st.warning("Data is currently being collected. Please ensure your data pipeline has run.")
else:
    locations = sorted(df['area_name'].unique())
    selected_location = st.selectbox("Select a Location", locations)

    df_location = df[df['area_name'] == selected_location].sort_values('timestamp', ascending=False)
    latest_data = df_location.iloc[0]

    # --- Main Display Section ---
    main_cols = st.columns([2, 1])
    with main_cols[0]:
        st.markdown('<div class="custom-card aqi-display">', unsafe_allow_html=True)
        aqi_color, aqi_level = get_aqi_status(latest_data['aqi'])
        st.markdown(f'<div class="aqi-value" style="color:{aqi_color};">{latest_data["aqi"]:.0f}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="aqi-level" style="color:{aqi_color};">{aqi_level}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="aqi-pm25">Based on PM2.5: {latest_data["pm25"]:.1f} µg/m³</div>', unsafe_allow_html=True)
        st.markdown("""<div class="gauge-bar"><div class="gauge-segment" style="background-color: #22c55e;"></div><div class="gauge-segment" style="background-color: #facc15;"></div><div class="gauge-segment" style="background-color: #f97316;"></div><div class="gauge-segment" style="background-color: #ef4444;"></div><div class="gauge-segment" style="background-color: #a855f7;"></div><div class="gauge-segment" style="background-color: #7f1d1d;"></div></div>""", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
    with main_cols[1]:
        st.markdown('<div class="custom-card">', unsafe_allow_html=True)
        st.markdown("<h5>Live Weather</h5>", unsafe_allow_html=True)
        st.metric("Temperature", f"{latest_data['temperature']:.1f}°C")
        st.metric("Humidity", f"{latest_data['humidity']:.0f}%")
        st.markdown('</div>', unsafe_allow_html=True)

    # --- Major Pollutants Section ---
    st.markdown('<div class="custom-card">', unsafe_allow_html=True)
    st.markdown("<h3>Major Pollutants</h3>", unsafe_allow_html=True)
    pollutant_cols = st.columns(6)
    pollutants = {'PM2.5': 'pm25', 'PM10': 'pm10', 'NO₂': 'no2', 'O₃': 'o3', 'CO': 'co'}
    i = 0
    for label, key in pollutants.items():
        value = latest_data.get(key)
        display_value = f"{value:.1f}" if pd.notna(value) else "N/A"
        with pollutant_cols[i % 6]:
            st.markdown(f"""<div class="metric-box"><div class="metric-value">{display_value}</div><div class="metric-label">{label}</div></div>""", unsafe_allow_html=True)
        i += 1
    st.markdown('</div>', unsafe_allow_html=True)
    
    # --- Historical Chart Section ---
    st.markdown('<div class="custom-card">', unsafe_allow_html=True)
    st.markdown("<h3>Historical Data (Last 24 Hours)</h3>", unsafe_allow_html=True)
    last_24h_df = df_location[df_location['timestamp'] >= (latest_data['timestamp'] - timedelta(hours=24))].copy()
    
    if not last_24h_df.empty:
        component_to_graph = st.selectbox("Select Historical Metric to Graph", ['aqi', 'pm25', 'pm10', 'temperature', 'humidity'])
        last_24h_df['color'] = last_24h_df['aqi'].apply(lambda x: get_aqi_status(x)[0])
        fig = go.Figure()
        fig.add_trace(go.Bar(x=last_24h_df['timestamp'], y=last_24h_df[component_to_graph], marker_color=last_24h_df['color'] if component_to_graph == 'aqi' else '#4fd1c7'))
        fig.update_layout(title_text=f'{component_to_graph.upper()} Trend', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font={'color': 'white'})
        st.plotly_chart(fig, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)