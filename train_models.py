import pandas as pd
import numpy as np
import xgboost as xgb
import joblib
import os
import warnings
from datetime import datetime
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error
from sqlalchemy import create_engine

warnings.filterwarnings("ignore")
SUPABASE_CONNECTION_STRING = os.environ.get(
    "SUPABASE_CONNECTION_STRING",
    "postgresql://postgres.tweplfwxwhspupqazori:ZqVZNkj4NvKCKDik@aws-1-us-east-1.pooler.supabase.com:6543/postgres"
)

TARGET_COLS   = ["pm25", "pm10", "temperature", "humidity"]
MIN_RECORDS   = 1000
ACCURACY_GATE = 0.70  

QUARANTINED_AREAS = ["Powai", "Andheri", "Colaba"]

#Feature engineering
def create_features(df_raw: pd.DataFrame) -> tuple:
    df = df_raw.copy()
    
    #datetime is converted to IST
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    if df["timestamp"].dt.tz is None:
        df["timestamp"] = df["timestamp"].dt.tz_localize('UTC')
    df["timestamp"] = df["timestamp"].dt.tz_convert('Asia/Kolkata')
    
    df = df.drop_duplicates(subset=['timestamp', 'area_name'])
    df = df.set_index("timestamp").sort_index()

    # Resample to strict 15-min grid
    df = df.resample('15T').mean(numeric_only=True)
    df = df.interpolate(method='linear', limit=4) 
    
    SPH = 4 

    #hour extracted is accurate to Mumbai local time
    df["hour"]        = df.index.hour
    df["day_of_week"] = df.index.dayofweek
    df["month"]       = df.index.month
    df["is_weekend"]  = (df.index.dayofweek >= 5).astype(int)
    df["hour_sin"]    = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"]    = np.cos(2 * np.pi * df["hour"] / 24)

    for col in TARGET_COLS:
        if col not in df.columns: continue
        s = df[col]
        
        df[f"{col}_lag1"]  = s.shift(1)
        df[f"{col}_lag4"]  = s.shift(4)
        df[f"{col}_lag96"] = s.shift(96)
        
        df[f"{col}_roll_3h"]  = s.shift(1).rolling(window=12, min_periods=1).mean()
        df[f"{col}_roll_24h"] = s.shift(1).rolling(window=96, min_periods=1).mean()

    if "temperature" in df.columns and "humidity" in df.columns:
        df["temp_humidity_idx"] = df["temperature"] * (1 - df["humidity"] / 100)

    df = df.dropna()
    return df, SPH

def build_feature_list(col: str) -> list:
    return [
        "hour", "day_of_week", "month", "is_weekend", "hour_sin", "hour_cos",
        f"{col}_lag1", f"{col}_lag4", f"{col}_lag96",
        f"{col}_roll_3h", f"{col}_roll_24h", "temp_humidity_idx"
    ]

#Training + evaluation
def train_and_evaluate(X: pd.DataFrame, y: pd.Series):
    n = len(X)
    train_idx = int(n * 0.70)
    val_idx = int(n * 0.85)

    X_tr, y_tr = X.iloc[:train_idx], y.iloc[:train_idx]
    X_val, y_val = X.iloc[train_idx:val_idx], y.iloc[train_idx:val_idx]
    X_test, y_test = X.iloc[val_idx:], y.iloc[val_idx:]

    model = xgb.XGBRegressor(
        n_estimators=2500,
        max_depth=6,
        learning_rate=0.01,
        subsample=0.85,
        colsample_bytree=0.8,
        reg_lambda=1.5,
        random_state=42,
        n_jobs=-1,
        early_stopping_rounds=100,
        eval_metric="rmse"
    )

    model.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
    y_pred = model.predict(X_test)
    
    return model, r2_score(y_test, y_pred), mean_absolute_error(y_test, y_pred)

#Main
if __name__ == "__main__":
    print(f"\n{'='*70}\n Mumbai Air Intelligence — Training \n{'='*70}\n")
    engine = create_engine(SUPABASE_CONNECTION_STRING)
    
    #Limit to the last 60 days to prevent server OOM crashes
    query = """
        SELECT * FROM city_metrics 
        WHERE timestamp >= NOW() - INTERVAL '60 days'
        ORDER BY timestamp ASC
    """
    df_full = pd.read_sql(query, engine)
    os.makedirs("models", exist_ok=True)

    # Filter out quarantined areas before processing
    valid_areas = [a for a in df_full["area_name"].unique() if a not in QUARANTINED_AREAS]

    for area in sorted(valid_areas):
        df_area = df_full[df_full["area_name"] == area].copy()
        if len(df_area) < MIN_RECORDS:
            print(f"⏭  {area:<15} — skipping (need {MIN_RECORDS} records).")
            continue

        print(f"📍 Processing {area}...")
        df_feat, SPH = create_features(df_area)

        for col in TARGET_COLS:
            features = [f for f in build_feature_list(col) if f in df_feat.columns]
            X, y = df_feat[features], df_feat[col]

            try:
                model, r2, mae = train_and_evaluate(X, y)
                status = "✅" if r2 >= ACCURACY_GATE else "⚠️ "
                print(f"  {status} {col:<12} R² (Unseen): {r2:.3f} | MAE: {mae:.2f}")

                joblib.dump({
                    "model": model, "features": features, "col": col, 
                    "area": area, "test_r2": r2, "steps_per_hour": SPH
                }, f"models/{area}_{col}_model.pkl")
            except Exception as e:
                print(f"  ✗ {col} failed: {e}")

    print(f"\n{'='*70}\n Done. Models saved to models/\n{'='*70}")