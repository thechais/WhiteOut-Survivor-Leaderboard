import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="State #3817 Leaderboards", page_icon="🛡️", layout="wide")
st.title("🛡️ Whiteout Survival — State #3817 Leaderboards")

@st.cache_data(ttl=300)
def load_data():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"])
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(credentials)
    
    sheet = client.open("WOS_State_3817_Leaderboards").sheet1
    df = pd.DataFrame(sheet.get_all_records())
    
    if not df.empty:
        df["Rank"] = pd.to_numeric(df["Rank"], errors="coerce")
        df["Submission_Date"] = pd.to_datetime(df["Submission_Date"], errors="coerce")
        df["Player_Name"] = df["Player_Name"].astype(str).str.strip()
        df["Event_Name"] = df["Event_Name"].astype(str).str.strip().str.upper()
    return df

try:
    df = load_data()
except Exception as e:
    st.error(f"Error connecting to Google Sheets: {e}")
    st.stop()

if df.empty:
    st.info("No data logged yet. Submit screenshots in Discord during the 00:00–03:00 UTC window to populate the dashboard!")
else:
    st.sidebar.header("Navigation")
    view = st.sidebar.radio("Select View", ["🏆 Event Leaderboards", "🔍 Player Tracker", "📊 State Analytics"])

    # ------------------------------------------
    # VIEW 1: EVENT LEADERBOARDS (WITH HISTORICAL DATES)
    # ------------------------------------------
    if view == "🏆 Event Leaderboards":
        st.subheader("Leaderboard Records")
        
        events = sorted(df["Event_Name"].unique().tolist())
        selected_event = st.selectbox("Select Event", events)
        
        event_df = df[df["Event_Name"] == selected_event]
        
        # Historical date selector
        available_dates = sorted(event_df["Submission_Date"].dt.date.unique().tolist(), reverse=True)
        selected_date = st.selectbox("Select Event Date", available_dates)
        
        # Display specific historical event run
        final_df = event_df[event_df["Submission_Date"].dt.date == selected_date].sort_values("Rank")
        
        st.dataframe(
            final_df[["Rank", "Player_Name", "Score", "Submission_Date"]],
            use_container_width=True,
            hide_index=True
        )

    # ------------------------------------------
    # VIEW 2: PLAYER TRACKER
    # ------------------------------------------
    elif view == "🔍 Player Tracker":
        st.subheader("Player Performance Search")
        
        player_list = sorted(df["Player_Name"].unique().tolist())
        selected_player = st.selectbox("Select Player", player_list)
        
        if selected_player:
            p_df = df[df["Player_Name"] == selected_player].sort_values("Submission_Date", ascending=False)
            st.dataframe(
                p_df[["Submission_Date", "Event_Name", "Rank", "Score"]],
                use_container_width=True,
                hide_index=True
            )

    # ------------------------------------------
    # VIEW 3: STATE ANALYTICS
    # ------------------------------------------
    elif view == "📊 State Analytics":
        st.subheader("State #3817 Hall of Fame")
        
        # Calculate 1st place wins per player across all historical events
        top1_df = df[df["Rank"] == 1]["Player_Name"].value_counts().reset_index()
        top1_df.columns = ["Player Name", "1st Place Count"]
        
        if not top1_df.empty:
            fig = px.bar(
                top1_df.head(10),
                x="Player Name",
                y="1st Place Count",
                color="1st Place Count",
                title="Top Event Winners (Most 1st Place Finishes)"
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No Rank 1 records logged yet.")
