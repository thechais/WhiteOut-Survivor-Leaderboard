import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import plotly.express as px
import plotly.graph_objects as go

# Page Configuration
st.set_page_config(
    page_title="WOS #3817 Analytics",
    page_icon="🛡️",
    layout="wide"
)

# ==========================================
# 1. DATA LOADING WITH CACHING
# ==========================================
@st.cache_data(ttl=60)
def load_data():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # Load GCP Credentials from Streamlit Secrets
    creds_dict = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    
    sheet = client.open("WOS_State_3817_Leaderboards").sheet1
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    
    if not df.empty:
        # Data Cleaning & Type Conversion
        df['Rank'] = pd.to_numeric(df['Rank'], errors='coerce')
        # Clean comma separators or non-numeric characters from Score
        df['Score_Clean'] = df['Score'].astype(str).str.replace(r'[^\d]', '', regex=True)
        df['Score_Clean'] = pd.to_numeric(df['Score_Clean'], errors='coerce')
        df['Submission_Date'] = pd.to_datetime(df['Submission_Date'])
        
    return df

st.title("🛡️ Whiteout Survival State #3817 - Leaderboard Analytics")

try:
    df = load_data()
    
    if df.empty:
        st.warning("No leaderboard data recorded yet!")
        st.stop()

    # ==========================================
    # 2. SIDEBAR FILTERS
    # ==========================================
    st.sidebar.header("🔍 Filters")
    
    # Event Filter
    available_events = ["All Events"] + list(df['Event_Name'].dropna().unique())
    selected_event = st.sidebar.selectbox("Select Event", available_events)
    
    # Apply Event Filter
    filtered_df = df.copy()
    if selected_event != "All Events":
        filtered_df = filtered_df[filtered_df['Event_Name'] == selected_event]
        
    # Player Search / Multiselect
    available_players = sorted(list(filtered_df['Player_Name'].dropna().unique()))
    selected_players = st.sidebar.multiselect(
        "Select Players to Compare", 
        options=available_players,
        default=available_players[:3] if len(available_players) >= 3 else available_players
    )

    # ==========================================
    # 3. INTERACTIVE PLOTLY CHARTS
    # ==========================================
    if selected_players:
        player_df = filtered_df[filtered_df['Player_Name'].isin(selected_players)]
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📈 Rank Progression (Top Rank = 1)")
            
            # Rank Progression Chart (Inverted Y-Axis)
            fig_rank = px.line(
                player_df,
                x='Submission_Date',
                y='Rank',
                color='Player_Name',
                markers=True,
                hover_data=['Event_Name', 'Score'],
                title="Rank Tracking Over Time"
            )
            
            # Invert Y-axis so Rank #1 sits at the very top of the graph
            fig_rank.update_yaxes(autorange="reversed", dtick=1)
            fig_rank.update_layout(
                xaxis_title="Date",
                yaxis_title="Rank Position",
                hovermode="x unified",
                legend_title="Player"
            )
            st.plotly_chart(fig_rank, use_container_width=True)
            
        with col2:
            st.subheader("📊 Score Comparison")
            
            # Score Chart
            fig_score = px.bar(
                player_df,
                x='Submission_Date',
                y='Score_Clean',
                color='Player_Name',
                barmode='group',
                hover_data=['Event_Name', 'Rank'],
                title="Scores Achieved Per Event Date"
            )
            
            fig_score.update_layout(
                xaxis_title="Date",
                yaxis_title="Score",
                hovermode="x unified",
                legend_title="Player"
            )
            st.plotly_chart(fig_score, use_container_width=True)

    else:
        st.info("👈 Please select at least one player from the sidebar to view charts.")

    # ==========================================
    # 4. RAW DATA TABLE
    # ==========================================
    st.markdown("---")
    st.subheader("📋 Leaderboard Records Table")
    st.dataframe(
        filtered_df[['Event_Name', 'Rank', 'Player_Name', 'Score', 'Submission_Date']].sort_values(
            by=['Submission_Date', 'Rank'], ascending=[False, True]
        ),
        use_container_width=True
    )

except Exception as e:
    st.error(f"❌ Error displaying analytics dashboard: {e}")
