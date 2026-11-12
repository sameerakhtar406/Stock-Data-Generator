import os
import sys
import pandas as pd
import streamlit as st
from datetime import date, timedelta

# Add root folder to sys.path so historical_screener.py can be imported cleanly
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from historical_screener import run_historical_screener

st.title("🕰️ Historical Flagged Companies")
st.write("Run `historical_screener.py` on any past trading date to inspect 2x+ volume breakouts with 2%–3.99% price action.")

col1, col2 = st.columns([2, 1])
with col1:
    selected_date = st.date_input(
        "Select Target Date (YYYY-MM-DD)",
        value=date.today() - timedelta(days=1),
        max_value=date.today()
    )
with col2:
    exchange_filter = st.selectbox("Filter Exchange", ["All", "NSE", "BSE"])

target_date_str = selected_date.strftime("%Y-%m-%d")
csv_filename = f"flagged_stocks_{target_date_str}.csv"

# Run the root screener when clicked
if st.button("🚀 Generate Historical Report", type="primary"):
    progress_bar = st.progress(0)
    status_text = st.empty()

    def update_progress(collected, total, fetched_date):
        progress_bar.progress(int((collected / total) * 100))
        status_text.text(f"[{collected}/{total}] Collected market data for {fetched_date}...")

    run_historical_screener(target_date_str, progress_callback=update_progress)

    progress_bar.empty()
    status_text.empty()

# Read and display the generated CSV output
if os.path.exists(csv_filename):
    df = pd.read_csv(csv_filename)

    if exchange_filter != "All" and not df.empty:
        df = df[df["Exchange"] == exchange_filter]

    if df.empty:
        st.warning(f"No flagged companies found for **{target_date_str}** (or the market was closed on this date).")
    else:
        st.success(f"Showing **{len(df)}** flagged companies for **{target_date_str}**")
        st.dataframe(df, use_container_width=True)

        st.download_button(
            label=f"⬇️ Download {csv_filename}",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name=csv_filename,
            mime="text/csv"
        )
else:
    st.info("Select a target date above and click **Generate Historical Report** to fetch results.")
