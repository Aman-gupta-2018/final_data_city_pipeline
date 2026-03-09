import streamlit as st
import pandas as pd
import joblib, os
import plotly.graph_objects as go
from sqlalchemy import create_engine
from datetime import timedelta

# --- AESTHETIC CONFIG ---
st.set_page_config(page_title="Mumbai Smart City Air Dashboard", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #0f172a; }
    .stApp { background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); color: white; }
    [data-testid="stMetricValue"] { font-size: 2rem !important; color: #3b82f6; }
    .prediction-card { 
        background: rgba(255, 255, 255, 0.05); 
        padding: 25px; 
        border-radius: 20px; 
        border: 1px solid rgba(255, 255, 255, 0.1); 
        backdrop-filter: blur(12px); 
        margin-bottom: 20px;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
    }
    .status-good { color: #22c55e; font-weight: bold; }
    .status-bad { color: #ef4444; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- DATABASE & LOGIC ---
@st.cache_resource
def get_db(): return create_engine(st.secrets["SUPABASE_CONNECTION_STRING"])

def get_recursive_predictions(latest_row, area, hours=3):
    results = []
    current_data = latest_row.to_dict()
    for h in range(1, hours + 1):
        pred_time = current_data['timestamp'] + timedelta(hours=1)
        preds = {'hour_offset': h, 'timestamp': pred_time}
        for col in ['pm25', 'temperature', 'humidity']:
            path = f'models/{area}_{col}_model.pkl'
            if not os.path.exists(path): return None
            m_data = joblib.load(path)
            feat = pd.DataFrame([{
                'hour': pred_time.hour, 'day_of_week': pred_time.dayofweek,
                f'{col}_lag1': current_data[col], f'{col}_roll_avg3': current_data[col]
            }])[m_data['features']]
            preds[col] = float(m_data['model'].predict(feat)[0])
        results.append(preds)
        current_data.update(preds)
    return results

def get_human_advice(pm25):
    if pm25 <= 12: return "✨ The air is crystal clear! It's a <span class='status-good'>great day</span> for outdoor exercise."
    if pm25 <= 35: return "🍃 The air is <span class='status-good'>fairly good</span>, but sensitive groups might feel a slight haze."
    if pm25 <= 55: return "⚠️ It's getting <span class='status-bad'>dusty</span>. If you have asthma, you should consider staying indoors."
    return "🚫 The air quality is <span class='status-bad'>bad</span>. Please wear a mask; it is not healthy to be outside."

# --- UI EXECUTION ---
st.title("🏙️ Mumbai Smart City: Air Intelligence")
df = pd.read_sql("SELECT * FROM city_metrics ORDER BY timestamp DESC LIMIT 2000", get_db(), parse_dates=['timestamp'])
df['timestamp'] = df['timestamp'].dt.tz_convert('Asia/Kolkata')

if not df.empty:
    locs = sorted(df['area_name'].unique())
    selected_loc = st.sidebar.selectbox("Select Neighborhood", locs)
    latest = df[df['area_name'] == selected_loc].iloc[0]

    # Current Stats
    st.subheader(f"Current Environment: {selected_loc}")
    c1, c2, c3 = st.columns(3)
    c1.metric("PM2.5", f"{latest['pm25']:.1f} µg/m³")
    c2.metric("Temp", f"{latest['temperature']:.1f}°C")
    c3.metric("Humidity", f"{latest['humidity']:.0f}%")

    # Predictions
    st.divider()
    st.header("🕒 3-Hour Smart Forecast")
    forecasts = get_recursive_predictions(latest, selected_loc)

    if forecasts:
        for f in forecasts:
            st.markdown(f"""<div class="prediction-card">
                <h3 style="margin-top:0;">{f['hour_offset']} Hour Forecast ({f['timestamp'].strftime('%I:%M %p')})</h3>
                <p style="font-size:1.2rem; line-height:1.6;">{get_human_advice(f['pm25'])}</p>
                <div style="display:flex; gap:40px; margin-top:15px;">
                    <div><b>PM2.5:</b> {f['pm25']:.1f}</div>
                    <div><b>Temp:</b> {f['temperature']:.1f}°C</div>
                    <div><b>Humidity:</b> {f['humidity']:.0f}%</div>
                </div>
            </div>""", unsafe_allow_html=True)
    else:
        st.info("Training models for this new location... please run train_models.py first.")