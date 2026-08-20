import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import os
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from jugaad_data.nse import stock_df

# --- MAC BUG FIX ---
original_makedirs = os.makedirs
def safe_makedirs(*args, **kwargs):
    kwargs['exist_ok'] = True
    return original_makedirs(*args, **kwargs)
os.makedirs = safe_makedirs

# --- UI CONFIGURATION ---
st.set_page_config(page_title="Stock Data Generator", page_icon="📈")
st.title("📈 Automated Stock Data Generator by Sameer")
st.write("Generate historical reports and check latest corporate filings.")

# --- DISPLAYING FLAGGED COMPANIES ---
st.header("🎯 Daily Flagged Companies")
if os.path.exists("flagged_stocks.csv"):
    flagged_df = pd.read_csv("flagged_stocks.csv")
    st.dataframe(flagged_df, use_container_width=True)
else:
    st.info("No flagged data generated yet. Run the daily screener to populate results.")


# --- USER INPUT ---
symbol = st.text_input("Enter NSE Symbol (e.g., HDFCBANK, TCS, INFY):").strip().upper()

# --- PROMOTER HOLDING BUTTON ---
if st.button("🔍 Check Latest Promoter Holding"):
    if symbol:
        with st.spinner(f"Fetching corporate filings for {symbol}..."):
            try:
                # yfinance requires '.NS' appended for Indian NSE stocks
                ticker = yf.Ticker(f"{symbol}.NS")
                info = ticker.info
                
                # Extract insider/promoter holding percentage
                promoter_pct = info.get('heldPercentInsiders', 0) * 100
                
                if promoter_pct > 0:
                    st.success(f"**Latest Promoter Holding for {symbol}:** {promoter_pct:.2f}%")
                    st.info("Note: This data reflects the most recently declared quarterly filing.")
                else:
                    st.warning("Could not find declared promoter holding for this symbol.")
            except Exception as e:
                st.error("Error fetching filing data. Check the symbol.")
    else:
        st.warning("Please enter a symbol first.")

st.divider()

# --- CSV GENERATOR BUTTON ---
if st.button("📊 Update & Generate CSV Data"):
    if symbol:
        filename = f"{symbol}_Master_Report.csv" 
        end_date = date.today()
        is_update = False
        
        with st.spinner("Processing data pipeline..."):
            # 1. Check for existing database
            if os.path.exists(filename):
                existing_df = pd.read_csv(filename)
                
                # Strip out any old bad times and enforce pure dates
                existing_df['Date'] = pd.to_datetime(existing_df['Date']).dt.date
                last_recorded_date = existing_df['Date'].max()
                
                if last_recorded_date >= end_date:
                    st.success(f"✅ {symbol} is already up to date (Latest: {last_recorded_date}).")
                    st.stop()
                    
                start_date = last_recorded_date + timedelta(days=1)
                st.info(f"Updating missing days: {start_date} to {end_date}")
                is_update = True
            else:
                start_date = end_date - relativedelta(years=10)
                st.info(f"No existing file found. Fetching full 10-year history...")
                existing_df = pd.DataFrame()

            try:
                # 2. Fetch new data
                raw_df = stock_df(symbol=symbol, from_date=start_date, to_date=end_date, series="EQ")
                
                if raw_df.empty:
                    st.success("✅ No new trading days to add.")
                else:
                    # 3. Process metrics
                    raw_df['DAILY_MEAN'] = (raw_df['HIGH'] + raw_df['LOW'] + raw_df['CLOSE']) / 3
                    delivery_col = '% DLY QT TO TRADED QTY'
                    delivery_data = raw_df[delivery_col] if delivery_col in raw_df.columns else "N/A"
                    
                    # Fix the Timezone glitch causing Sunday dates
                    raw_dates = pd.to_datetime(raw_df['DATE']).dt.tz_localize(None)
                    corrected_dates = (raw_dates + pd.Timedelta(hours=5, minutes=30)).dt.date
                    
                    new_df = pd.DataFrame({
                        'Date': corrected_dates,
                        'Opening Share Price': raw_df['OPEN'],
                        'Closing Share Price': raw_df['CLOSE'],
                        'Daily Mean Share Price': raw_df['DAILY_MEAN'].round(2), 
                        'Daily Trading Volume': raw_df['VOLUME'],
                        'Daily Delivery Percentage': delivery_data
                    })
                    
                    # 4. Merge Data
                    if is_update:
                        final_df = pd.concat([existing_df, new_df], ignore_index=True)
                    else:
                        final_df = new_df
                        
                    final_df = final_df.drop_duplicates(subset=['Date'])
                    final_df = final_df.sort_values(by='Date')
                    
                    # 5. Calculate On-Balance Volume (OBV)
                    price_change = final_df['Closing Share Price'].diff()
                    direction = np.sign(price_change).fillna(0)
                    final_df['OBV'] = (direction * final_df['Daily Trading Volume']).cumsum()
                    
                    # 6. Export and Display
                    final_df.to_csv(filename, index=False)
                    st.success(f"✅ Master file updated! Added {len(new_df)} new trading days.")
                    
                    csv_data = final_df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="⬇️ Download Latest CSV",
                        data=csv_data,
                        file_name=filename,
                        mime='text/csv',
                    )
            except Exception as e:
                st.error(f"❌ Error fetching data: {e}")
    else:
        st.warning("Please enter a symbol first.")


st.divider()  # Adds a clean horizontal line separator before the footer
st.caption("Made by Sameer Akhtar | Data sourced from NSE & Yahoo Finance")