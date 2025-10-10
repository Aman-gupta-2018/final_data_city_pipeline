# app.py (Final version with units added)
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import plotly.express as px
import plotly.graph_objects as go
from datetime import timedelta

# --- Page Configuration ---
st.set_page_config(page_title="Mumbai Air Quality Dashboard", layout="wide")

# --- Custom CSS ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    body { font-family: 'Inter', sans-serif; }
    .main { background-color: #0D1117; }
    .block-container { padding-top: 2rem; }
    h1 {
        background: -webkit-linear-gradient(45deg, #4fd1c7, #63b3ed);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    h3 {
        color: #C9D1D9 !important;
        border-bottom: 2px solid #4fd1c7;
        padding-bottom: 10px;
        margin-bottom: 1.5rem;
    }
</style>
""", unsafe_allow_html=True)

# --- Helper Functions ---
def pm25_to_us_aqi(pm25):
    if pd.isna(pm25) or pm25 < 0: return None
    if pm25 > 1000: return 500
    if 0.0 <= pm25 <= 12.0: return round(((50 - 0) / (12.0 - 0.0)) * (pm25 - 0.0) + 0)
    if 12.1 <= pm25 <= 35.4: return round(((100 - 51) / (35.4 - 12.1)) * (pm25 - 12.1) + 51)
    if 35.5 <= pm25 <= 55.4: return round(((150 - 101) / (55.4 - 35.5)) * (pm25 - 35.5) + 101)
    if 55.5 <= pm25 <= 150.4: return round(((200 - 151) / (150.4 - 55.5)) * (pm25 - 55.5) + 151)
    if 150.5 <= pm25 <= 250.4: return round(((300 - 201) / (250.4 - 150.5)) * (pm25 - 150.5) + 201)
    return 500

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

    st.header(f"Live Metrics for {selected_location}", divider='rainbow')
    
    main_cols = st.columns(2)
    with main_cols[0]:
        aqi_val = latest_data["aqi"]
        aqi_color, aqi_level = get_aqi_status(aqi_val)
        
        aqi_gauge = go.Figure(go.Indicator(
            mode = "gauge+number", value = aqi_val,
            domain = {'x': [0, 1], 'y': [0, 1]},
            number = {'font': {'size': 80, 'color': aqi_color}},
            title = {'text': f"<b>{aqi_level}</b>", 'font': {'size': 24}},
            gauge = {
                'axis': {'range': [0, 300], 'tickwidth': 1, 'tickcolor': "#8B949E"},
                'bar': {'color': aqi_color, 'thickness': 0},
                'bgcolor': "rgba(0,0,0,0)", 'shape': "angular",
                'steps': [
                    {'range': [0, 50], 'color': '#22c55e'}, {'range': [51, 100], 'color': '#facc15'},
                    {'range': [101, 150], 'color': '#f97316'}, {'range': [151, 200], 'color': '#ef4444'},
                    {'range': [201, 300], 'color': '#a855f7'}],
                'threshold': {'line': {'color': "white", 'width': 3}, 'thickness': 0.8, 'value': aqi_val}
            }))
        aqi_gauge.update_layout(height=250, margin=dict(l=30, r=30, t=60, b=30), paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(aqi_gauge, use_container_width=True)

    with main_cols[1]:
        st.markdown("<br><br>", unsafe_allow_html=True)
        sub_cols = st.columns(2)
        sub_cols[0].metric("Temperature", f"{latest_data['temperature']:.1f}°C")
        sub_cols[1].metric("Humidity", f"{latest_data['humidity']:.0f}%")
        sub_cols[0].metric("PM2.5", f"{latest_data['pm25']:.1f} µg/m³")
        sub_cols[1].metric("PM10", f"{latest_data['pm10']:.1f} µg/m³" if pd.notna(latest_data['pm10']) else "N/A")

    st.header("Major Pollutants", divider='rainbow')
    pollutant_cols = st.columns(6)
    pollutants = {'NO₂': 'no2', 'O₃': 'o3', 'CO': 'co'}
    i = 0
    for label, key in pollutants.items():
        value = latest_data.get(key)
        with pollutant_cols[i]:
            # --- FIX: Added the unit 'µg/m³' to the display ---
            st.metric(label, f"{value:.1f} µg/m³" if pd.notna(value) else "N/A")
        i += 1
    
    st.header("Next Hour Predictions", divider='rainbow')
    st.info("Train your models by running `python train_models.py` to see predictions here.")
    
    st.header("Historical Data (Last 24 Hours)", divider='rainbow')
    last_24h_df = df_location[df_location['timestamp'] >= (latest_data['timestamp'] - timedelta(hours=24))].copy()
    
    if not last_24h_df.empty:
        component_to_graph = st.selectbox("Select Historical Metric", ['aqi', 'pm25', 'pm10', 'temperature', 'humidity'])
        
        fig = px.area(
            last_24h_df, x='timestamp', y=component_to_graph,
            title=f'{component_to_graph.upper()} Trend', markers=True
        )
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font={'color': 'white'})
        fig.update_traces(line=dict(color='#63b3ed'))
        
        st.plotly_chart(fig, use_container_width=True)