import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Page configuration
st.set_page_config(page_title="State #3817 Leaderboards", layout="wide")
st.title("🛡️ Whiteout Survival - State #3817 Leaderboards")

# Fetch data from Google Sheets
@st.cache_data(ttl=600)  # Cache for 10 minutes
def load_data():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    # Load secrets from Streamlit Secrets Manager
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    client = gspread.authorize(creds)
    sheet = client.open("WOS_State_3817_Leaderboards").sheet1
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    if not df.empty:
        df["Rank"] = pd.to_numeric(df["Rank"], errors="coerce")
        df["Submission_Date"] = pd.to_datetime(df["Submission_Date"])
    return df

df = load_data()

if df.empty:
    st.info("No leaderboard data captured yet.")
else:
    # Sidebar Filters
    st.sidebar.header("Navigation & Filters")
    view_option = st.sidebar.radio("View Mode", ["Event Leaderboards", "Player Tracker", "State Analytics"])
    
    events = ["All"] + list(df["Event_Name"].unique())
    selected_event = st.sidebar.selectbox("Select Event", events)

    filtered_df = df if selected_event == "All" else df[df["Event_Name"] == selected_event]

    # Mode 1: Event Leaderboard Tables
    if view_option == "Event Leaderboards":
        st.subheader(f"Leaderboard Entries: {selected_event}")
        st.dataframe(
            filtered_df.sort_values(by=["Submission_Date", "Rank"], ascending=[False, True]),
            use_container_width=True
        )

    # Mode 2: Search Player History
    elif view_option == "Player Tracker":
        st.subheader("🔍 Search Player Performance")
        player_search = st.text_input("Enter Player Name:", "")
        if player_search:
            player_df = df[df["Player_Name"].str.contains(player_search, case=False, na=False)]
            if not player_df.empty:
                st.write(f"History for **{player_search}**:")
                st.dataframe(player_df.sort_values(by="Submission_Date", ascending=False))
                
                # Plot Rank Progression
                fig = px.line(
                    player_df, 
                    x="Submission_Date", 
                    y="Rank", 
                    color="Event_Name", 
                    title="Rank History (Lower is Better)",
                    markers=True
                )
                fig.update_yaxes(autorange="reversed")  # Rank 1 at top
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("Player not found in records.")

    # Mode 3: State-Wide Analytics
    elif view_option == "State Analytics":
        st.subheader("📊 State #3817 Hall of Fame")
        top_players = filtered_df[filtered_df["Rank"] <= 3]["Player_Name"].value_counts().reset_index()
        top_players.columns = ["Player Name", "Top 3 Finishes"]
        
        fig = px.bar(top_players.head(10), x="Player Name", y="Top 3 Finishes", title="Most Top 3 Finishes")
        st.plotly_chart(fig, use_container_width=True)
