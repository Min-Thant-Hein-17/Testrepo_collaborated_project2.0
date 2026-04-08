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

# Custom CSS for styling
st.markdown("""
<style>
    html { scroll-behavior: smooth; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem; }
    .row-style {
        padding: 10px;
        border-bottom: 1px solid rgba(128, 128, 128, 0.2);
    }
    .row-style:hover { background-color: rgba(128, 128, 128, 0.05); }
</style>
""", unsafe_allow_html=True)

# 2. Session State Initialization
if 'stellar_data' not in st.session_state:
    st.session_state.stellar_data = None
if 'display_name' not in st.session_state:
    st.session_state.display_name = ""
if 'target_id' not in st.session_state:  
    st.session_state.target_id = ""
if 'analysis_months' not in st.session_state:
    url_months = st.query_params.get("months")
    st.session_state.analysis_months = int(url_months) if (url_months and url_months.isdigit()) else 1

# --- DIALOGUE BOX COMPONENT ---
@st.dialog("Counterparty Transaction History", width="large")
def show_account_history_dialog(account_id, name):
    st.write(f"### Investigating: {name}")
    st.caption(f"Address: {account_id}")
    
    months = st.session_state.analysis_months
    with st.spinner("Fetching blockchain data..."):
        # We use a separate call here for the dialog
        detail_data = analyze_stellar_account(account_id, months=months)
    
    if detail_data:
        df_detail = pd.DataFrame(detail_data)
        st.write(f"Found {len(df_detail)} transactions in the last {months} month(s).")
        
        # Display a clean dataframe for quick inspection
        st.dataframe(
            df_detail[['timestamp', 'direction', 'amount', 'asset', 'other_account']],
            use_container_width=True,
            hide_index=True
        )
    else:
        st.warning("No transaction history found for this account in the selected timeframe.")
    
    if st.button("Close and Go Back"):
        st.rerun()

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
                return True
        st.error("Account details or transactions not found.")
        return False

# 3. Sidebar Configuration
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
    fetch_cached_analysis.clear()
    st.rerun()

# 4. Main Dashboard
if st.session_state.stellar_data:
    st.title(f"{st.session_state.display_name}*nugpay.app 🪙")
    
    # --- KPI SECTION ---
    dmmk_bal, nusdt_bal = fetch_balances(st.session_state.target_id)
    b1, b2, _ = st.columns([1, 1, 2])
    b1.metric("Current DMMK Balance", f"{dmmk_bal:,.2f}")
    b2.metric("Current nUSDT Balance", f"{nusdt_bal:,.7f}")
    st.markdown("---")

    df = pd.DataFrame(st.session_state.stellar_data)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # --- FILTERS ---
    st.subheader("Interactive Filters")
    selected_assets = st.pills("Filter Assets", options=["DMMK", "nUSDT"], default=["DMMK", "nUSDT"], selection_mode="multi")

    filtered_df = df.copy()
    if not selected_assets:
        st.info("Select an asset to view data.")
    elif filtered_df.empty:
        st.warning("No data found.")
    else:
        # --- TRANSACTION TABLE (WITH BUTTONS) ---
        st.write("**Transaction History**")
        
        # Header Row
        h_col1, h_col2, h_col3, h_col4, h_col5, h_col6 = st.columns([2, 1, 2, 1, 1, 1])
        h_col1.write("**Date/Time**")
        h_col2.write("**Direction**")
        h_col3.write("**Other Account**")
        h_col4.write("**Amount**")
        h_col5.write("**Asset**")
        h_col6.write("**Actions**")
        st.markdown("---")

        # Data Rows
        for i, row in filtered_df.iterrows():
            r_col1, r_col2, r_col3, r_col4, r_col5, r_col6 = st.columns([2, 1, 2, 1, 1, 1])
            
            r_col1.write(row['timestamp'].strftime('%Y-%m-%d %H:%M:%S'))
            r_col2.write(row['direction'])
            r_col3.write(str(row['other_account']))
            
            amt_str = f"{row['amount']:,.2f}" if row['asset'] == "DMMK" else f"{row['amount']:,.7f}"
            r_col4.write(amt_str)
            r_col5.write(row['asset'])
            
            # THE DIALOGUE BUTTON
            if r_col6.button("🔍 View", key=f"btn_{i}_{row['other_account_id']}"):
                show_account_history_dialog(row['other_account_id'], row['other_account'])

        # --- EXPORT SECTION ---
        st.markdown("### Export Data")
        csv_data = filtered_df.to_csv(index=False).encode('utf-8')
        st.download_button("⬇️ Download History (CSV)", csv_data, "history.csv", "text/csv")

else:
    st.title("NUGpay User Analytics")
    st.info("Enter an Account Name or ID in the sidebar to begin.")
