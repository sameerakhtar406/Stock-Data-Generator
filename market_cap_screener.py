import yfinance as yf
import pandas as pd
import time
import logging
import os
import requests
import zipfile
import io
from datetime import date, timedelta
from jugaad_data.nse import bhavcopy_save

# Logging for GitHub Actions
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def fetch_nse_bhavcopy(target_date):
    """Downloads and formats NSE Bhavcopy"""
    try:
        filename = bhavcopy_save(target_date, "./")
        df = pd.read_csv(filename)
        df.columns = df.columns.str.strip() 
        
        # 1. Handle Old Format
        if 'SERIES' in df.columns:
            df = df[df['SERIES'] == 'EQ']
            df = df[['SYMBOL', 'CLOSE', 'PREVCLOSE', 'TOTTRDQTY']]
            
        # 2. Handle New UDiFF Format (Corrected Columns)
        elif 'SctySrs' in df.columns:
            df = df[df['SctySrs'] == 'EQ']
            df = df[['TckrSymb', 'ClsPric', 'PrvsClsgPric', 'TtlTradgVol']]
            
        else:
            logging.warning(f"[NSE WARNING] Unrecognized columns for {target_date}: {df.columns.tolist()[:5]}")
            os.remove(filename)
            return pd.DataFrame()
            
        df.columns = ['Symbol', 'Close', 'Prev_Close', 'Volume']
        df['Exchange'] = 'NSE'
        os.remove(filename) 
        return df
    except Exception as e:
        return pd.DataFrame()

def fetch_bse_bhavcopy(target_date):
    """Downloads and formats BSE Bhavcopy with Stealth Headers"""
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
    except Exception as e:
        pass 
        
    return pd.DataFrame()

def get_master_ticker_list():
    """Finds the most recent trading day and fetches both NSE and BSE symbols."""
    target_date = date.today()
    combined_df = pd.DataFrame()
    
    # Looking back up to 5 days to find the most recent active trading day
    for _ in range(5):
        if target_date.weekday() < 5:  # Monday to Friday
            nse_df = fetch_nse_bhavcopy(target_date)
            bse_df = fetch_bse_bhavcopy(target_date)
            
            combined_df = pd.concat([nse_df, bse_df], ignore_index=True)
            if not combined_df.empty:
                logging.info(f"Successfully fetched {len(combined_df)} master tickers for {target_date}")
                break
        target_date -= timedelta(days=1)
        
    if combined_df.empty:
        logging.error("Failed to fetch market data for the past 5 days.")
        return []

    # Format symbols for Yahoo Finance API
    yf_symbols = []
    for _, row in combined_df.iterrows():
        raw_sym = str(row['Symbol']).strip()
        if row['Exchange'] == 'NSE':
            yf_symbols.append(f"{raw_sym}.NS")
        elif row['Exchange'] == 'BSE':
            yf_symbols.append(f"{raw_sym}.BO")
            
    return yf_symbols

def get_fundamental_fallback(ticker_obj, metric_name):
    """Fallback calculation if standard yfinance info is missing."""
    try:
        financials = ticker_obj.financials
        balance_sheet = ticker_obj.balance_sheet
        
        if financials.empty or balance_sheet.empty:
            return 0
            
        if metric_name == "ROCE":
            ebit = financials.loc['EBIT'].iloc[0] 
            total_assets = balance_sheet.loc['Total Assets'].iloc[0]
            current_liabilities = balance_sheet.loc['Current Liabilities'].iloc[0]
            if (total_assets - current_liabilities) == 0:
                return 0
            return ebit / (total_assets - current_liabilities)
            
        elif metric_name == "ROE":
            net_income = financials.loc['Net Income'].iloc[0]
            stockholders_equity = balance_sheet.loc['Stockholders Equity'].iloc[0]
            if stockholders_equity == 0:
                return 0
            return net_income / stockholders_equity
    except Exception:
        return 0
    return 0

def run_screener():
    tickers = get_master_ticker_list()
    if not tickers:
        return
        
    logging.info(f"Starting fundamental screen for {len(tickers)} combined NSE/BSE stocks...")
    
    data = []
    
    for i, symbol in enumerate(tickers):
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            market_cap = info.get('marketCap', 0)
            
            roe = info.get('returnOnEquity')
            if roe is None:
                roe = get_fundamental_fallback(ticker, "ROE")
                
            roce = info.get('returnOnCapitalEmployed', info.get('returnOnAssets'))
            if roce is None:
                roce = get_fundamental_fallback(ticker, "ROCE")
            
            hist = ticker.history(period="max")
            if not hist.empty:
                ath = hist['High'].max()
                cmp = hist['Close'].iloc[-1]
                
                # Determining original symbol and exchange for output display
                clean_symbol = symbol.replace(".NS", "").replace(".BO", "")
                exchange_label = "NSE" if ".NS" in symbol else "BSE"
                
                data.append({
                    'Exchange': exchange_label,
                    'Symbol': clean_symbol,
                    'MarketCap (Cr)': market_cap / 10000000 if market_cap else 0, 
                    'ROE': roe,
                    'ROCE': roce,
                    'ATH': ath,
                    'CMP': cmp,
                    'RawMarketCap': market_cap
                })
        except Exception:
            pass
            
        if (i + 1) % 200 == 0:
            logging.info(f"Processed {i + 1}/{len(tickers)} stocks...")
            
        # Crucial delay to prevent Yahoo Finance IP ban
        time.sleep(0.2)
            
    df = pd.DataFrame(data)
    
    if df.empty:
        logging.warning("No fundamental data successfully retrieved from yfinance.")
        df = pd.DataFrame(columns=['Exchange', 'Symbol', 'MarketCap (Cr)', 'ROE', 'ROCE', 'ATH', 'CMP', 'RawMarketCap', 'Category'])
        df.to_csv("market_cap_results.csv", index=False)
        return

    # EXACT FILTRATION CRITERIA (CMP<=ATH)
    filtered_df = df[
        (df['ROE'] > 0.20) & 
        (df['ROCE'] > 0.20) & 
        (df['CMP'] <= (0.70 * df['ATH'])) 
    ].copy()
    
    if not filtered_df.empty:
        filtered_df['Category'] = ['Category A (> ₹20k Cr)' if mc > 200000000000 else 'Category B (< ₹20k Cr)' for mc in filtered_df['RawMarketCap']]
    
    filtered_df.to_csv("market_cap_results.csv", index=False)
    logging.info(f"Screener complete. Found {len(filtered_df)} stocks meeting criteria. Saved to market_cap_results.csv")

if __name__ == "__main__":
    run_screener()
