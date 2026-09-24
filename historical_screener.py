import os
import requests
import zipfile
import io
import time
import pandas as pd
from datetime import datetime, timedelta
from jugaad_data.nse import bhavcopy_save

def fetch_nse_bhavcopy(target_date):
    """Downloads and formats NSE Bhavcopy"""
    try:
        filename = bhavcopy_save(target_date, "./")
        df = pd.read_csv(filename)
        df.columns = df.columns.str.strip()
        
        # Old Format
        if 'SERIES' in df.columns:
            df = df[df['SERIES'] == 'EQ']
            df = df[['SYMBOL', 'CLOSE', 'PREVCLOSE', 'TOTTRDQTY']]
        # New UDiFF Format
        elif 'SctySrs' in df.columns:
            df = df[df['SctySrs'] == 'EQ']
            df = df[['TckrSymb', 'ClsPric', 'PrvsClsgPric', 'TtlTradgVol']]
        else:
            if os.path.exists(filename):
                os.remove(filename)
            return pd.DataFrame()
            
        df.columns = ['Symbol', 'Close', 'Prev_Close', 'Volume']
        df['Exchange'] = 'NSE'
        if os.path.exists(filename):
            os.remove(filename)
        return df
    except Exception:
        return pd.DataFrame()

def fetch_bse_bhavcopy(target_date):
    """Downloads and formats BSE Bhavcopy"""
    date_str = target_date.strftime("%d%m%y")
    url = f"https://www.bseindia.com/download/BhavCopy/Equity/EQ{date_str}_CSV.ZIP"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Accept': 'application/zip, text/html,application/xhtml+xml',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.bseindia.com/markets/MarketInfo/BhavCopy.aspx'
    }
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200 and 'zip' in res.headers.get('Content-Type', '').lower():
            with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                with z.open(z.namelist()[0]) as f:
                    df = pd.read_csv(f)
                    df.columns = df.columns.str.strip()
                    if 'SC_TYPE' in df.columns:
                        df = df[df['SC_TYPE'] == 'Q']
                    df = df[['SC_NAME', 'CLOSE', 'PREVCLOSE', 'NO_OF_SHRS']]
                    df.columns = ['Symbol', 'Close', 'Prev_Close', 'Volume']
                    df['Exchange'] = 'BSE'
                    return df
    except Exception:
        pass
    return pd.DataFrame()

def run_historical_screener(target_date_str):
    target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    print(f"\n[SYSTEM] Running historical screener for Day-31: {target_date}...")
    
    trading_days_data = []
    current_date = target_date
    days_collected = 0
    attempts = 0
    
    while days_collected < 31:
        if attempts > 60:
            print("[ERROR] Could not fetch 31 valid historical trading days.")
            return
            
        nse_df = fetch_nse_bhavcopy(current_date)
        bse_df = fetch_bse_bhavcopy(current_date)
        combined = pd.concat([nse_df, bse_df], ignore_index=True)
        
        if not combined.empty:
            combined['Date'] = current_date
            trading_days_data.append(combined)
            days_collected += 1
            print(f"   -> [{days_collected}/31] Collected data for {current_date}")
            
        current_date -= timedelta(days=1)
        attempts += 1
        time.sleep(0.5)

    master_df = pd.concat(trading_days_data, ignore_index=True)
    master_df['Symbol'] = master_df['Symbol'].str.strip()

    # Separate target day vs previous 30 trading days
    day_31_data = master_df[master_df['Date'] == target_date].copy()
    history_data = master_df[master_df['Date'] < target_date].copy()

    # Calculate 30-day baseline average volume
    avg_vol_df = history_data.groupby(['Symbol', 'Exchange'])['Volume'].mean().reset_index()
    avg_vol_df.rename(columns={'Volume': '30D_Avg_Volume'}, inplace=True)

    analysis_df = pd.merge(day_31_data, avg_vol_df, on=['Symbol', 'Exchange'], how='inner')
    analysis_df['Volume_Multiple'] = (analysis_df['Volume'] / analysis_df['30D_Avg_Volume']).round(2)
    analysis_df['Price_Change_Pct'] = (((analysis_df['Close'] - analysis_df['Prev_Close']) / analysis_df['Prev_Close']) * 100).round(2)

    # Filter: Volume >= 2x AND 2.0% <= Price Change <= 3.99%
    flagged = analysis_df[
        (analysis_df['Volume_Multiple'] >= 2.0) &
        (analysis_df['Price_Change_Pct'] >= 2.0) &
        (analysis_df['Price_Change_Pct'] <= 3.99)
    ].copy()

    flagged = flagged[['Symbol', 'Exchange', 'Close', 'Price_Change_Pct', 'Volume', '30D_Avg_Volume', 'Volume_Multiple']]
    flagged = flagged.sort_values(by='Volume_Multiple', ascending=False)

    out_file = f"flagged_stocks_{target_date_str}.csv"
    flagged.to_csv(out_file, index=False)
    print(f"\n✅ Completed! Found {len(flagged)} flagged companies for {target_date_str}.")
    print(f"📁 Saved report to: {out_file}")

if __name__ == "__main__":
    date_input = input("Enter target date (YYYY-MM-DD) [e.g., 2026-07-24]: ").strip()
    if not date_input:
        date_input = "2026-07-24"
    run_historical_screener(date_input)