import pandas as pd
import xgboost as xgb
import joblib, os
from sqlalchemy import create_engine

SUPABASE_CONNECTION_STRING = "postgresql://postgres.tweplfwxwhspupqazori:ZqVZNkj4NvKCKDik@aws-1-us-east-1.pooler.supabase.com:6543/postgres"
TARGET_COLS = ['pm25', 'temperature', 'humidity']

def create_features(df):
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.set_index('timestamp').resample('1h').mean(numeric_only=True).interpolate(limit=3)
    df['hour'] = df.index.hour
    df['day_of_week'] = df.index.dayofweek
    for col in TARGET_COLS:
        df[f'{col}_lag1'] = df[col].shift(1)
        df[f'{col}_roll_avg3'] = df[col].shift(1).rolling(window=3).mean()
    return df.dropna()

if __name__ == "__main__":
    engine = create_engine(SUPABASE_CONNECTION_STRING)
    df_full = pd.read_sql("SELECT * FROM city_metrics ORDER BY timestamp ASC", engine)
    os.makedirs('models', exist_ok=True)
    for area in df_full['area_name'].unique():
        df_area = create_features(df_full[df_full['area_name'] == area].copy())
        if len(df_area) < 5: continue
        for col in TARGET_COLS:
            features = ['hour', 'day_of_week', f'{col}_lag1', f'{col}_roll_avg3']
            model = xgb.XGBRegressor(n_estimators=100, max_depth=3)
            model.fit(df_area[features], df_area[col])
            joblib.dump({'model': model, 'features': features}, f'models/{area}_{col}_model.pkl')