import streamlit as st
import pandas as pd
import joblib, os
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import create_engine
from datetime import timedelta
import numpy as np

#PAGE CONFIG
st.set_page_config(
    page_title="Mumbai Air Intelligence",
    layout="wide",
    page_icon="🏙️",
    initial_sidebar_state="expanded"
)

#CSS INJECTION
_CSS = """
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@300;400;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
*, *::before, *::after { box-sizing: border-box; }
html, body, .stApp {
    font-family: 'Sora', sans-serif !important;
    background: #060d1a !important;
    color: #e2e8f0 !important;
}
[data-testid="stSidebar"] {
    background: rgba(6,13,26,0.97) !important;
    border-right: 1px solid rgba(251,146,60,0.15) !important;
}
[data-testid="stSidebar"] * { color: #94a3b8 !important; font-family: 'Sora',sans-serif !important; }
[data-testid="stSidebar"] strong { color: #e2e8f0 !important; }
[data-testid="stHeader"] { background: transparent !important; }
.block-container { padding-top: 2rem !important; max-width: 1400px !important; }
footer, #MainMenu { display: none !important; }
.stTabs [data-baseweb="tab-list"] {
    background: rgba(255,255,255,0.03) !important;
    border-radius: 12px; padding: 4px; gap: 2px;
    border: 1px solid rgba(255,255,255,0.07);
}
.stTabs [data-baseweb="tab"] {
    border-radius: 9px !important;
    font-family: 'Sora', sans-serif !important;
    font-size: 0.82rem !important; font-weight: 500 !important;
    color: #64748b !important; padding: 8px 18px !important;
}
.stTabs [aria-selected="true"] {
    background: rgba(251,146,60,0.15) !important;
    color: #fbbf24 !important;
}
.stTabs [data-baseweb="tab-highlight"],
.stTabs [data-baseweb="tab-border"] { display: none !important; }
.stSelectbox > div > div, .stMultiSelect > div > div {
    background: rgba(255,255,255,0.05) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 10px !important; color: #e2e8f0 !important;
    font-family: 'Sora', sans-serif !important;
}
hr { border-color: rgba(255,255,255,0.06) !important; }

[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"],
button[aria-label="Collapse sidebar"],
button[aria-label="Expand sidebar"],
button[aria-label="Close sidebar"],
section[data-testid="stSidebar"] > div:first-child > div > button {
    display: none !important;
}
[data-testid="stSidebar"] > div:first-child {
    overflow: hidden !important;
    padding-top: 1.5rem !important;
}
</style>
"""
try:
    st.html(_CSS)
except AttributeError:
    st.markdown(_CSS, unsafe_allow_html=True)

#STYLE HELPERS
_CARD = (
    "background:rgba(255,255,255,0.033);"
    "border:1px solid rgba(255,255,255,0.07);"
    "border-radius:18px;padding:22px 26px;margin-bottom:18px;"
    "position:relative;overflow:hidden;"
)
_TOP_LINE = (
    "position:absolute;top:0;left:0;right:0;height:1px;"
    "background:linear-gradient(90deg,transparent,rgba(251,146,60,0.4),transparent);"
)
_SEC_HDR = (
    "font-size:0.7rem;letter-spacing:0.2em;text-transform:uppercase;"
    "color:#f97316;font-weight:600;margin-bottom:14px;"
)

def sec_hdr(text):
    return f'<div style="{_SEC_HDR}">{text}</div>'

def hex_to_rgba(hex_color, alpha=0.08):
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
    return f'rgba({r},{g},{b},{alpha})'

#CONSTANTS
SPARSE_THRESHOLD = 500

# Quarantine broken sensors so they do not render on the UI
QUARANTINED_AREAS = ["Powai", "Andheri", "Colaba"]

TARGETS = ['pm25', 'pm10', 'temperature', 'humidity']
TARGET_COLS = TARGETS

PLOT_CFG = dict(
    paper_bgcolor='rgba(0,0,0,0)',
    plot_bgcolor='rgba(0,0,0,0)',
    font=dict(family='Sora, sans-serif', color='#94a3b8'),
    margin=dict(l=0, r=0, t=30, b=0),
)
GRID = dict(gridcolor='rgba(255,255,255,0.05)', zerolinecolor='rgba(255,255,255,0.08)')

PM_META = {
    'pm25':        {'label':'PM2.5',   'unit':'µg/m³','color':'#f97316','safe':30},
    'pm10':        {'label':'PM10',    'unit':'µg/m³','color':'#fb923c','safe':60},
    'no2':         {'label':'NO₂',     'unit':'µg/m³','color':'#a78bfa','safe':40},
    'o3':          {'label':'O₃',      'unit':'µg/m³','color':'#38bdf8','safe':100},
    'co':          {'label':'CO',      'unit':'µg/m³','color':'#34d399','safe':4000},
    'temperature': {'label':'Temp',    'unit':'°C',   'color':'#fbbf24','safe':None},
    'humidity':    {'label':'Humidity','unit':'%',    'color':'#60a5fa','safe':None},
}
AREA_PAL = ['#f97316','#38bdf8','#a78bfa','#34d399','#fbbf24',
            '#fb7185','#2dd4bf','#facc15','#60a5fa','#c084fc']

def pm25_to_aqi(pm25):
    if pd.isna(pm25) or pm25 < 0: return 0
    c = round(float(pm25), 1)
    def _lerp(c_lo, c_hi, i_lo, i_hi, v):
        return round(((i_hi - i_lo) / (c_hi - c_lo)) * (v - c_lo) + i_lo)
    if c <= 30:  return _lerp(0,   30,  0,   50,  c)
    if c <= 60:  return _lerp(31,  60,  51,  100, c)
    if c <= 90:  return _lerp(61,  90,  101, 200, c)
    if c <= 120: return _lerp(91,  120, 201, 300, c)
    if c <= 250: return _lerp(121, 250, 301, 400, c)
    if c <= 380: return _lerp(251, 380, 401, 500, c)
    return 500

AQI_BANDS = [
    (50,  '#22c55e','Good',         '✨ Clear air — perfect for outdoor activity.'),
    (100, '#a3e635','Satisfactory', '🍃 Mostly good; minor discomfort for sensitive groups.'),
    (200, '#facc15','Moderate',     '⚠️ May cause breathing discomfort on prolonged exposure.'),
    (300, '#f97316','Poor',         '🌫️ Avoid outdoor activity; children & elderly at risk.'),
    (400, '#ef4444','Very Poor',    '🚨 Serious health risk — stay indoors, keep windows closed.'),
    (999, '#7c3aed','Severe',       '☠️ Hazardous! Medical emergency risk for all groups.'),
]

def get_status(aqi):
    for thr, col, lbl, msg in AQI_BANDS:
        if aqi <= thr: return col, lbl, msg
    return '#7c3aed', 'Severe', '☠️ Hazardous!'

#DB
@st.cache_resource
def get_db():
    return create_engine(st.secrets["SUPABASE_CONNECTION_STRING"])

@st.cache_data(ttl=60)
def load_data():
    engine = get_db()

    df_hist = pd.read_sql(
        "SELECT * FROM city_metrics "
        "WHERE timestamp >= NOW() - INTERVAL '7 days' "
        "ORDER BY timestamp DESC",
        engine, parse_dates=['timestamp']
    )

    df_latest = pd.read_sql(
        "SELECT DISTINCT ON (area_name) * FROM city_metrics "
        "ORDER BY area_name, timestamp DESC",
        engine, parse_dates=['timestamp']
    )

    df = (pd.concat([df_hist, df_latest])
            .drop_duplicates(subset=['timestamp','area_name'])
            .reset_index(drop=True))

    df['timestamp'] = df['timestamp'].dt.tz_convert('Asia/Kolkata')

    df = df.sort_values(['area_name','timestamp']).reset_index(drop=True)
    
    # Filter out quarantined areas before calculating rolling averages
    df = df[~df['area_name'].isin(QUARANTINED_AREAS)].reset_index(drop=True)
    
    for col in ['pm25','pm10','temperature','humidity']:
        df[f'{col}_roll_avg_7d'] = (
            df.groupby('area_name')[col]
              .transform(lambda s: s.shift(1).rolling(window=336, min_periods=1).mean())
        )

    df['aqi'] = df['pm25'].apply(pm25_to_aqi)
    return df

#PREDICTIONS
CLAMP   = {'pm25':(0,500),'pm10':(0,600),'temperature':(10,45),'humidity':(5,100)}

def get_predictions(df_area, area, hours=3):
    results = []
    
    #Resample the actual history to a 15-minute grid to match training
    df_hist = df_area.copy().set_index('timestamp').sort_index()
    df_hist = df_hist.resample('15min').mean(numeric_only=True).interpolate(method='linear', limit=4)

    #Need at least 97 records to build features
    if len(df_hist) < 97:
        return None

    # Extract true historical series
    history = {col: df_hist[col].values.tolist() for col in TARGET_COLS if col in df_hist.columns}
    cur_time = df_hist.index[-1]

    #Determine steps_per_hour dynamically
    _sph = 4
    for _col in TARGET_COLS:
        path = f'models/{area}_{_col}_model.pkl'
        if os.path.exists(path):
            _sph = joblib.load(path).get('steps_per_hour', 4)
            break

    total_steps = hours * _sph

    for step in range(1, total_steps + 1):
        pt = cur_time + timedelta(minutes=(60 / _sph) * step)
        p = {'hour_offset': int(step / _sph), 'timestamp': pt}
        
        temp_val = history['temperature'][-1]
        hum_val = history['humidity'][-1]
        thi = temp_val * (1 - hum_val / 100)

        for col in TARGET_COLS:
            path = f'models/{area}_{col}_model.pkl'
            if not os.path.exists(path): return None
            m_data = joblib.load(path)
            
            hist = history[col]

            feat_dict = {
                'hour': pt.hour,
                'day_of_week': pt.dayofweek,
                'month': pt.month,
                'is_weekend': int(pt.dayofweek >= 5),
                'hour_sin': float(np.sin(2 * np.pi * pt.hour / 24)),
                'hour_cos': float(np.cos(2 * np.pi * pt.hour / 24)),
                f'{col}_lag1': hist[-1],
                f'{col}_lag4': hist[-4],   
                f'{col}_lag96': hist[-96], 
                f'{col}_roll_3h': float(np.mean(hist[-12:])),
                f'{col}_roll_24h': float(np.mean(hist[-96:])),
                'temp_humidity_idx': thi,
            }

            row_data = {k: feat_dict[k] for k in m_data['features'] if k in feat_dict}
            feat_df = pd.DataFrame([row_data])[m_data['features']]

            raw = float(m_data['model'].predict(feat_df)[0])
            lo, hi = CLAMP.get(col, (None, None))
            val = max(lo, min(hi, raw)) if lo is not None else raw
            p[col] = val

            history[col].append(val)

        if step % _sph == 0:
            p['aqi'] = pm25_to_aqi(p['pm25'])
            results.append(p)

    return results

#PLOT HELPERS
def theme(fig, height=300, margin=None):
    m = margin or dict(l=0,r=0,t=30,b=0)
    fig.update_layout(height=height, margin=m,
                      paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                      font=dict(family='Sora,sans-serif', color='#94a3b8'))
    fig.update_xaxes(**GRID)
    fig.update_yaxes(**GRID)
    return fig

def sparkline(df_in, col, color, height=240, title=''):
    df_h = (df_in.set_index('timestamp')[col]
            .resample('15min').mean().dropna().reset_index())
    df_h.columns = ['timestamp', col]
    fig = go.Figure(go.Scatter(
        x=df_h['timestamp'], y=df_h[col], mode='lines',
        line=dict(color=color, width=2),
        fill='tozeroy', fillcolor=hex_to_rgba(color, 0.08),
        hovertemplate=f'<b>{col.upper()}</b> %{{y:.1f}}<extra></extra>',
    ))
    if title:
        fig.update_layout(title=dict(text=title, font=dict(size=12,color='#64748b')))
    return theme(fig, height=height)

def aqi_gauge(val, color):
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=min(val, 500),
        number=dict(font=dict(color=color, size=64, family='JetBrains Mono')),
        title=dict(text="AQI (India CPCB)", font=dict(size=12, color='#64748b', family='Sora')),
        gauge=dict(
            axis=dict(
                range=[0, 500],
                tickmode='array',
                tickvals=[0, 50, 100, 200, 300, 400, 500],
                ticktext=['0','50','100','200','300','400','500'],
                tickfont=dict(size=8, color='#475569'),
            ),
            bar=dict(color=color, thickness=0.22),
            bgcolor='rgba(255,255,255,0.02)', borderwidth=0,
            steps=[
                dict(range=[0,   50],  color='rgba(34,197,94,0.12)'),
                dict(range=[50,  100], color='rgba(163,230,53,0.10)'),
                dict(range=[100, 200], color='rgba(250,204,21,0.09)'),
                dict(range=[200, 300], color='rgba(249,115,22,0.09)'),
                dict(range=[300, 400], color='rgba(239,68,68,0.09)'),
                dict(range=[400, 500], color='rgba(124,58,237,0.09)'),
            ],
            threshold=dict(line=dict(color=color, width=3), thickness=0.8, value=min(val,500)),
        )
    ))
    return theme(fig, height=290, margin=dict(l=10,r=10,t=10,b=10))

#LOAD DATA
try:
    df = load_data()
except Exception as e:
    st.error(f"**Database error:** {e}")
    st.stop()

if df.empty:
    st.warning("No data yet. Run the collection pipeline first.")
    st.stop()

#SIDEBAR
all_areas = sorted(df['area_name'].unique())
with st.sidebar:
    st.markdown("### 📍 Location")
    selected_area = st.selectbox("Neighbourhood", all_areas, label_visibility='collapsed')
    st.markdown("---")
    st.markdown("### 🗓️ Time window")
    time_window = st.selectbox(
        "Show last", ['24 hours','48 hours','7 days','All data'],
        label_visibility='collapsed'
    )
    st.markdown("---")
    st.markdown("### ℹ️ About")
    st.markdown(
        f"Data collected every **15 mins** from OpenWeatherMap And WAQI "
        f"across {len(all_areas)} Mumbai neighbourhoods.\n\n"
        "Predictions use XGBoost models trained on historical records."
    )

def filter_window(df_in, w):
    ts = df_in['timestamp'].max()
    h  = {'24 hours':24,'48 hours':48,'7 days':168}.get(w)
    return df_in[df_in['timestamp'] >= ts - timedelta(hours=h)] if h else df_in

df_area   = df[df['area_name'] == selected_area].sort_values('timestamp', ascending=False)
df_window = filter_window(df_area, time_window)
latest    = df_area.iloc[0]
n_recs    = len(df_area)
is_sparse = n_recs < SPARSE_THRESHOLD
aqi_val   = int(latest['aqi'])
aqi_color, aqi_label, aqi_msg = get_status(aqi_val)

from datetime import timezone as _tz
_now_ist = pd.Timestamp.now(tz='Asia/Kolkata')
_data_age_min = int((_now_ist - latest['timestamp']).total_seconds() / 60)
_data_stale   = _data_age_min > 60

#PAGE HEADER
st.markdown(
    '<h1 style="font-family:Sora,sans-serif;font-weight:700;font-size:clamp(1.8rem,3vw,2.6rem);'
    'letter-spacing:-0.03em;background:linear-gradient(135deg,#fbbf24,#f97316,#fb923c);'
    '-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;margin:0 0 4px;">'
    '🏙️ Mumbai Air Intelligence</h1>'
    '<p style="font-size:0.8rem;letter-spacing:0.18em;text-transform:uppercase;'
    'color:#475569;margin-bottom:24px;">'
    'Real-time air quality · Predictive analytics · Smart city dashboard</p>',
    unsafe_allow_html=True
)

if is_sparse:
    st.markdown(
        f'<div style="background:linear-gradient(135deg,rgba(251,146,60,0.10),rgba(245,158,11,0.06));'
        f'border:1px solid rgba(251,146,60,0.25);border-radius:12px;padding:14px 20px;'
        f'display:flex;align-items:center;gap:12px;margin-bottom:18px;">'
        f'<span style="font-size:1.3rem;">📡</span>'
        f'<div><b style="color:#fbbf24;font-size:0.88rem;">Data Collection in Progress</b><br>'
        f'<span style="font-size:0.78rem;color:#94a3b8;">{selected_area} was recently added '
        f'({n_recs:,} records). Live readings shown; ML forecasts activate once enough data is collected.'
        f'</span></div></div>',
        unsafe_allow_html=True
    )

tab_live, tab_trends, tab_compare, tab_poll = st.tabs([
    "🔴  Live Dashboard", "📈  Historical Trends",
    "🗺️  Area Comparison", "🧪  Pollutant Analysis",
])

with tab_live:
    col_g, col_info = st.columns([1, 2], gap="large")

    with col_g:
        badge_bg = 'rgba(34,197,94,0.12)' if aqi_val<=50 else 'rgba(249,115,22,0.12)'
        st.plotly_chart(aqi_gauge(aqi_val, aqi_color),
                        use_container_width=True, config={'displayModeBar': False})
        st.markdown(
            f'<div style="text-align:center;margin-top:-8px;">'
            f'<span style="display:inline-flex;align-items:center;padding:5px 14px;'
            f'border-radius:100px;background:{badge_bg};color:{aqi_color};'
            f'border:1px solid {aqi_color}44;font-size:0.75rem;font-weight:600;'
            f'letter-spacing:0.06em;text-transform:uppercase;">{aqi_label}</span>'
            f'<p style="font-size:0.82rem;color:#94a3b8;margin-top:10px;line-height:1.5;">{aqi_msg}</p>'
            f'<p style="font-size:0.68rem;color:{"#ef4444" if _data_stale else "#475569"};">' 
            f'{"⚠️ Data is " + str(_data_age_min) + " min old — collection may have missed a run" if _data_stale else "Updated " + latest["timestamp"].strftime("%d %b · %I:%M %p IST")}</p>'
            f'</div>',
            unsafe_allow_html=True
        )

    with col_info:
        def chip(key, val):
            m    = PM_META.get(key, {})
            safe = m.get('safe')
            num  = f"{val:.1f}" if pd.notna(val) else "—"
            clr  = '#ef4444' if (safe and pd.notna(val) and val > safe) else '#e2e8f0'
            return (
                f'<div style="background:rgba(255,255,255,0.04);'
                f'border:1px solid rgba(255,255,255,0.08);border-radius:10px;'
                f'padding:10px 14px;flex:1;min-width:82px;">'
                f'<div style="font-size:0.66rem;color:#64748b;letter-spacing:0.1em;'
                f'text-transform:uppercase;">{m.get("label",key)}</div>'
                f'<div style="font-family:JetBrains Mono,monospace;font-size:1.15rem;'
                f'font-weight:600;color:{clr};margin-top:2px;">{num}'
                f'<span style="font-size:0.58rem;color:#475569;margin-left:3px;">'
                f'{m.get("unit","")}</span></div></div>'
            )

        chips = "".join([
            chip('pm25',        latest.get('pm25')),
            chip('pm10',        latest.get('pm10')),
            chip('no2',         latest.get('no2')),
            chip('o3',          latest.get('o3')),
            chip('co',          latest.get('co')),
            chip('temperature', latest.get('temperature')),
            chip('humidity',    latest.get('humidity')),
        ])
        st.markdown(
            f'<div style="{_CARD}">'
            f'<div style="{_TOP_LINE}"></div>'
            f'<div style="{_SEC_HDR}">Pollutant readings</div>'
            f'<div style="display:flex;gap:10px;flex-wrap:wrap;">{chips}</div>'
            f'</div>',
            unsafe_allow_html=True
        )

        df24 = df_area[df_area['timestamp'] >= latest['timestamp'] - timedelta(hours=24)]
        if len(df24) > 2:
            fig_sp = sparkline(df24.sort_values('timestamp'), 'pm25', '#f97316',
                               height=150, title='PM2.5 — last 24 hours')
            fig_sp.add_hline(y=30, line_dash='dot',
                             line_color='rgba(251,191,36,0.4)', line_width=1)
            fig_sp.update_xaxes(showticklabels=False)
            st.plotly_chart(fig_sp, use_container_width=True, config={'displayModeBar': False})

    st.markdown(f'<div style="{_SEC_HDR}margin-top:6px;">3-Hour Predictive Forecast</div>',
                unsafe_allow_html=True)

    if is_sparse:
        st.markdown(
            '<div style="background:rgba(251,146,60,0.06);border:1px solid rgba(251,146,60,0.15);'
            'border-radius:12px;padding:20px;text-align:center;color:#94a3b8;font-size:0.85rem;">'
            '🤖 &nbsp;ML models training — forecasts available once enough data is collected.</div>',
            unsafe_allow_html=True
        )
    else:
        forecasts = get_predictions(df_area, selected_area)
        if forecasts:
            f_cols = st.columns(3, gap="medium")
            for i, f in enumerate(forecasts):
                fc, fl, fm = get_status(f['aqi'])
                with f_cols[i]:
                    st.markdown(
                        f'<div style="background:rgba(255,255,255,0.03);'
                        f'border:1px solid rgba(255,255,255,0.07);'
                        f'border-top:3px solid {fc}44;border-radius:16px;padding:20px;">'
                        f'<div style="font-size:0.7rem;color:#475569;letter-spacing:0.1em;'
                        f'text-transform:uppercase;margin-bottom:8px;">'
                        f'+{f["hour_offset"]}h &nbsp;·&nbsp; {f["timestamp"].strftime("%I:%M %p")}</div>'
                        f'<div style="font-family:JetBrains Mono,monospace;font-size:2.2rem;'
                        f'font-weight:600;color:{fc};line-height:1;">{f["aqi"]}</div>'
                        f'<div style="font-size:0.77rem;font-weight:600;color:{fc};margin:4px 0 8px;">{fl}</div>'
                        f'<div style="font-size:0.74rem;color:#64748b;line-height:1.5;">{fm}</div>'
                        f'<div style="margin-top:12px;padding-top:10px;'
                        f'border-top:1px solid rgba(255,255,255,0.06);'
                        f'display:grid;grid-template-columns:1fr 1fr;gap:5px;font-size:0.68rem;">'
                        f'<div><span style="color:#475569;">PM2.5&nbsp;</span>'
                        f'<b style="color:#f97316;">{f["pm25"]:.1f}µg</b></div>'
                        f'<div><span style="color:#475569;">PM10&nbsp;</span>'
                        f'<b style="color:#fb923c;">{f["pm10"]:.1f}µg</b></div>'
                        f'<div><span style="color:#475569;">Temp&nbsp;</span>'
                        f'<b style="color:#fbbf24;">{f["temperature"]:.1f}°C</b></div>'
                        f'<div><span style="color:#475569;">Humidity&nbsp;</span>'
                        f'<b style="color:#60a5fa;">{f["humidity"]:.0f}%</b></div>'
                        f'</div></div>',
                        unsafe_allow_html=True
                    )
        else:
            st.info("Model files not found or lacking 24h history. Make sure to collect data and run `train_models.py`.")

with tab_trends:
    df_t = filter_window(df_area, time_window).sort_values('timestamp')
    if len(df_t) < 2:
        st.info("Not enough data. Try a wider time range.")
    else:
        st.markdown(f'<div style="{_SEC_HDR}">AQI Timeline — {selected_area}</div>',
                    unsafe_allow_html=True)
        df_th = df_t.set_index('timestamp').resample('15min').mean(numeric_only=True).reset_index()
        df_th['aqi'] = df_th['pm25'].apply(pm25_to_aqi)

        fig_aqi = go.Figure()
        for lo, hi, c in [(0,50,'#22c55e'),(50,100,'#a3e635'),(100,200,'#facc15'),
                           (200,300,'#f97316'),(300,500,'#ef4444')]:
            fig_aqi.add_hrect(y0=lo, y1=hi, fillcolor=c, opacity=0.04, line_width=0)
        fig_aqi.add_trace(go.Scatter(
            x=df_th['timestamp'], y=df_th['aqi'], mode='lines',
            line=dict(color='#f97316', width=2.5),
            fill='tozeroy', fillcolor='rgba(249,115,22,0.07)',
            hovertemplate='<b>AQI</b> %{y:.0f}<extra></extra>',
        ))
        theme(fig_aqi, height=240)
        fig_aqi.update_yaxes(title='AQI')
        st.plotly_chart(fig_aqi, use_container_width=True, config={'displayModeBar': False})

        st.markdown(f'<div style="{_SEC_HDR}">Pollutant Trends</div>', unsafe_allow_html=True)
        g1, g2 = st.columns(2, gap="medium")
        for i, col_key in enumerate(['pm25','pm10','temperature','humidity']):
            meta = PM_META[col_key]
            with (g1 if i % 2 == 0 else g2):
                fig = sparkline(df_t, col_key, meta['color'], height=220,
                                title=f'{meta["label"]} ({meta["unit"]})')
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

with tab_compare:
    snap = df.sort_values('timestamp').groupby('area_name').last().reset_index()
    snap['aqi']   = snap['pm25'].apply(pm25_to_aqi)
    snap['color'] = snap['aqi'].apply(lambda x: get_status(x)[0])
    snap['label'] = snap['aqi'].apply(lambda x: get_status(x)[1])
    snap = snap.sort_values('aqi', ascending=False)

    st.markdown(f'<div style="{_SEC_HDR}">Current AQI Ranking — All Neighbourhoods</div>',
                unsafe_allow_html=True)
    fig_bar = go.Figure(go.Bar(
        x=snap['aqi'], y=snap['area_name'], orientation='h',
        marker=dict(color=snap['color'], opacity=0.85, line=dict(width=0)),
        text=[f"  {v}  {l}" for v,l in zip(snap['aqi'],snap['label'])],
        textposition='outside',
        textfont=dict(size=11, color='#94a3b8', family='JetBrains Mono'),
        hovertemplate='<b>%{y}</b><br>AQI: %{x}<extra></extra>',
    ))
    for v,lbl,c in [(50,'Good','#22c55e'),(100,'Moderate','#facc15'),(200,'Poor','#f97316')]:
        fig_bar.add_vline(x=v, line_dash='dot', line_color=c, line_width=1,
                          annotation_text=lbl, annotation_font_size=9,
                          annotation_font_color=c, annotation_position='top')
    theme(fig_bar, height=380)
    fig_bar.update_xaxes(range=[0, max(snap['aqi'].max()*1.25, 150)])
    fig_bar.update_yaxes(categoryorder='total ascending')
    st.plotly_chart(fig_bar, use_container_width=True, config={'displayModeBar': False})

    c1, c2 = st.columns(2, gap="medium")
    with c1:
        st.markdown(f'<div style="{_SEC_HDR}">PM2.5 Across Areas</div>', unsafe_allow_html=True)
        df_pm = snap.sort_values('pm25', ascending=True)
        fig_pm = go.Figure(go.Bar(
            y=df_pm['area_name'], x=df_pm['pm25'], orientation='h',
            marker=dict(color='#f97316', opacity=0.75),
            hovertemplate='<b>%{y}</b><br>PM2.5: %{x:.1f} µg/m³<extra></extra>',
        ))
        fig_pm.add_vline(x=30, line_dash='dot', line_color='rgba(251,191,36,0.5)', line_width=1)
        theme(fig_pm, height=300)
        fig_pm.update_xaxes(title='µg/m³')
        st.plotly_chart(fig_pm, use_container_width=True, config={'displayModeBar': False})

    with c2:
        st.markdown(f'<div style="{_SEC_HDR}">Temperature & Humidity</div>', unsafe_allow_html=True)
        df_tw = snap.dropna(subset=['temperature','humidity']).sort_values('temperature')
        fig_th = go.Figure()
        fig_th.add_trace(go.Bar(
            name='Temp (°C)', x=df_tw['area_name'], y=df_tw['temperature'],
            marker=dict(color='#fbbf24', opacity=0.8),
            hovertemplate='%{x}<br>Temp: %{y:.1f}°C<extra></extra>',
        ))
        fig_th.add_trace(go.Bar(
            name='Humidity (%)', x=df_tw['area_name'], y=df_tw['humidity'],
            marker=dict(color='#60a5fa', opacity=0.7),
            hovertemplate='%{x}<br>Humidity: %{y:.1f}%<extra></extra>',
        ))
        theme(fig_th, height=300)
        fig_th.update_layout(
            barmode='group',
            legend=dict(orientation='h', y=1.05, font=dict(size=11, color='#94a3b8')),
        )
        fig_th.update_xaxes(tickangle=-30)
        st.plotly_chart(fig_th, use_container_width=True, config={'displayModeBar': False})

    st.markdown(f'<div style="{_SEC_HDR}">Multi-Area Timeline Comparison</div>',
                unsafe_allow_html=True)
    c_s1, c_s2 = st.columns([2,1], gap="small")
    with c_s1:
        cmp_areas = st.multiselect("Areas", all_areas, default=all_areas[:4],
                                   key='cmp_areas', label_visibility='collapsed')
    with c_s2:
        cmp_metric = st.selectbox("Metric", list(PM_META.keys()),
                                  format_func=lambda x: PM_META[x]['label'],
                                  key='cmp_metric', label_visibility='collapsed')

    if cmp_areas:
        df_cmp = filter_window(df[df['area_name'].isin(cmp_areas)], time_window)
        fig_cmp = go.Figure()
        for idx, area in enumerate(cmp_areas):
            da = df_cmp[df_cmp['area_name'] == area].sort_values('timestamp')
            dh = da.set_index('timestamp').resample('15min').mean(numeric_only=True)
            if cmp_metric == 'aqi': dh['aqi'] = dh['pm25'].apply(pm25_to_aqi)
            dh = dh.reset_index()
            if dh.empty or cmp_metric not in dh.columns: continue
            clr = AREA_PAL[idx % len(AREA_PAL)]
            fig_cmp.add_trace(go.Scatter(
                x=dh['timestamp'], y=dh[cmp_metric], name=area,
                mode='lines', line=dict(color=clr, width=2),
                hovertemplate=f'<b>{area}</b> %{{y:.1f}}<extra></extra>',
            ))
        theme(fig_cmp, height=300)
        fig_cmp.update_layout(
            legend=dict(orientation='h', y=1.05, font=dict(size=11,color='#94a3b8')),
        )
        fig_cmp.update_yaxes(title=PM_META.get(cmp_metric,{}).get('unit',''))
        st.plotly_chart(fig_cmp, use_container_width=True, config={'displayModeBar': False})

with tab_poll:
    df_p = filter_window(df_area, time_window).sort_values('timestamp')
    c_rad, c_scat = st.columns([1, 1.4], gap="large")

    with c_rad:
        st.markdown(f'<div style="{_SEC_HDR}">Pollutant Profile — {selected_area}</div>',
                    unsafe_allow_html=True)
        rcols = ['pm25','pm10','no2','o3']
        rsafe = [30, 60, 40, 100]
        rvals = [min((latest.get(c) or 0)/s*100, 200) for c,s in zip(rcols,rsafe)]
        rlbls = ['PM2.5','PM10','NO₂','O₃']
        fig_rad = go.Figure()
        fig_rad.add_trace(go.Scatterpolar(
            r=rvals+[rvals[0]], theta=rlbls+[rlbls[0]],
            fill='toself', fillcolor='rgba(249,115,22,0.12)',
            line=dict(color='#f97316', width=2),
            hovertemplate='<b>%{theta}</b><br>%{r:.0f}% of safe limit<extra></extra>',
        ))
        fig_rad.add_trace(go.Scatterpolar(
            r=[100]*5, theta=rlbls+[rlbls[0]], mode='lines',
            line=dict(color='rgba(251,191,36,0.35)', width=1, dash='dot'),
            showlegend=False, hoverinfo='skip',
        ))
        fig_rad.update_layout(
            height=300,
            margin=dict(l=0,r=0,t=10,b=0),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(family='Sora,sans-serif', color='#94a3b8'),
            polar=dict(
                bgcolor='rgba(255,255,255,0.02)',
                radialaxis=dict(visible=True, range=[0,200],
                                tickfont=dict(size=8,color='#475569'),
                                gridcolor='rgba(255,255,255,0.06)',
                                linecolor='rgba(255,255,255,0.06)'),
                angularaxis=dict(tickfont=dict(size=11,color='#94a3b8'),
                                 gridcolor='rgba(255,255,255,0.06)',
                                 linecolor='rgba(255,255,255,0.06)'),
            ),
            showlegend=False,
        )
        st.plotly_chart(fig_rad, use_container_width=True, config={'displayModeBar': False})
        st.markdown(
            '<p style="text-align:center;font-size:0.7rem;color:#475569;">'
            'Values as % of safe threshold · Dotted ring = safe limit</p>',
            unsafe_allow_html=True
        )

    with c_scat:
        st.markdown(f'<div style="{_SEC_HDR}">PM2.5 vs PM10 Correlation</div>',
                    unsafe_allow_html=True)
        df_sc = df_p.dropna(subset=['pm25','pm10'])
        if len(df_sc) > 5:
            fig_sc = px.scatter(
                df_sc, x='pm10', y='pm25', color='aqi',
                color_continuous_scale=['#22c55e','#facc15','#f97316','#ef4444','#7c3aed'],
                range_color=[0,350], opacity=0.65,
                hover_data={'timestamp':True,'pm25':':.1f','pm10':':.1f','aqi':True},
            )
            fig_sc.update_traces(marker=dict(size=6))
            fig_sc.update_coloraxes(colorbar=dict(
                title=dict(text='AQI', font=dict(size=11,color='#64748b')),
                tickfont=dict(size=9,color='#64748b'), thickness=10,
            ))
            theme(fig_sc, height=300)
            fig_sc.update_xaxes(title='PM10 µg/m³')
            fig_sc.update_yaxes(title='PM2.5 µg/m³')
            st.plotly_chart(fig_sc, use_container_width=True, config={'displayModeBar': False})
        else:
            st.info("Not enough data for correlation in this window.")

    st.markdown(f'<div style="{_SEC_HDR}">PM2.5 Heatmap — Hour of Day vs Day of Week</div>',
                unsafe_allow_html=True)
    df_h2 = df_area.copy()
    df_h2['hour'] = df_h2['timestamp'].dt.hour
    df_h2['dow']  = df_h2['timestamp'].dt.day_name()
    dow_order = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
    pivot = df_h2.pivot_table(values='pm25', index='dow', columns='hour', aggfunc='mean')
    pivot = pivot.reindex([d for d in dow_order if d in pivot.index])

    if not pivot.empty:
        fig_heat = go.Figure(go.Heatmap(
            z=pivot.values, x=list(range(24)), y=pivot.index.tolist(),
            colorscale=[[0,'#1e293b'],[0.3,'#f97316'],[0.7,'#ef4444'],[1.0,'#7c3aed']],
            hovertemplate='<b>%{y}</b> · Hour %{x}<br>PM2.5: %{z:.1f} µg/m³<extra></extra>',
            colorbar=dict(
                title=dict(text='PM2.5',font=dict(size=10,color='#64748b')),
                tickfont=dict(size=9,color='#64748b'), thickness=10,
            ),
        ))
        theme(fig_heat, height=260)
        fig_heat.update_xaxes(
            title='Hour of day',
            tickvals=list(range(0,24,3)),
            ticktext=[f'{h:02d}:00' for h in range(0,24,3)]
        )
        st.plotly_chart(fig_heat, use_container_width=True, config={'displayModeBar': False})

    st.markdown(f'<div style="{_SEC_HDR}">All-Area Pollutant Snapshot</div>',
                unsafe_allow_html=True)
    tbl = snap[['area_name','aqi','pm25','pm10','no2','o3','co','temperature','humidity']].copy()
    tbl.columns = ['Area','AQI','PM2.5','PM10','NO₂','O₃','CO','Temp °C','Humidity %']
    tbl = tbl.set_index('Area')

    def _c_aqi(v):
        c,_,_ = get_status(int(v)) if pd.notna(v) else ('#fff','','')
        return f'color:{c};font-weight:600;font-family:JetBrains Mono,monospace;'
    def _c_hi(v, thr):
        base = 'font-family:JetBrains Mono,monospace;'
        return ('color:#ef4444;' + base) if (pd.notna(v) and v > thr) else base

    styled = (tbl.style
              .map(_c_aqi, subset=['AQI'])
              .map(lambda v: _c_hi(v,30),  subset=['PM2.5'])
              .map(lambda v: _c_hi(v,60),  subset=['PM10'])
              .map(lambda v: _c_hi(v,40),  subset=['NO₂'])
              .format(na_rep='—', precision=1)
              .set_properties(**{
                  'background-color':'rgba(0,0,0,0)',
                  'border-color':'rgba(255,255,255,0.06)',
                  'color':'#94a3b8','font-size':'0.82rem',
              })
              .set_table_styles([{
                  'selector':'thead th',
                  'props':[
                      ('background-color','rgba(255,255,255,0.04)'),
                      ('color','#64748b'),('font-size','0.7rem'),
                      ('letter-spacing','0.1em'),('text-transform','uppercase'),
                      ('border-bottom','1px solid rgba(255,255,255,0.08)'),
                  ]
              }]))
    st.dataframe(styled, use_container_width=True)