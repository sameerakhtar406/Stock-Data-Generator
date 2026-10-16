import yfinance as yf
import pandas as pd
import time
import logging

# Set up basic logging so you can monitor progress in GitHub Actions logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

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

def get_master_ticker_list():
    """
    TODO: Insert your logic here to pull the 7,000+ NSE/BSE tickers.
    You can read from a CSV or fetch via an API exactly as you do in `screener.py`.
    Make sure the symbols have the '.NS' suffix for yfinance (e.g., 'RELIANCE.NS').
    """
    # Placeholder array - replace this with your actual full list extraction!
    return ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "SUZLON.NS", "ITC.NS", "ZOMATO.NS", "IREDA.NS", "YESBANK.NS"]

def run_screener():
    tickers = get_master_ticker_list()
    logging.info(f"Starting fundamental screen for {len(tickers)} stocks...")
    
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
                
                data.append({
                    'Symbol': symbol.replace(".NS", ""),
                    'MarketCap (Cr)': market_cap / 10000000 if market_cap else 0, 
                    'ROE': roe,
                    'ROCE': roce,
                    'ATH': ath,
                    'CMP': cmp,
                    'RawMarketCap': market_cap
                })
        except Exception as e:
            # Silently pass errors for individual tickers so the loop doesn't crash
            pass
            
        # Log progress every 500 stocks to prevent GitHub Actions log flooding
        if (i + 1) % 500 == 0:
            logging.info(f"Processed {i + 1}/{len(tickers)} stocks...")
            
        # Crucial: Sleep briefly to avoid getting IP-banned by Yahoo Finance during a 7,000 ticker pull
        time.sleep(0.2)
            
    df = pd.DataFrame(data)
    
    if df.empty:
        logging.warning("No data retrieved from yfinance.")
        # Create an empty DataFrame with the required columns so Streamlit doesn't break
        df = pd.DataFrame(columns=['Symbol', 'MarketCap (Cr)', 'ROE', 'ROCE', 'ATH', 'CMP', 'RawMarketCap', 'Category'])
        df.to_csv("market_cap_results.csv", index=False)
        return

    # EXACT BROKER CRITERIA: ROE/ROCE > 20% AND CMP is <= 70% of ATH
    filtered_df = df[
        (df['ROE'] > 0.20) & 
        (df['ROCE'] > 0.20) & 
        (df['CMP'] <= (0.70 * df['ATH'])) 
    ].copy()
    
    if not filtered_df.empty:
        filtered_df['Category'] = ['Category A (> ₹20k Cr)' if mc > 200000000000 else 'Category B (< ₹20k Cr)' for mc in filtered_df['RawMarketCap']]
    
    # Save the static file for Streamlit to read
    filtered_df.to_csv("market_cap_results.csv", index=False)
    logging.info(f"Screener complete. Found {len(filtered_df)} stocks meeting criteria. Saved to market_cap_results.csv")

if __name__ == "__main__":
    run_screener()
