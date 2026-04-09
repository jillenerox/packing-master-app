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
def get_weather_data(city):
    if "weather_api_key" not in st.secrets:
        return None, None
    try:
        key = st.secrets["weather_api_key"]
        # Current Weather
        curr_url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={key}&units=metric"
        curr_res = requests.get(curr_url).json()
        
        # Forecast (5 Day)
        fore_url = f"https://api.openweathermap.org/data/2.5/forecast?q={city}&appid={key}&units=metric"
        fore_res = requests.get(fore_url).json()
        
        return curr_res, fore_res
    except:
        return None, None

# --- 3. DATA LOADING (With Caching) ---
@st.cache_data(ttl=300) 
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

# Fetch Weather
weather_now, weather_forecast = get_weather_data(dest)

# --- 5. UI LAYOUT ---
st.set_page_config(page_title="Packing Master", page_icon="✈️", layout="wide")

st.title(f"🎒 {trip_name}")
c1, c2, c3 = st.columns(3)
c1.metric("Destination", dest)
c2.metric("Trip Length", f"{duration} Days")
c3.metric("Countdown", f"{days_to_trip} Days")

st.divider()

# --- 6. WEATHER SECTION ---
# Temporary debug line - delete this once it's working!
st.write(f"Debug: Weather Key Found? {'weather_api_key' in st.secrets}")
st.write(f"Debug: Reminders Found? {len(df_reminders)} rows loaded")

if weather_now:
    st.subheader(f"🌦️ Weather Report: {dest}")
    w_col1, w_col2 = st.columns([1, 2])
    
    with w_col1:
        # Simplified extraction to avoid string literal errors
        main_data = weather_now.get('main', {})
        temp = main_data.get('temp', 0)
        
        weather_list = weather_now.get('weather', [{}])
        desc = weather_list[0].get('description', 'No description')
        
        st.write("**Right Now:**")
        st.markdown(f"### {int(temp)}°C | {desc.capitalize()}")
    
    with w_col2:
        st.write("**Trip Forecast (Next 5 Days):**")
        forecast_items = weather_forecast.get('list', [])
        # Get one forecast per day (filtering for noon)
        f_days = [f for f in forecast_items if "12:00:00" in f.get('dt_txt', '')]
        
        if f_days:
            cols = st.columns(len(f_days))
            for i, day in enumerate(f_days):
                dt_str = day.get('dt_txt', '')
                d_date = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").strftime("%a")
                d_temp = int(day.get('main', {}).get('temp', 0))
                cols[i].write(f"{d_date}\n\n**{d_temp}°**")

st.divider()

# --- 7. TABS ---
tab1, tab2, tab3 = st.tabs(["🔔 Reminders", "📦 Packing List", "🔐 Vault"])

with tab1:
    # SORTING: Not Done first, then by Days_Before descending
    df_reminders['sort_done'] = df_reminders['Done'].apply(lambda x: 0 if str(x).upper() == "NO" else 1)
    df_reminders = df_reminders.sort_values(by=['sort_done', 'Days_Before'], ascending=[True, False])
    
    reminder_sheet = sh.worksheet("Reminders")
    
    for idx, row in df_reminders.iterrows():
        # Correct index for GSheets (Row 1 is header, so index + 2)
        gsheet_row = row.name + 2
        deadline = start_dt - pd.Timedelta(days=int(row['Days_Before']))
        is_done = str(row['Done']).upper() == "YES"
        is_late = (datetime.now() > deadline) and not is_done
        
        color = "#28a745" if is_done else "#FF4B4B"
        icon = "✅" if is_done else ("⚠️" if is_late else "📅")

        with st.container(border=True):
            r_text, r_btn = st.columns([4, 1])
            with r_text:
                st.markdown(f"<span style='color:{color}; font-weight:bold;'>{icon} {row['Reminder']}</span>", unsafe_allow_html=True)
                st.caption(f"Due {deadline.strftime('%d %b')} ({row['Days_Before']} days out)")
            with r_btn:
                btn_label = "Undo" if is_done else "Done"
                if st.button(btn_label, key=f"btn_{idx}", use_container_width=True):
                    new_val = "No" if is_done else "Yes"
                    reminder_sheet.update_cell(gsheet_row, 3, new_val)
                    st.cache_data.clear()
                    st.rerun()

with tab2:
    st.subheader("📦 Trip Packing List")
    
    # 1. ADD NEW ITEM SECTION
    with st.expander("➕ Add New Item to List"):
        with st.form("add_item_form", clear_on_submit=True):
            new_cat = st.selectbox("Category", ["Clothing", "Toiletries", "Electronics", "Documents", "Others"])
            new_item = st.text_input("Item Name")
            if st.form_submit_state and st.form_submit_button("Add to Sheet"):
                if new_item:
                    # Append to GSheets (Assuming columns: Category, Item, Packed)
                    sh.worksheet("Packing_List").append_row([new_cat, new_item, "No"])
                    st.cache_data.clear()
                    st.rerun()

    # 2. DISPLAY BY CATEGORY
    packing_sheet = sh.worksheet("Packing_List")
    
    # Group items by Category from your GSheet
    categories = df_packing['Category'].unique()
    
    for cat in categories:
        st.markdown(f"#### {cat}")
        cat_items = df_packing[df_packing['Category'] == cat]
        
        for idx, row in cat_items.iterrows():
            # Index for GSheets (Row 1 is header)
            gsheet_row = row.name + 2
            is_packed = str(row['Packed']).upper() == "YES"
            
            # Styling based on your Red/Red request
            if is_packed:
                # Muted Red / Strikethrough for Packed
                text_style = "color: #ffcccc; text-decoration: line-through;"
                btn_label = "Unpack"
            else:
                # Bright Red for Not Packed
                text_style = "color: #FF4B4B; font-weight: bold;"
                btn_label = "Pack"

            with st.container(border=True):
                p_col1, p_col2, p_col3 = st.columns([3, 1, 1])
                
                with p_col1:
                    st.markdown(f"<span style='{text_style}'>{row['Item']}</span>", unsafe_allow_html=True)
                
                with p_col2:
                    if st.button(btn_label, key=f"pack_{idx}", use_container_width=True):
                        new_status = "No" if is_packed else "Yes"
                        packing_sheet.update_cell(gsheet_row, 3, new_status)
                        st.cache_data.clear()
                        st.rerun()
                
                with p_col3:
                    if st.button("🗑️", key=f"del_{idx}", use_container_width=True):
                        packing_sheet.delete_rows(gsheet_row)
                        st.cache_data.clear()
                        st.rerun()

with tab3:
    st.info("Storage for passports and tickets.")
    st.link_button("Go to Vault", "https://drive.google.com")
