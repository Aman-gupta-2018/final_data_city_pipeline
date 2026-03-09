import pandas as pd
import xgboost as xgb
import joblib, os
from sqlalchemy import create_engine

# Use your actual connection string here for local training
SUPABASE_CONNECTION_STRING = "SUPABASE_CONNECTION_STRING" 
TARGET_COLS = ['pm25', 'temperature', 'humidity']

def create_features(df):
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.set_index('timestamp').resample('1h').mean(numeric_only=True).interpolate(limit=3)
    
    # Matching the exact features expected by the updated app.py
    df['hour'] = df.index.hour
    df['day_of_week'] = df.index.dayofweek
    df['month'] = df.index.month
    
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
        if len(df_area) < 10: continue
            
        for col in TARGET_COLS:
            features = ['hour', 'day_of_week', 'month', f'{col}_lag1', f'{col}_roll_avg3']
            X = df_area[features]
            y = df_area[col]
            
            model = xgb.XGBRegressor(n_estimators=100, max_depth=3, learning_rate=0.05)
            model.fit(X, y)
            joblib.dump({'model': model, 'features': features}, f'models/{area}_{col}_model.pkl')
    print("✅ Training Complete: All models synchronized.")