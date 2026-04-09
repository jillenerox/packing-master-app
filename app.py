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
    try:
        api_key = st.secrets["weather_api_key"]
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric"
        response = requests.get(url).json()
        temp = response['main']['temp']
        condition = response['weather'][0']['main']
        return temp, condition
    except:
        return None, None

# --- 3. DATA LOADING ---
def load_data():
    config = pd.DataFrame(sh.worksheet("Trip_Config").get_all_records())
    packing = pd.DataFrame(sh.worksheet("Packing_List").get_all_records())
    reminders = pd.DataFrame(sh.worksheet("Reminders").get_all_records())
    return config, packing, reminders

df_config, df_packing, df_reminders = load_data()

# --- 4. TRIP CALCULATIONS ---
trip_info = df_config.iloc[0]
trip_name = trip_info['Trip Name']
dest = trip_info['Destination']
start_dt = pd.to_datetime(trip_info['Start_Date'])
end_dt = pd.to_datetime(trip_info['End_Date'])
laundry = str(trip_info['Laundry_Access']).upper() == "YES"

duration = (end_dt - start_dt).days
days_to_trip = (start_dt - datetime.now()).days

# Weather Call
curr_temp, curr_cond = get_weather(dest)

# --- 5. THE LAUNDRY MATH ENGINE ---
def calculate_quantities(days, has_laundry):
    multiplier = 0.5 if has_laundry else 1.0
    return {
        "Tops": math.ceil((days / 1.5) * multiplier),
        "Bottoms": math.ceil((days / 3) * multiplier),
        "Socks/Undies": math.ceil((days + 1) * multiplier),
        "Outerwear": 1 if days < 7 else 2
    }

quantities = calculate_quantities(duration, laundry)

# --- 6. UI LAYOUT ---
st.set_page_config(page_title="Travel Ready", page_icon="✈️", layout="wide")

# Header Section
st.title(f"🎒 {trip_name}")
c1, c2, c3 = st.columns(3)
c1.metric("Destination", dest)
c2.metric("Duration", f"{duration} Days")
c3.metric("Countdown", f"{days_to_trip} Days Out")

st.divider()

# --- 7. TABS ---
tab1, tab2, tab3 = st.tabs(["🔔 Reminders", "📦 Packing List", "🔐 Vault"])

with tab1:
    st.subheader("Trip Countdown Reminders")
    # Sort reminders by urgency
    df_reminders = df_reminders.sort_values(by="Days_Before", ascending=False)

    for _, row in df_reminders.iterrows():
        deadline = start_dt - pd.Timedelta(days=int(row['Days_Before']))
        days_to_deadline = (deadline - datetime.now()).days
        is_done = str(row['Done']).upper() == "YES"
        
        if is_done:
            color, icon = "#28a745", "✅" 
        elif days_to_deadline < 0:
            color, icon = "#FF4B4B", "🚨" 
        elif days_to_deadline <= 2:
            color, icon = "#FFA500", "⚠️" 
        else:
            color, icon = "#555555", "📅"

        st.markdown(f"""
            <div style='border-left: 6px solid {color}; padding: 12px; background: #f1f1f1; 
                        border-radius: 6px; margin-bottom: 10px;'>
                <div style='display: flex; justify-content: space-between; align-items: center;'>
                    <span style='font-weight: bold; color: #333;'>{icon} {row['Reminder']}</span>
                    <span style='font-size: 0.85em; color: {color}; font-weight: bold;'>
                        {deadline.strftime('%d %b')} ({days_to_deadline}d)
                    </span>
                </div>
            </div>
        """, unsafe_allow_html=True)

with tab2:
    # Weather Widget
    if curr_temp:
        with st.container(border=True):
            w1, w2 = st.columns([1, 4])
            w1.markdown(f"<h1 style='text-align: center; margin:0;'>{int(curr_temp)}°C</h1>", unsafe_allow_html=True)
            w2.markdown(f"**Current Weather in {dest}**<br>Condition: {curr_cond}", unsafe_allow_html=True)
            if "Rain" in str(curr_cond):
                st.warning("☔ Rain detected! Don't forget an umbrella or raincoat.")

    st.write("### 💡 Recommended Quantities")
    q_cols = st.columns(4)
    q_cols[0].metric("Tops", quantities["Tops"])
    q_cols[1].metric("Bottoms", quantities["Bottoms"])
    q_cols[2].metric("Innerwear", quantities["Socks/Undies"])
    q_cols[3].metric("Jackets", quantities["Outerwear"])

    st.divider()
    st.write("### 📋 Full Packing Checklist")
    # Interactive Table for Packing
    edited_df = st.data_editor(df_packing, hide_index=True, use_container_width=True)
    
    if st.button("Save Packing Progress"):
        # This is where you'd write back to GSheets if you want to save state
        st.success("Progress logged! (Note: GSheet write-back code can be added here)")

with tab3:
    st.info("Quick access to your important travel documents.")
    # Replace the link below with your actual Google Drive folder link
    st.link_button("📂 Open Google Drive Vault", "https://drive.google.com", use_container_width=True)
