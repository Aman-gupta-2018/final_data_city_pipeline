import streamlit as st
import pandas as pd
import joblib, os
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import create_engine
from datetime import timedelta

# --- AESTHETIC CONFIG ---
st.set_page_config(page_title="Mumbai Air Intelligence", layout="wide")

st.markdown("""
    <style>
    .stApp { background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); color: white; }
    .prediction-card { 
        background: rgba(255, 255, 255, 0.05); 
        padding: 20px; border-radius: 15px; 
        border: 1px solid rgba(255, 255, 255, 0.1); 
        backdrop-filter: blur(10px); 
        margin-bottom: 15px;
    }
    .advice-text { font-size: 1rem; line-height: 1.4; color: #cbd5e1; }
    .status-good { color: #22c55e; font-weight: bold; }
    .status-bad { color: #ef4444; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- DATABASE CONNECTION ---
@st.cache_resource
def get_db():
    return create_engine(st.secrets["SUPABASE_CONNECTION_STRING"])

# --- CORE LOGIC ---
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
                'hour': pred_time.hour,
                'day_of_week': pred_time.dayofweek,
                'month': pred_time.month,
                f'{col}_lag1': current_data[col],
                f'{col}_roll_avg3': current_data[col] # Simplified rolling for recursion
            }])[m_data['features']]
            preds[col] = float(m_data['model'].predict(feat)[0])
        results.append(preds)
        current_data.update(preds)
    return results

def get_human_advice(pm25):
    if pm25 <= 12: return "✨ The air is crystal clear! It's a <span class='status-good'>great time</span> for a walk."
    if pm25 <= 35: return "🍃 The air is <span class='status-good'>decent</span>, though you might notice a slight haze."
    if pm25 <= 55: return "⚠️ It's getting <span class='status-bad'>dusty</span>. If you're sensitive, stay indoors."
    return "🚫 The air is <span class='status-bad'>bad</span>. Wear a mask; it's not healthy outside."

# --- UI EXECUTION ---
st.title("🏙️ Mumbai Smart City: Air Intelligence")

try:
    df = pd.read_sql("SELECT * FROM city_metrics ORDER BY timestamp DESC LIMIT 2000", get_db(), parse_dates=['timestamp'])
    
    if not df.empty:
        # Sidebar
        locs = sorted(df['area_name'].unique())
        selected_loc = st.sidebar.selectbox("Select Neighborhood", locs)
        latest = df[df['area_name'] == selected_loc].iloc[0]

        # 1. Current Stats
        st.subheader(f"Current Stats: {selected_loc}")
        m1, m2, m3 = st.columns(3)
        m1.metric("PM2.5", f"{latest['pm25']:.1f} µg/m³")
        m2.metric("Temp", f"{latest['temperature']:.1f}°C")
        m3.metric("Humidity", f"{latest['humidity']:.0f}%")

        # 2. 3-HOUR FORECAST
        st.divider()
        st.header("🕒 3-Hour Predictive Forecast")
        forecasts = get_recursive_predictions(latest, selected_loc)

        if forecasts:
            f_cols = st.columns(3)
            for i, f in enumerate(forecasts):
                with f_cols[i]:
                    st.markdown(f"""
                    <div class="prediction-card">
                        <h4 style="margin-top:0;">+{f['hour_offset']}h ({f['timestamp'].strftime('%I:%M %p')})</h4>
                        <div class="advice-text">{get_human_advice(f['pm25'])}</div>
                        <p style="margin-top:10px;"><b>PM2.5:</b> {f['pm25']:.1f}</p>
                    </div>
                    """, unsafe_allow_html=True)
        
        # 3. GRAPHS & COMPARISONS
        st.divider()
        st.header("📊 Area Comparisons & Trends")
        
        # Trend Graph
        fig_trend = px.line(df[df['area_name'] == selected_loc], x='timestamp', y='pm25', 
                            title=f"PM2.5 Trend for {selected_loc}", template="plotly_dark")
        st.plotly_chart(fig_trend, use_container_width=True)
        
        # Multi-Area Comparison
        comp_locs = st.multiselect("Compare with other areas:", locs, default=["Vasai", "Bhiwandi", "Kaman Road"])
        if comp_locs:
            comp_df = df[df['area_name'].isin(comp_locs)]
            fig_comp = px.bar(comp_df.groupby('area_name')['pm25'].mean().reset_index(), 
                              x='area_name', y='pm25', color='area_name',
                              title="Average PM2.5 Comparison", template="plotly_dark")
            st.plotly_chart(fig_comp, use_container_width=True)

    else:
        st.error("No data found in Supabase.")
except Exception as e:
    st.error(f"Error: {e}")