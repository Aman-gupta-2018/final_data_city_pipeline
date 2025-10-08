# app.py
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import plotly.express as px

st.set_page_config(page_title="Mumbai Smart City Dashboard", layout="wide")

# This function connects to your Supabase DB and fetches the data
@st.cache_data(ttl=600) # Cache the data for 10 minutes
def fetch_data():
    engine = create_engine(st.secrets["SUPABASE_CONNECTION_STRING"])
    # Fetch the most recent 1000 records to keep the dashboard fast
    df = pd.read_sql("SELECT * FROM city_metrics ORDER BY timestamp DESC LIMIT 1000", engine, parse_dates=['timestamp'])
    # Convert timestamp to your local time (IST)
    df['timestamp'] = df['timestamp'].dt.tz_convert('Asia/Kolkata')
    return df

# --- Main App ---
try:
    df = fetch_data()
    st.title("🏙️ Mumbai Smart City Dashboard")

    # Create a dropdown menu to select a location
    locations = df['area_name'].unique()
    selected_location = st.selectbox("Select a Location", locations)

    # Filter the data for the selected location
    df_location = df[df['area_name'] == selected_location].sort_values('timestamp', ascending=False)

    if df_location.empty:
        st.warning("No data available for this location yet.")
    else:
        latest_data = df_location.iloc[0]

        # --- Display Live Metrics ---
        st.header(f"Live Metrics for {selected_location}")
        cols = st.columns(4)
        cols[0].metric("Temperature", f"{latest_data['temperature']:.1f}°C")
        cols[1].metric("Humidity", f"{latest_data['humidity']:.0f}%")
        cols[2].metric("AQI", f"{latest_data['aqi']:.0f}")
        cols[3].metric("PM2.5", f"{latest_data['pm25']:.1f} µg/m³")

        # --- Display Historical Charts ---
        st.header("Historical Data (Recent)")

        # Filter data for the last 24 hours from the fetched data
        last_24h_df = df_location[df_location['timestamp'] >= (df_location['timestamp'].max() - pd.Timedelta(hours=24))]

        # Create a dropdown to select which metric to graph
        component_to_graph = st.selectbox("Select Metric to Graph", ['aqi', 'pm25', 'pm10', 'temperature', 'humidity', 'no2', 'o3', 'co'])

        # Create the bar chart
        fig = px.bar(
            last_24h_df, 
            x='timestamp', 
            y=component_to_graph, 
            title=f"{component_to_graph.upper()} over the Last 24 Hours"
        )
        st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"An error occurred. Please check your database connection and secrets. Error: {e}")