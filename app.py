import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import math
import requests

# --- 1. CONNECTION SETUP ---
@st.cache_resource
def init_connection():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    return gspread.authorize(creds)

client = init_connection()
sh = client.open("Packing_Master")

# --- 2. WEATHER API FUNCTION ---
def get_weather(city):
    if "weather_api_key" not in st.secrets:
        return None, None
    try:
        key = st.secrets["weather_api_key"]
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {"q": city, "appid": key, "units": "metric"}
        res = requests.get(url, params=params)
        data = res.json()
        return data["main"]["temp"], data["weather"][0]["main"]
    except:
        return None, None

# --- 3. DATA LOADING (With Caching) ---
@st.cache_data(ttl=60) # Cache for 1 minute to allow updates to show
def load_data():
    config = pd.DataFrame(sh.worksheet("Trip_Config").get_all_records())
    packing = pd.DataFrame(sh.worksheet("Packing_List").get_all_records())
    reminders = pd.DataFrame(sh.worksheet("Reminders").get_all_records())
    return config, packing, reminders

df_config, df_packing, df_reminders = load_data()

# --- 4. TRIP CALCULATIONS ---
trip_info = df_config.iloc[0]
trip_name = trip_info['Trip_Name']
dest = trip_info['Destination']
start_dt = pd.to_datetime(trip_info['Start_Date'])
end_dt = pd.to_datetime(trip_info['End_Date'])
laundry = str(trip_info['Laundry_Access']).upper() == "YES"

duration = (end_dt - start_dt).days
days_to_trip = (start_dt - datetime.now()).days

# Weather Call
curr_temp, curr_cond = get_weather(dest)

# --- 5. THE LAUNDRY MATH ---
def calculate_quantities(days, has_laundry):
    multiplier = 0.5 if has_laundry else 1.0
    return {
        "Tops": math.ceil((days / 1.5) * multiplier),
        "Bottoms": math.ceil((days / 3) * multiplier),
        "Socks/Undies": math.ceil((days + 1) * multiplier)
    }

quantities = calculate_quantities(duration, laundry)

# --- 6. UI LAYOUT ---
st.set_page_config(page_title="Travel Ready", page_icon="✈️", layout="wide")

st.title(f"🎒 {trip_name}")

# Metrics Row
m1, m2, m3 = st.columns(3)
m1.metric("Destination", dest)
m2.metric("Duration", f"{duration} Days")
m3.metric("Days Until Trip", days_to_trip)

# Weather Widget at the top
if curr_temp:
    with st.container(border=True):
        w1, w2 = st.columns([1, 5])
        w1.markdown(f"<h1 style='text-align: center; margin:0;'>{int(curr_temp)}°</h1>", unsafe_allow_html=True)
        w2.markdown(f"**Current Weather in {dest}**<br>{curr_cond}", unsafe_allow_html=True)

st.divider()

# --- 7. TABS ---
tab1, tab2, tab3 = st.tabs(["🔔 Reminders", "📦 Packing List", "🔐 Vault"])

with tab1:
    st.subheader("Trip Checklist")
    
    # We use a form-like display for reminders
    reminder_sheet = sh.worksheet("Reminders")
    
    for idx, row in df_reminders.iterrows():
        deadline = start_dt - pd.Timedelta(days=int(row['Days_Before']))
        is_done = str(row['Done']).upper() == "YES"
        overdue = datetime.now() > deadline and not is_done
        
        # Color and Icon Logic
        if is_done:
            color = "#28a745" # Green
            label = "Done"
            icon = "✅"
        else:
            color = "#FF4B4B" # Red
            label = "Pending"
            icon = "⚠️" if datetime.now() > deadline else "📅"

        # Create a container for each reminder
        with st.container(border=True):
            col_text, col_btn = st.columns([4, 1])
            
            with col_text:
                st.markdown(f"<span style='color:{color}; font-weight:bold;'>{icon} {row['Reminder']}</span>", unsafe_allow_html=True)
                st.caption(f"Due: {deadline.strftime('%d %b')} ({row['Days_Before']} days before trip)")
            
            with col_btn:
                # Toggle Button
                new_status = "No" if is_done else "Yes"
                if st.button(f"Mark as {new_status}", key=f"rem_{idx}"):
                    # Update Google Sheet directly (Row is idx+2 because GSheets is 1-indexed + header)
                    reminder_sheet.update_cell(idx + 2, 3, new_status)
                    st.cache_data.clear() # Clear cache to refresh the UI
                    st.rerun()

with tab2:
    st.write(f"### 💡 Recommended for {duration} Days")
    q_cols = st.columns(3)
    q_cols[0].metric("Tops", quantities["Tops"])
    q_cols[1].metric("Bottoms", quantities["Bottoms"])
    q_cols[2].metric("Innerwear", quantities["Socks/Undies"])
    
    st.divider()
    st.write("### 📋 Full Packing Checklist")
    st.data_editor(df_packing, hide_index=True, use_container_width=True)

with tab3:
    st.link_button("📂 Open Digital Vault", "https://drive.google.com", use_container_width=True)
