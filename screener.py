import os
import smtplib
import requests
import zipfile
import io
import time
import pandas as pd
from datetime import date, timedelta
from jugaad_data.nse import bhavcopy_save
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

def fetch_nse_bhavcopy(target_date):
    """Downloads and formats NSE Bhavcopy"""
    try:
        filename = bhavcopy_save(target_date, "./")
        df = pd.read_csv(filename)
        # Keep only standard Equities (EQ)
        df = df[df['SERIES'] == 'EQ']
        df = df[['SYMBOL', 'CLOSE', 'PREVCLOSE', 'TOTTRDQTY']]
        df.columns = ['Symbol', 'Close', 'Prev_Close', 'Volume']
        df['Exchange'] = 'NSE'
        os.remove(filename) # Clean up file
        return df
    except Exception:
        return pd.DataFrame()

def fetch_bse_bhavcopy(target_date):
    """Downloads and formats BSE Bhavcopy directly from their servers"""
    date_str = target_date.strftime("%d%m%y")
    url = f"https://www.bseindia.com/download/BhavCopy/Equity/EQ{date_str}_CSV.ZIP"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                with z.open(z.namelist()[0]) as f:
                    df = pd.read_csv(f)
                    df.columns = df.columns.str.strip()
                    # Filter for standard Equity (Q)
                    if 'SC_TYPE' in df.columns:
                        df = df[df['SC_TYPE'] == 'Q']
                    df = df[['SC_NAME', 'CLOSE', 'PREVCLOSE', 'NO_OF_SHRS']]
                    df.columns = ['Symbol', 'Close', 'Prev_Close', 'Volume']
                    df['Exchange'] = 'BSE'
                    return df
    except Exception:
        pass
    return pd.DataFrame()

def run_screener():
    print("[SYSTEM] Booting Quantitative Screener...")
    
    trading_days_data = []
    current_date = date.today()
    days_collected = 0
    
    # Go back in time until we find exactly 31 valid trading days (skipping weekends/holidays)
    print("[SYSTEM] Fetching 31 days of historical Bhavcopy data for NSE & BSE. This may take 2 minutes...")
    while days_collected < 31:
        # Fetch data for this specific date
        nse_df = fetch_nse_bhavcopy(current_date)
        bse_df = fetch_bse_bhavcopy(current_date)
        
        combined_daily_df = pd.concat([nse_df, bse_df], ignore_index=True)
        
        if not combined_daily_df.empty:
            combined_daily_df['Date'] = current_date
            trading_days_data.append(combined_daily_df)
            days_collected += 1
            print(f"   -> Fetched Market Data for {current_date} ({len(combined_daily_df)} companies)")
            
        current_date -= timedelta(days=1)
        time.sleep(1) # Being polite to the exchange servers
        
    # Combine all 31 days into one massive dataset
    master_df = pd.concat(trading_days_data, ignore_index=True)
    master_df['Symbol'] = master_df['Symbol'].str.strip()
    
    print("[SYSTEM] Data aggregated. Running mathematical filters...")
    
    # 1. Separate Today's Data (Day 31) vs History (Past 30 Days)
    today_date = master_df['Date'].max()
    today_data = master_df[master_df['Date'] == today_date].copy()
    historical_data = master_df[master_df['Date'] < today_date].copy()
    
    # 2. Calculate the 30-Day Average Volume for each company
    avg_vol_df = historical_data.groupby(['Symbol', 'Exchange'])['Volume'].mean().reset_index()
    avg_vol_df.rename(columns={'Volume': '30D_Avg_Volume'}, inplace=True)
    
    # 3. Merge Today's Data with the 30-Day Averages
    analysis_df = pd.merge(today_data, avg_vol_df, on=['Symbol', 'Exchange'], how='inner')
    
    # 4. CALCULATE CRITERIA
    # Volume Multiple (Today vs 30D Avg)
    analysis_df['Volume_Multiple'] = (analysis_df['Volume'] / analysis_df['30D_Avg_Volume']).round(2)
    # Price Change % (Today's Close vs Yesterday's Close)
    analysis_df['Price_Change_Pct'] = (((analysis_df['Close'] - analysis_df['Prev_Close']) / analysis_df['Prev_Close']) * 100).round(2)
    
    # 5. THE SCREENER FILTERS: 
    # Must have >= 2x volume AND price change between 2% and 3.99%
    flagged = analysis_df[
        (analysis_df['Volume_Multiple'] >= 2.0) & 
        (analysis_df['Price_Change_Pct'] >= 2.0) & 
        (analysis_df['Price_Change_Pct'] <= 3.99)
    ].copy()
    
    # Clean up the final output table
    flagged = flagged[['Symbol', 'Exchange', 'Close', 'Price_Change_Pct', 'Volume', '30D_Avg_Volume', 'Volume_Multiple']]
    flagged = flagged.sort_values(by='Volume_Multiple', ascending=False)
    
    output_filename = "flagged_stocks.csv"
    flagged.to_csv(output_filename, index=False)
    print(f"[SYSTEM] Screener Complete! Flagged {len(flagged)} breakout stocks.")
    
    send_email(output_filename, len(flagged), today_date)

def send_email(attachment_path, stock_count, run_date):
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")
    recipient_email = os.getenv("RECIPIENT_EMAIL")

    if not (sender_email and sender_password and recipient_email):
        print("[WARNING] Email secrets not configured. Exiting.")
        return

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = f" Daily Screener Report by Sam - {run_date} ({stock_count} Stocks Flagged)"

    body = f"Hello,\n\nMarket analysis is complete for {run_date}.\n\nThe screener analyzed roughly 7,000 active Indian equities across both the NSE and BSE. It found {stock_count} companies today that experienced a 2x+ Volume Breakout while maintaining a tight 2-3% upward price action.\n\nThe detailed CSV is attached.\n\nBest regards,\n Sameer 'Sam'"
    msg.attach(MIMEText(body, 'plain'))

    with open(attachment_path, "rb") as attachment:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(attachment.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(attachment_path)}")
    msg.attach(part)

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
    print("[SYSTEM] Email dispatched.")

if __name__ == "__main__":
    run_screener()
