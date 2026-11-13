import os
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
from jugaad_data.nse import stock_df

# --- MAC BUG FIX ---
original_makedirs = os.makedirs
def safe_makedirs(*args, **kwargs):
    kwargs["exist_ok"] = True
    return original_makedirs(*args, **kwargs)
os.makedirs = safe_makedirs

# --- HEADER ---
st.title("📈 Automated Stock Data Generator")
st.caption("Daily NSE/BSE breakout alerts, promoter holding filings, and 10-year historical CSV exports.")

# --- ORGANIZE INTO TWO CLEAN TABS ---
tab_daily, tab_lookup = st.tabs([
    "🎯 Daily Flagged Companies",
    "🔍 Single-Stock Lookup & CSV Export"
])

# ==========================================
# TAB 1: DAILY FLAGGED COMPANIES
# ==========================================
with tab_daily:
    if os.path.exists("flagged_stocks.csv"):
        flagged_df = pd.read_csv("flagged_stocks.csv")

        if flagged_df.empty:
            st.info("The daily screener ran, but 0 companies met the breakout criteria today.")
        else:
            # Summary KPIs + Exchange Filter
            col_m1, col_m2, col_m3, col_filter = st.columns([1, 1, 1, 1.2])
            with col_m1:
                st.metric("Flagged Stocks", len(flagged_df))
            with col_m2:
                max_vol = flagged_df["Volume_Multiple"].max() if "Volume_Multiple" in flagged_df.columns else 0
                st.metric("Peak Volume Multiple", f"{max_vol:.2f}x")
            with col_m3:
                max_gain = flagged_df["Price_Change_Pct"].max() if "Price_Change_Pct" in flagged_df.columns else 0
                st.metric("Top Price Move", f"+{max_gain:.2f}%")
            with col_filter:
                exchanges = ["All"] + sorted(flagged_df["Exchange"].dropna().unique().tolist()) if "Exchange" in flagged_df.columns else ["All"]
                selected_exchange = st.selectbox("Filter Exchange", exchanges)

            display_df = flagged_df if selected_exchange == "All" else flagged_df[flagged_df["Exchange"] == selected_exchange]
            st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info("No flagged data generated yet. Run the daily screener workflow to populate results.")

# ==========================================
# TAB 2: SINGLE-STOCK TOOLS
# ==========================================
with tab_lookup:
    symbol = st.text_input(
        "Enter NSE Symbol",
        placeholder="e.g., HDFCBANK, TCS, INFY"
    ).strip().upper()

    col_promoter, col_csv = st.columns(2)

    # --- LEFT COLUMN: PROMOTER HOLDING ---
    with col_promoter:
        st.subheader("🏢 Corporate Filings")
        st.write("Check the most recently declared quarterly insider/promoter shareholding.")
        if st.button("🔍 Check Latest Promoter Holding", use_container_width=True):
            if symbol:
                with st.spinner(f"Fetching corporate filings for {symbol}..."):
                    try:
                        ticker = yf.Ticker(f"{symbol}.NS")
                        info = ticker.info
                        promoter_pct = info.get("heldPercentInsiders", 0) * 100

                        if promoter_pct > 0:
                            st.success(f"**Latest Promoter Holding ({symbol}):** {promoter_pct:.2f}%")
                            st.caption("Reflects the most recently declared quarterly filing.")
                        else:
                            st.warning("Could not find declared promoter holding for this symbol.")
                    except Exception:
                        st.error("Error fetching filing data. Verify the NSE symbol.")
            else:
                st.warning("Please enter an NSE symbol above first.")

    # --- RIGHT COLUMN: 10-YEAR CSV GENERATOR ---
    with col_csv:
        st.subheader("📊 Historical Price & OBV Report")
        st.write("Generate or incrementally update a 10-year daily price, delivery, and OBV dataset.")
        if st.button("📊 Update & Generate CSV Data", type="primary", use_container_width=True):
            if symbol:
                filename = f"{symbol}_Master_Report.csv"
                end_date = date.today()
                is_update = False

                with st.spinner("Processing data pipeline..."):
                    if os.path.exists(filename):
                        existing_df = pd.read_csv(filename)
                        existing_df["Date"] = pd.to_datetime(existing_df["Date"]).dt.date
                        last_recorded_date = existing_df["Date"].max()

                        if last_recorded_date >= end_date:
                            st.success(f"✅ {symbol} is already up to date (Latest: {last_recorded_date}).")
                            st.stop()

                        start_date = last_recorded_date + timedelta(days=1)
                        st.info(f"Updating missing days: {start_date} to {end_date}")
                        is_update = True
                    else:
                        start_date = end_date - relativedelta(years=10)
                        st.info("No existing file found. Fetching full 10-year history...")
                        existing_df = pd.DataFrame()

                    try:
                        raw_df = stock_df(symbol=symbol, from_date=start_date, to_date=end_date, series="EQ")

                        if raw_df.empty:
                            st.success("✅ No new trading days to add.")
                        else:
                            raw_df["DAILY_MEAN"] = (raw_df["HIGH"] + raw_df["LOW"] + raw_df["CLOSE"]) / 3
                            delivery_col = "% DLY QT TO TRADED QTY"
                            delivery_data = raw_df[delivery_col] if delivery_col in raw_df.columns else "N/A"

                            # Fix timezone offset so IST dates don't shift to Sundays
                            raw_dates = pd.to_datetime(raw_df["DATE"]).dt.tz_localize(None)
                            corrected_dates = (raw_dates + pd.Timedelta(hours=5, minutes=30)).dt.date

                            new_df = pd.DataFrame({
                                "Date": corrected_dates,
                                "Opening Share Price": raw_df["OPEN"],
                                "Closing Share Price": raw_df["CLOSE"],
                                "Daily Mean Share Price": raw_df["DAILY_MEAN"].round(2),
                                "Daily Trading Volume": raw_df["VOLUME"],
                                "Daily Delivery Percentage": delivery_data,
                            })

                            final_df = pd.concat([existing_df, new_df], ignore_index=True) if is_update else new_df
                            final_df = final_df.drop_duplicates(subset=["Date"]).sort_values(by="Date")

                            # Calculate On-Balance Volume (OBV)
                            price_change = final_df["Closing Share Price"].diff()
                            direction = np.sign(price_change).fillna(0)
                            final_df["OBV"] = (direction * final_df["Daily Trading Volume"]).cumsum()

                            final_df.to_csv(filename, index=False)
                            st.success(f"✅ Master file updated! Added {len(new_df)} new trading days.")

                            csv_data = final_df.to_csv(index=False).encode("utf-8")
                            st.download_button(
                                label="⬇️ Download Latest CSV",
                                data=csv_data,
                                file_name=filename,
                                mime="text/csv",
                                use_container_width=True,
                            )
                    except Exception as e:
                        st.error(f"❌ Error fetching data: {e}")
            else:
                st.warning("Please enter an NSE symbol above first.")
