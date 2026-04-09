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
    # 1. FORCE REFRESH: We load a fresh copy to ensure no other filters are active
    # This prevents items from disappearing when their status changes
    df_grid = load_data()[1] # Re-grabs the second item (packing list) from your load_data function
    
    # Standardize column names
    df_grid.columns = df_grid.columns.str.strip()
    cols = {col.lower(): col for col in df_grid.columns}
    col_item, col_type, col_cat, col_packed = cols.get('item', 'Item'), cols.get('trip_type', 'Trip_Type'), cols.get('category', 'Category'), cols.get('packed', 'Packed')

    # 2. Get active trip type
    try:
        active_trip_type = df_config.iloc[0]['Trip_Type']
    except:
        active_trip_type = "Regular"
    
    st.subheader(f"📦 Packing for: {active_trip_type}")

    # 3. STATIC FILTER: Specific Trip + Regular Essentials
    # We SORT by Item name so they stay in the exact same spot on the screen
    grid_list = df_grid[
        (df_grid[col_type] == active_trip_type) | 
        (df_grid[col_type] == "Regular")
    ].sort_values(by=[col_cat, col_item])

    if not grid_list.empty:
        packing_sheet = sh.worksheet("Packing_List")
        categories = grid_list[col_cat].unique()

        for cat in categories:
            st.markdown(f"#### {cat}")
            cat_items = grid_list[grid_list[col_cat] == cat]
            
            # Display items in a 2-column grid
            for i in range(0, len(cat_items), 2):
                cols_ui = st.columns(2)
                chunk = cat_items.iloc[i:i+2]
                
                for j, (idx, row) in enumerate(chunk.iterrows()):
                    # Use row.name to get the original row index from the Google Sheet
                    gsheet_row = row.name + 2 
                    is_packed = str(row[col_packed]).upper() == "YES"
                    
                    # Colors: Green if packed, White if not
                    bg_color = "#D1FFD7" if is_packed else "#FFFFFF" 
                    text_color = "#0E5A1F" if is_packed else "#D0021B"
                    border_color = "#28A745" if is_packed else "#D0021B"
                    
                    with cols_ui[j]:
                        # The Card Visual
                        st.markdown(f"""
                            <div style="
                                background-color:{bg_color}; 
                                border: 2px solid {border_color}; 
                                padding: 15px; 
                                border-radius: 10px; 
                                text-align: center;
                                margin-bottom: -45px;
                            ">
                                <p style="color:{text_color}; font-weight:bold; margin:0; font-size:1.1em;">
                                    {row[col_item]}
                                </p>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        # The Trigger
                        # The key includes the packed status to prevent state collisions
                        if st.checkbox("Toggle", value=is_packed, key=f"grid_p_{idx}_{is_packed}", label_visibility="hidden"):
                            if not is_packed:
                                packing_sheet.update_cell(gsheet_row, 3, "Yes")
                                st.cache_data.clear()
                                st.rerun()
                        else:
                            if is_packed:
                                packing_sheet.update_cell(gsheet_row, 3, "No")
                                st.cache_data.clear()
                                st.rerun()
    else:
        st.warning("No items found. Check your Trip_Type in Google Sheets!")


with tab3:
    st.info("Storage for passports and tickets.")
    st.link_button("Go to Vault", "https://drive.google.com")
