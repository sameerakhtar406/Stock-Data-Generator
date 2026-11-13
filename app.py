import streamlit as st

# Global page config (must be called once in the main entrypoint)
st.set_page_config(
    page_title="Stock Data Generator",
    page_icon="📈",
    layout="wide",  # Fixes the narrow centered table layout
)

# Define custom sidebar titles, icons, and display order
pages = [
    st.Page("pages/Home_dashboard.py", title="Daily Flagging Screener", icon="📈", default=True),
    st.Page("pages/filter_market_cap.py", title="ROCE/ROE Market Cap Screener", icon="💰"),
    st.Page("pages/historical_reports.py", title="Historical Reports", icon="🕰️"),
]

pg = st.navigation(pages)

with st.sidebar:
    st.divider()
    st.caption("Built by Sameer Akhtar")
    st.caption("Data: NSE & Yahoo Finance")

pg.run()
