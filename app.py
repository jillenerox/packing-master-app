import streamlit as st
import pandas as pd
import requests

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

# --- WEATHER MOOD AND TEMP ---
def get_weather(city):
    api_key = st.secrets["weather_api_key"]
    # Ensure there is an 'f' before the quotes and no line breaks inside the quotes
    url = f"https://api.googleapis.com/weather/v1/current?q={city}&key={api_key}"
    
    try:
        response = requests.get(url).json()
        temp = response['main']['temp']
        condition = response['weather'][0']['main'] 
        return temp, condition
    except:
        return None, None


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
    st.write("### 🔔 Trip Countdown")
    
    # Sort reminders so the most urgent are on top
    df_reminders = df_reminders.sort_values(by="Days_Before", ascending=False)

    for _, row in df_reminders.iterrows():
        deadline = start_dt - pd.Timedelta(days=row['Days_Before'])
        days_to_deadline = (deadline - datetime.now()).days
        is_done = str(row['Done']).upper() == "YES"
        
        # Color Logic
        if is_done:
            color, icon = "#28a745", "✅" # Green
        elif days_to_deadline < 0:
            color, icon = "#FF4B4B", "🚨" # Red (Overdue)
        elif days_to_deadline <= 2:
            color, icon = "#FFA500", "⚠️" # Orange (Urgent)
        else:
            color, icon = "#555555", "📅" # Grey (Future)

        # Render Styled Card
        st.markdown(f"""
            <div style='border-left: 6px solid {color}; padding: 12px; background: #f9f9f9; 
                        border-radius: 6px; margin-bottom: 10px; box-shadow: 2px 2px 5px rgba(0,0,0,0.05);'>
                <div style='display: flex; justify-content: space-between; align-items: center;'>
                    <span style='font-weight: bold; color: #333;'>{icon} {row['Reminder']}</span>
                    <span style='font-size: 0.85em; color: {color}; font-weight: bold;'>
                        {deadline.strftime('%d %b')} ({days_to_deadline}d)
                    </span>
                </div>
            </div>
        """, unsafe_allow_html=True)

with tab2:
    # Weather Alert
    if curr_temp:
        st.write(f"### 🌡️ Current Weather in {dest}: {curr_temp}°C ({curr_cond})")
        if "Rain" in curr_cond:
            st.warning("☔ It's currently raining there! Make sure your umbrella is in the 'Essentials' section.")
        if curr_temp < 15:
            st.info("❄️ It's a bit chilly! I've highlighted your 'Cold' gear below.")

    st.write("### 📦 Categorized Checklist")
    
    # Smart Filtering: Show items matching the weather/trip type
    # (You can expand this logic based on your Packing_List 'Trip_Type' column)
    st.data_editor(df_packing, hide_index=True, use_container_width=True, key="packing_editor")

with tab3:
    st.link_button("📂 Open Digital Vault (Google Drive)", "https://drive.google.com", use_container_width=True)
