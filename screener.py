import os
import smtplib
import pandas as pd
import numpy as np
from datetime import date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

def run_screener():
    # Placeholder: Replace with unified Bhavcopy retrieval
    # Criteria: Volume >= (2x 30-Day Avg) & |Price Change| between 2% and 3%
    print("[SYSTEM] Running quantitative screen...")
    
    # Mock result format (populated by Bhavcopy parser)
    flagged_df = pd.DataFrame(columns=[
        "Symbol", "Exchange", "Close_Price", 
        "30D_Avg_Volume", "Today_Volume", "Volume_Multiple", "30D_Return_Pct"
    ])
    
    # Save the master flagged file for the Streamlit dashboard
    output_filename = "flagged_stocks.csv"
    flagged_df.to_csv(output_filename, index=False)
    print(f"[SYSTEM] Saved results to {output_filename}")
    
    # Dispatch Email
    send_email(output_filename, len(flagged_df))

def send_email(attachment_path, stock_count):
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")
    recipient_email = os.getenv("RECIPIENT_EMAIL")

    if not (sender_email and sender_password and recipient_email):
        print("[WARNING] Email secrets not configured. Skipping SMTP dispatch.")
        return

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = f"📈 Daily Market Screener Report by Sam- {date.today()} ({stock_count} Flagged)"

    body = f"""Hello,\n\nPlease find attached the daily stock breakout screener report for {date.today()}.\n\nTotal companies flagged: {stock_count}\n\nYou can also view the interactive dashboard on Streamlit.\n\nBest regards,\n Sameer Akhtar 'Sam'"""
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
    print("[SYSTEM] Email successfully dispatched to recipient.")

if __name__ == "__main__":
    run_screener()