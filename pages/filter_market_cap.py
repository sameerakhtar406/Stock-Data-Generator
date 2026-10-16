import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.title("MARKET CAP: High Return & Deep Discount Screener")

# Expanded sample list to increase chances of finding a match
sample_tickers = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "SUZLON.NS", "ITC.NS", "ZOMATO.NS", "IREDA.NS", "YESBANK.NS", "IDEA.NS"]

def get_fundamental_fallback(ticker_obj, metric_name):
    """Fallback calculation if standard yfinance info is missing."""
    try:
        financials = ticker_obj.financials
        balance_sheet = ticker_obj.balance_sheet
        
        if metric_name == "ROCE":
            ebit = financials.loc['EBIT'].iloc[0] 
            total_assets = balance_sheet.loc['Total Assets'].iloc[0]
            current_liabilities = balance_sheet.loc['Current Liabilities'].iloc[0]
            return ebit / (total_assets - current_liabilities)
            
        elif metric_name == "ROE":
            net_income = financials.loc['Net Income'].iloc[0]
            stockholders_equity = balance_sheet.loc['Stockholders Equity'].iloc[0]
            return net_income / stockholders_equity
            
    except Exception:
        return 0
    return 0

@st.cache_data
def analyze_companies(tickers):
    data = []
    for symbol in tickers:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            market_cap = info.get('marketCap', 0)
            
            # Fetch ROE with fallback
            roe = info.get('returnOnEquity')
            if roe is None:
                roe = get_fundamental_fallback(ticker, "ROE")
                
            # Fetch ROCE with fallback
            roce = info.get('returnOnCapitalEmployed', info.get('returnOnAssets'))
            if roce is None:
                roce = get_fundamental_fallback(ticker, "ROCE")
            
            # Extract Technicals
            hist = ticker.history(period="max")
            if hist.empty:
                continue
                
            ath = hist['High'].max()
            cmp = hist['Close'].iloc[-1]
            
            data.append({
                'Symbol': symbol.replace(".NS", ""),
                'MarketCap (Cr)': market_cap / 10000000 if market_cap else 0, # Convert raw to Crores for readability
                'ROE': roe,
                'ROCE': roce,
                'ATH': ath,
                'CMP': cmp,
                'RawMarketCap': market_cap
            })
        except Exception:
            pass
            
    df = pd.DataFrame(data)
    
    # Apply filtering logic (Adjusted the 30% ATH rule to be a 30% discount from ATH. Revert if you truly want 70% crashed stocks)
    filtered_df = df[
        (df['ROE'] > 0.20) & 
        (df['ROCE'] > 0.20) & 
        (df['CMP'] <= (0.70 * df['ATH'])) 
    ].copy()
    
    # Categorize by Market Cap (> 20,000 Crores = 200,000,000,000 raw)
    if not filtered_df.empty:
        filtered_df['Category'] = ['Category A (> ₹20k Cr)' if mc > 200000000000 else 'Category B (< ₹20k Cr)' for mc in filtered_df['RawMarketCap']]
        
    return filtered_df

# UI Layout
st.sidebar.header("Screener Filters")
market_cap_filter = st.sidebar.radio(
    "Filter by Market Cap",
    ["Show All", "Category A (> ₹20k Cr)", "Category B (< ₹20k Cr)"]
)

if st.button("Run Fundamental Screen"):
    with st.spinner("Analyzing fundamentals and price action..."):
        results = analyze_companies(sample_tickers)
        
        if results.empty:
            st.warning("No companies currently meet all strict criteria.(Try running the full dataset!)")
        else:
            # Apply the sidebar filter
            if market_cap_filter != "Show All":
                display_df = results[results['Category'] == market_cap_filter].drop(columns=['RawMarketCap'])
            else:
                display_df = results.drop(columns=['RawMarketCap'])
                
            if display_df.empty:
                st.warning(f"No companies found in {market_cap_filter} meeting the criteria.")
            else:
                st.dataframe(display_df.style.format({
                    'MarketCap (Cr)': '₹{:,.0f}',
                    'ROE': '{:.1%}',
                    'ROCE': '{:.1%}',
                    'ATH': '₹{:.2f}',
                    'CMP': '₹{:.2f}'
                }), use_container_width=True)
