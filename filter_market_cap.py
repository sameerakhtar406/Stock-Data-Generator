import streamlit as st
import yfinance as yf
import pandas as pd

st.title("🎯 High Return & Deep Discount Screener")

# A small sample list for the UI. (Running 7,000 live will time out!)
sample_tickers = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "SUZLON.NS"]

@st.cache_data
def analyze_companies(tickers):
    data = []
    for symbol in tickers:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            # Extract Fundamentals
            market_cap = info.get('marketCap', 0)
            roe = info.get('returnOnEquity', 0)
            # ROCE is sometimes missing from standard API returns, so we fall back to ROA if needed
            roce = info.get('returnOnCapitalEmployed', info.get('returnOnAssets', 0))
            
            # Extract Technicals
            hist = ticker.history(period="max")
            if hist.empty:
                continue
                
            ath = hist['High'].max()
            cmp = hist['Close'].iloc[-1]
            
            data.append({
                'Symbol': symbol.replace(".NS", ""),
                'MarketCap': market_cap,
                'ROE': roe,
                'ROCE': roce,
                'ATH': ath,
                'CMP': cmp
            })
        except Exception:
            pass
            
    df = pd.DataFrame(data)
    
    # 1. Apply filtering logic
    filtered_df = df[
        (df['ROE'] > 0.20) & 
        (df['ROCE'] > 0.20) & 
        (df['CMP'] <= (0.30 * df['ATH']))
    ].copy()
    
    # 2. Categorize by Market Cap
    if not filtered_df.empty:
        filtered_df['Category'] = ['A (> ₹20k Cr)' if mc > 200000000000 else 'B (< ₹20k Cr)' for mc in filtered_df['MarketCap']]
        
    return filtered_df

if st.button("Run Fundamental Screen"):
    with st.spinner("Analyzing fundamentals and price action..."):
        results = analyze_companies(sample_tickers)
        
        if results.empty:
            st.warning("No companies currently meet all strict criteria.")
        else:
            cat_a = results[results['Category'] == 'A (> ₹20k Cr)']
            cat_b = results[results['Category'] == 'B (< ₹20k Cr)']
            
            # Use Streamlit tabs to cleanly separate Category A and Category B in the UI
            tab1, tab2 = st.tabs(["Category A (> ₹20k Cr)", "Category B (< ₹20k Cr)"])
            
            with tab1:
                st.dataframe(cat_a, use_container_width=True)
            with tab2:
                st.dataframe(cat_b, use_container_width=True)