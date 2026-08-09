import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials

# Page Configuration
st.set_page_config(
    page_title="State #3817 Leaderboards | Whiteout Survival",
    page_icon="🛡️",
    layout="wide"
)

st.title("🛡️ Whiteout Survival — State #3817 Leaderboards")
st.markdown("Automated top 20 event tracking and player performance history.")

# Connect to Google Sheets via Streamlit Secrets
@st.cache_data(ttl=300)  # Auto-refresh data every 5 minutes
def load_data():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    # Load secrets set up in Streamlit Community Cloud
    creds_dict = dict(st.secrets["gcp_service_account"])
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(credentials)
    
    sheet = client.open("WOS_State_3817_Leaderboards").sheet1
    records = sheet.get_all_records()
    df = pd.DataFrame(records)
    
    if not df.empty:
        # Data Cleaning & Type Conversion
        df["Rank"] = pd.to_numeric(df["Rank"], errors="coerce")
        df["Submission_Date"] = pd.to_datetime(df["Submission_Date"], errors="coerce")
        df["Player_Name"] = df["Player_Name"].astype(str).str.strip()
        df["Event_Name"] = df["Event_Name"].astype(str).str.strip().str.upper()
        
    return df

try:
    df = load_data()
except Exception as e:
    st.error(f"Error loading Google Sheets data. Check your Streamlit Secrets configuration: {e}")
    st.stop()

if df.empty:
    st.info("No leaderboard data recorded yet. Upload screenshots to `#small-events-monitoring` in Discord to populate the dashboard!")
else:
    # Sidebar Filters
    st.sidebar.header("Navigation")
    view_mode = st.sidebar.radio(
        "Select View",
        ["🏆 Event Leaderboards", "🔍 Player Tracker", "📊 State Analytics"]
    )

    # Key Performance Indicators
    col1, col2, col3 = st.columns(3)
    col1.metric("Events Tracked", df["Event_Name"].nunique())
    col2.metric("Total Rankings Logged", len(df))
    col3.metric("Unique Players", df["Player_Name"].nunique())
    st.divider()

    # VIEW 1: EVENT LEADERBOARDS
    if view_mode == "🏆 Event Leaderboards":
        st.subheader("Event Leaderboard Entries")
        
        events = sorted(df["Event_Name"].unique().tolist())
        selected_event = st.selectbox("Filter by Event", ["All Events"] + events)
        
        event_df = df if selected_event == "All Events" else df[df["Event_Name"] == selected_event]

        # Date Filter
        available_dates = sorted(event_df["Submission_Date"].dt.date.dropna().unique().tolist(), reverse=True)
        selected_date = st.selectbox("Filter by Date", ["All Dates"] + available_dates)

        if selected_date != "All Dates":
            event_df = event_df[event_df["Submission_Date"].dt.date == selected_date]

        display_df = event_df[["Event_Name", "Rank", "Player_Name", "Score", "Submission_Date"]].sort_values(
            by=["Submission_Date", "Rank"], ascending=[False, True]
        )

        st.dataframe(display_df, use_container_width=True, hide_index=True)

    # VIEW 2: PLAYER TRACKER
    elif view_mode == "🔍 Player Tracker":
        st.subheader("Player Performance & Progression History")
        
        player_list = sorted(df["Player_Name"].unique().tolist())
        selected_player = st.selectbox("Search or Select Player:", player_list)

        if selected_player:
            p_df = df[df["Player_Name"] == selected_player].sort_values(by="Submission_Date", ascending=False)
            
            # Individual Player Stats
            top1_count = len(p_df[p_df["Rank"] == 1])
            top3_count = len(p_df[p_df["Rank"] <= 3])
            top10_count = len(p_df[p_df["Rank"] <= 10])

            m1, m2, m3 = st.columns(3)
            m1.metric("1st Place Finishes", top1_count)
            m2.metric("Top 3 Finishes", top3_count)
            m3.metric("Top 10 Finishes", top10_count)

            st.write(f"Leaderboard History for **{selected_player}**:")
            st.dataframe(
                p_df[["Submission_Date", "Event_Name", "Rank", "Score"]],
                use_container_width=True,
                hide_index=True
            )

            # Rank Progression Chart (Inverted Y-axis so Rank 1 is at the top)
            if len(p_df) > 1:
                fig = px.line(
                    p_df,
                    x="Submission_Date",
                    y="Rank",
                    color="Event_Name",
                    markers=True,
                    title=f"{selected_player} — Rank History Across Events"
                )
                fig.update_yaxes(autorange="reversed", dtick=1)
                st.plotly_chart(fig, use_container_width=True)

    # VIEW 3: STATE ANALYTICS
    elif view_mode == "📊 State Analytics":
        st.subheader("State #3817 Hall of Fame")

        col_a, col_b = st.columns(2)

        with col_a:
            st.markdown("### Most Top 3 Finishes")
            top3_df = df[df["Rank"] <= 3]["Player_Name"].value_counts().reset_index()
            top3_df.columns = ["Player Name", "Top 3 Count"]
            fig_top3 = px.bar(
                top3_df.head(10),
                x="Player Name",
                y="Top 3 Count",
                color="Top 3 Count",
                color_continuous_scale="Blues"
            )
            st.plotly_chart(fig_top3, use_container_width=True)

        with col_b:
            st.markdown("### Most #1 Finishes")
            top1_df = df[df["Rank"] == 1]["Player_Name"].value_counts().reset_index()
            top1_df.columns = ["Player Name", "1st Place Count"]
            fig_top1 = px.bar(
                top1_df.head(10),
                x="Player Name",
                y="1st Place Count",
                color="1st Place Count",
                color_continuous_scale="Oranges"
            )
            st.plotly_chart(fig_top1, use_container_width=True)

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
