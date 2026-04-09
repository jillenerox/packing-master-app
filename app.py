import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import math

# --- 1. CONNECTION SETUP ---
@st.cache_resource
def init_connection():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    return gspread.authorize(creds)

client = init_connection()
sh = client.open("Packing_Master") # Ensure this matches your Sheet name exactly

# --- 2. DATA LOADING ---
def load_data():
    config = pd.DataFrame(sh.worksheet("Trip_Config").get_all_records())
    packing = pd.DataFrame(sh.worksheet("Packing_List").get_all_records())
    reminders = pd.DataFrame(sh.worksheet("Reminders").get_all_records())
    return config, packing, reminders

df_config, df_packing, df_reminders = load_data()

# --- 3. TRIP CALCULATIONS ---
# Extracting values from the Trip_Config tab
trip_info = df_config.iloc[0]
trip_name = trip_info['Trip_Name']
dest = trip_info['Destination']
start_dt = pd.to_datetime(trip_info['Start_Date'])
end_dt = pd.to_datetime(trip_info['End_Date'])
laundry = str(trip_info['Laundry_Access']).upper() == "YES"

duration = (end_dt - start_dt).days
days_to_trip = (start_dt - datetime.now()).days

# --- 4. THE LAUNDRY MATH ENGINE ---
def calculate_quantities(days, has_laundry):
    multiplier = 0.5 if has_laundry else 1.0
    return {
        "Tops": math.ceil((days / 1.5) * multiplier),
        "Bottoms": math.ceil((days / 3) * multiplier),
        "Socks/Undies": math.ceil((days + 1) * multiplier),
        "Outerwear": 1 if days < 7 else 2
    }

quantities = calculate_quantities(duration, laundry)

# --- 5. UI LAYOUT ---
st.set_page_config(page_title="Travel Ready", page_icon="✈️")

# Header Section
st.title(f"🎒 {trip_name}")
c1, c2, c3 = st.columns(3)
c1.metric("Destination", dest)
c2.metric("Duration", f"{duration} Days")
c3.metric("Countdown", f"{days_to_trip} Days Out")

st.divider()

# --- 6. PRESCRIPTIVE RECOMMENDATIONS ---
st.subheader("💡 Recommended Quantities")
st.info(f"Based on a {duration}-day trip " + ("with" if laundry else "without") + " laundry access:")

q_cols = st.columns(4)
q_cols[0].metric("Tops", quantities["Tops"])
q_cols[1].metric("Bottoms", quantities["Bottoms"])
q_cols[2].metric("Innerwear", quantities["Socks/Undies"])
q_cols[3].metric("Jackets", quantities["Outerwear"])

# --- 7. TABS FOR REMINDERS & PACKING ---
tab1, tab2, tab3 = st.tabs(["🔔 Reminders", "📦 Packing List", "🔐 Vault"])

with tab1:
    st.write("### Trip Countdown")
    # Logic for your colored reminders goes here (similar to the snippet we discussed)
    for _, row in df_reminders.iterrows():
        deadline = start_dt - pd.Timedelta(days=row['Days_Before'])
        st.checkbox(f"{row['Reminder']} (Due: {deadline.strftime('%d %b')})", value=(row['Done'] == "Yes"))

with tab2:
    st.write("### Categorized Checklist")
    # Filter packing list by Trip Type
    # For now, showing a simple dataframe
    st.data_editor(df_packing, hide_index=True, use_container_width=True)

with tab3:
    st.link_button("📂 Open Digital Vault (Google Drive)", "https://drive.google.com", use_container_width=True)
