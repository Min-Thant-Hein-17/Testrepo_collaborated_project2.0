import streamlit as st
import pandas as pd
import urllib.parse
import calendar
from datetime import datetime, timezone, timedelta
from stellar_sdk import Server
from stellar_logic import (
    analyze_stellar_account, 
    resolve_username_to_id, 
    resolve_id_to_name
)

# 1. Page Configuration
st.set_page_config(page_title="NUGpay Pro Dashboard", layout="wide")

# Custom CSS (Original preserved)
st.markdown("""
<style>
    html { scroll-behavior: smooth; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem; }
    /* Style for the row alignment */
    .row-container {
        padding: 5px 0px;
        border-bottom: 1px solid rgba(128, 128, 128, 0.2);
        display: flex;
        align-items: center;
    }
</style>
""", unsafe_allow_html=True)

# --- NEW DIALOGUE BOX FUNCTION ---
@st.dialog("Account Investigation", width="large")
def show_account_details_dialog(account_id, name):
    st.write(f"Detailed Transaction History for: **{name}**")
    st.info(f"Address: {account_id}")
    
    # Use your existing logic to fetch data for this specific account
    with st.spinner("Fetching full history..."):
        # We use the same month timeframe as the main dashboard
        details = analyze_stellar_account(account_id, months=st.session_state.analysis_months)
    
    if details:
        det_df = pd.DataFrame(details)
        # Display as a clean dataframe for quick analysis
        st.dataframe(
            det_df[['timestamp', 'direction', 'amount', 'asset', 'other_account']], 
            use_container_width=True,
            hide_index=True
        )
    else:
        st.warning("No transaction history found for this account within the selected timeframe.")
    
    if st.button("Close and Go Back"):
        st.rerun()

# 2. Session State Initialization (Original preserved)
if 'stellar_data' not in st.session_state:
    st.session_state.stellar_data = None
if 'display_name' not in st.session_state:
    st.session_state.display_name = ""
if 'target_id' not in st.session_state:  
    st.session_state.target_id = ""
if 'analysis_months' not in st.session_state:
    url_months = st.query_params.get("months")
    st.session_state.analysis_months = int(url_months) if (url_months and url_months.isdigit()) else 1

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_cached_analysis(target_id, months):
    return analyze_stellar_account(target_id, months=months)

@st.cache_data(ttl=300, show_spinner=False)
def fetch_balances(account_id):
    if not account_id: return 0.0, 0.0
    server = Server("https://horizon.stellar.org")
    try:
        account = server.accounts().account_id(account_id).call()
        balances = account.get('balances', [])
        dmmk, nusdt = 0.0, 0.0
        for b in balances:
            asset_code = b.get('asset_code')
            balance = float(b.get('balance', 0))
            if asset_code == 'DMMK': dmmk = balance * 1000.0  
            elif asset_code == 'nUSDT': nusdt = balance
        return dmmk, nusdt
    except Exception: return 0.0, 0.0

def load_account_data(identifier, months):
    with st.spinner(f"Resolving identity and fetching history for {identifier}..."):
        target_id = None
        current_name = identifier
        if identifier.startswith("G") and len(identifier) == 56:
            target_id = identifier
            found_name = resolve_id_to_name(identifier)
            if found_name: current_name = found_name
        else:
            target_id = resolve_username_to_id(identifier)
        
        if target_id:
            data = fetch_cached_analysis(target_id, months)
            if data:
                st.session_state.stellar_data = data
                st.session_state.display_name = current_name
                st.session_state.target_id = target_id 
                st.query_params["target_account"] = target_id
                st.query_params["name"] = current_name
                st.query_params["months"] = str(months)
                return True
        st.error("Account details or transactions not found.")
        return False

# URL Check (Original preserved)
target_from_url = st.query_params.get("target_account")
if target_from_url and st.session_state.display_name != st.query_params.get("name"):
    load_account_data(target_from_url, st.session_state.analysis_months)

# 3. Sidebar Configuration (Original preserved)
st.sidebar.header("Configuration")
input_method = st.sidebar.radio("Search By", ["Account Name", "Account ID"])

if input_method == "Account Name":
    user_input = st.sidebar.text_input("Enter Name", value=st.session_state.display_name, placeholder="e.g. sithu")
else:
    user_input = st.sidebar.text_input("Enter Account ID", value=st.session_state.target_id, placeholder="G...")

analysis_months = st.sidebar.slider("Timeframe (Months)", 1, 12, st.session_state.analysis_months)
st.session_state.analysis_months = analysis_months 

col_side1, col_side2 = st.sidebar.columns(2)
if col_side1.button("Analyze Account", use_container_width=True) and user_input:
    load_account_data(user_input, analysis_months)
if col_side2.button("Clear Cache", use_container_width=True):
    st.session_state.stellar_data = None
    st.session_state.display_name = ""
    st.session_state.target_id = "" 
    st.query_params.clear()
    fetch_cached_analysis.clear()
    st.rerun()

# 4. Main Dashboard
st.markdown("<div id='top-anchor'></div>", unsafe_allow_html=True)
if st.session_state.display_name:
    st.title(f"{st.session_state.display_name}*nugpay.app 🪙")
else:
    st.title("NUGpay User Analytics")

if st.session_state.stellar_data:
    df = pd.DataFrame(st.session_state.stellar_data)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['month_year'] = df['timestamp'].dt.strftime('%B %Y')
    df['day'] = df['timestamp'].dt.day

    # --- KPI SECTION (Original preserved) ---
    st.subheader("Current Balance")
    dmmk_bal, nusdt_bal = fetch_balances(st.session_state.target_id)
    b1, b2, _ = st.columns([1, 1, 2])
    b1.metric("DMMK", f"{dmmk_bal:,.2f}")
    b2.metric("nUSDT", f"{nusdt_bal:,.7f}")
    st.markdown("---")

    # --- INTERACTIVE FILTERS (Original preserved) ---
    st.subheader("Interactive Filters")
    filter_mode = st.radio("Date Filter Mode", ["Standard (Month/Week)", "Custom Date Range"], horizontal=True)
    t1, t2, t3 = st.columns(3)
    start_date, end_date = None, None

    if filter_mode == "Standard (Month/Week)":
        with t1:
            available_months = df.sort_values('timestamp', ascending=False)['month_year'].unique().tolist()
            sel_month = st.selectbox("Filter by Month", ["All Months"] + available_months)
        with t2:
            if sel_month == "All Months":
                sel_week = st.selectbox("Filter by Week", ["All Weeks"], disabled=True)
            else:
                month_name, year_str = sel_month.split(" ")
                month_idx = list(calendar.month_name).index(month_name)
                _, last_day = calendar.monthrange(int(year_str), month_idx)
                dynamic_weeks = ["1 - 7 (First Week)", "8 - 14 (Second Week)", "15 - 21 (Third Week)", f"22 - {last_day} (Fourth Week)"]
                sel_week = st.selectbox("Filter by Week", ["All Weeks"] + dynamic_weeks)
    else:
        with t1:
            date_range = st.date_input("Select Range", value=(df['timestamp'].min().date(), df['timestamp'].max().date()))
            if isinstance(date_range, tuple) and len(date_range) == 2:
                start_date, end_date = date_range

    with t3:
        recency = st.radio("Quick Tracker", ["Full History", "Last 7 Days", "Last 24 Hours"], horizontal=True)

    selected_assets = st.pills("Filter Assets", options=["DMMK", "nUSDT"], default=["DMMK", "nUSDT"], selection_mode="multi")

    # Filter Application Logic
    filtered_df = df.copy()
    if filter_mode == "Standard (Month/Week)" and sel_month != "All Months":
        filtered_df = filtered_df[filtered_df['month_year'] == sel_month]
        if sel_week != "All Weeks":
            bounds = sel_week.split(" (")[0].split(" - ")
            filtered_df = filtered_df[filtered_df['day'].between(int(bounds[0]), int(bounds[1]))]
    elif start_date and end_date:
        filtered_df = filtered_df[(filtered_df['timestamp'].dt.date >= start_date) & (filtered_df['timestamp'].dt.date <= end_date)]
    
    # --- UPDATED TRANSACTION TABLE WITH BUTTONS ---
    st.write("**Transaction History**")
    if filtered_df.empty:
        st.warning("No data found for this selection.")
    else:
        # Create Table Header
        h_col1, h_col2, h_col3, h_col4, h_col5, h_col6 = st.columns([2, 1, 2, 1, 1, 1])
        h_col1.write("**Date/Time**")
        h_col2.write("**Direction**")
        h_col3.write("**Other Account**")
        h_col4.write("**Amount**")
        h_col5.write("**Asset**")
        h_col6.write("**Action**")

        # Iterate through rows to add buttons
        for index, row in filtered_df.iterrows():
            st.markdown('<div class="row-container">', unsafe_allow_html=True)
            c1, c2, c3, c4, c5, c6 = st.columns([2, 1, 2, 1, 1, 1])
            
            c1.write(row['timestamp'].strftime('%Y-%m-%d %H:%M:%S'))
            c2.write(row['direction'])
            c3.write(row['other_account'])
            
            # Format Amount based on Asset
            amt_str = f"{row['amount']:,.2f}" if row['asset'] == "DMMK" else f"{row['amount']:,.7f}"
            c4.write(amt_str)
            c5.write(row['asset'])
            
            # THE INVESTIGATE BUTTON
            if c6.button("🔍 Investigate", key=f"investigate_{index}", use_container_width=True):
                show_account_details_dialog(row['other_account_id'], row['other_account'])
            st.markdown('</div>', unsafe_allow_html=True)

        # --- SUMMARY SECTION (Original preserved) ---
        st.markdown("<div id='summary-section' style='padding-top:20px;'></div>", unsafe_allow_html=True)
        st.markdown("---")
        st.subheader("Summary by Account")
        
        summary_df = filtered_df.copy()
        summary_df['Incoming'] = summary_df.apply(lambda x: x['amount'] if x['direction'] == "INCOMING" else 0, axis=1)
        summary_df['Outgoing'] = summary_df.apply(lambda x: x['amount'] if x['direction'] == "OUTGOING" else 0, axis=1)

        account_summary = summary_df.groupby(['other_account', 'other_account_id', 'asset']).agg(
            Outgoing=('Outgoing', 'sum'), Incoming=('Incoming', 'sum'),
            Total_Volume=('amount', 'sum'), Tx_Count=('amount', 'count')
        ).reset_index()
        account_summary['Net_Difference'] = account_summary['Incoming'] - account_summary['Outgoing']
        
        # Display summary (Simple dataframe for cleanliness)
        st.dataframe(account_summary, use_container_width=True, hide_index=True)

        # --- EXPORT SECTION (Original preserved) ---
        st.markdown("### Export Data")
        ex_col1, ex_col2 = st.columns(2)
        with ex_col1:
            csv_hist = filtered_df.to_csv(index=False).encode('utf-8')
            st.download_button("⬇️ Export History", data=csv_hist, file_name="history.csv", mime="text/csv")
        with ex_col2:
            csv_sum = account_summary.to_csv(index=False).encode('utf-8')
            st.download_button("⬇️ Export Summary", data=csv_sum, file_name="summary.csv", mime="text/csv")

        st.markdown('---')
        st.markdown('<a href="#top-anchor" style="color:#aaa; text-decoration:none; float:right;">↑ Back to Top</a>', unsafe_allow_html=True)
else:
    st.info("Enter an Account Name or Account ID in the sidebar to begin.")
