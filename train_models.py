# train_models.py
import pandas as pd
import xgboost as xgb
import joblib
from sqlalchemy import create_engine
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error
import os

# IMPORTANT: Paste your Supabase TRANSACTION POOLER connection string here
SUPABASE_CONNECTION_STRING = "postgresql://postgres.tweplfwxwhspupqazori:ZqVZNkj4NvKCKDik@aws-1-us-east-1.pooler.supabase.com:6543/postgres"

TARGET_COLS = ['aqi', 'pm25', 'pm10', 'temperature', 'humidity']

def create_features(df):
    """Create time-series features from a dataframe."""
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.set_index('timestamp')
    df['hour'] = df.index.hour
    df['day_of_week'] = df.index.dayofweek
    df['month'] = df.index.month
    
    for col in TARGET_COLS:
        if col in df.columns:
            df[f'{col}_lag1'] = df[col].shift(1)
            df[f'{col}_roll_avg3'] = df[col].shift(1).rolling(window=3, min_periods=1).mean()
    
    return df.dropna()

if __name__ == "__main__":
    print("Connecting to cloud database to fetch training data...")
    engine = create_engine(SUPABASE_CONNECTION_STRING)
    df_full = pd.read_sql("SELECT * FROM city_metrics ORDER BY timestamp", engine)

    if len(df_full) < 100:
        print("Not enough data to train. Please wait for your pipeline to collect at least 100 data points.")
    else:
        os.makedirs('models', exist_ok=True)
        for area in df_full['area_name'].unique():
            print(f"\n--- Processing data and training models for {area} ---")
            df_area = df_full[df_full['area_name'] == area].copy()
            df_featured = create_features(df_area)

            if len(df_featured) < 50:
                print(f"Not enough featured data for {area}. Skipping.")
                continue
            
            # --- Train a model for each component ---
            for target_col in TARGET_COLS:
                feature_cols = [
                    'hour', 'day_of_week', 'month',
                    f'{target_col}_lag1', f'{target_col}_roll_avg3'
                ]
                
                # Ensure all required features actually exist in the dataframe
                valid_features = [f for f in feature_cols if f in df_featured.columns]
                if not valid_features or f'{target_col}_lag1' not in valid_features:
                    print(f"Skipping model for '{target_col}' in {area}, not enough features.")
                    continue

                X = df_featured[valid_features]
                y = df_featured[target_col]

                # Split data: 80% for training, 20% for testing. shuffle=False is crucial for time-series.
                X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)
                
                model = xgb.XGBRegressor(objective='reg:squarederror', n_estimators=1000, learning_rate=0.01, n_jobs=-1, early_stopping_rounds=50)
                
                print(f"Training model for {target_col}...")
                model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)
                
                # Test the model and print its performance
                preds = model.predict(X_test)
                rmse = mean_squared_error(y_test, preds, squared=False)
                print(f"-> Model for '{target_col}' trained. Test RMSE: {rmse:.2f}")
                
                model_path = f'models/{area}_{target_col}_model.pkl'
                joblib.dump({'model': model, 'features': valid_features}, model_path)
                print(f"-> Model saved to {model_path}")