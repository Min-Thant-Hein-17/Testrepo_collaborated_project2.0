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

# Custom CSS for UI
st.markdown("""
<style>
    html { scroll-behavior: smooth; }
    table.dataframe { width: 100%; border-collapse: collapse; border: none; font-family: sans-serif; }
    table.dataframe th, table.dataframe td { padding: 10px 12px; border-bottom: 1px solid rgba(128, 128, 128, 0.2); text-align: left; }
    table.dataframe th { font-size: 14px; color: rgba(128, 128, 128, 0.8); font-weight: 600; }
    table.dataframe tr:hover { background-color: rgba(128, 128, 128, 0.1); }
    a.account-link { text-decoration: none; color: #1f77b4; font-weight: 600; }
    a.account-link:hover { text-decoration: underline; }
    .subtle-jump { font-size: 0.85rem; color: #1f77b4 !important; text-decoration: none; border-bottom: 1px dashed #1f77b4; display: inline-block; margin-top: 5px; }
    .back-top { font-size: 0.8rem; color: #aaa !important; text-decoration: none; float: right; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem; }
</style>
""", unsafe_allow_html=True)

# 2. Session State Initialization
if 'stellar_data' not in st.session_state: st.session_state.stellar_data = None
if 'display_name' not in st.session_state: st.session_state.display_name = ""
if 'target_id' not in st.session_state: st.session_state.target_id = ""
if 'history_stack' not in st.session_state: st.session_state.history_stack = []
if 'analysis_months' not in st.session_state: st.session_state.analysis_months = 1
if 'last_nav_type' not in st.session_state: st.session_state.last_nav_type = "initial"

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

def load_account_data(identifier, months, save_to_history=True):
    # Save current state to history before loading new one
    if save_to_history and st.session_state.target_id and st.session_state.target_id != identifier:
        st.session_state.history_stack.append({
            "id": st.session_state.target_id,
            "name": st.session_state.display_name,
            "months": st.session_state.analysis_months
        })

    with st.spinner(f"Resolving {identifier}..."):
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
                st.session_state.analysis_months = months
                st.query_params["target_account"] = target_id
                st.query_params["months"] = str(months)
                return True
    return False

# Detect Blue Link clicks
url_target = st.query_params.get("target_account")
if url_target and st.session_state.target_id != url_target:
    if st.session_state.last_nav_type != "back":
        url_m = int(st.query_params.get("months", 1))
        load_account_data(url_target, url_m, save_to_history=True)
    st.session_state.last_nav_type = "forward"

# 3. Sidebar
st.sidebar.header("Configuration")
input_method = st.sidebar.radio("Search By", ["Account Name", "Account ID"])
user_input = st.sidebar.text_input("Enter Name/ID", value=st.session_state.display_name if input_method == "Account Name" else st.session_state.target_id)

# Timeframe slider linked to session state
analysis_months = st.sidebar.slider("Timeframe (Months)", 1, 12, value=st.session_state.analysis_months)

col_side1, col_side2 = st.sidebar.columns(2)
if col_side1.button("Analyze Account", use_container_width=True) and user_input:
    st.session_state.last_nav_type = "forward"
    load_account_data(user_input, analysis_months, save_to_history=True)
    st.rerun()

if col_side2.button("Clear Cache", use_container_width=True):
    st.session_state.clear()
    st.query_params.clear()
    st.rerun()

# 4. Main Dashboard
st.markdown("<div id='top-anchor'></div>", unsafe_allow_html=True)

# THE BACK BUTTON
if st.session_state.history_stack:
    prev = st.session_state.history_stack[-1]
    if st.button(f"← Back to {prev['name']}", key="nav_back_btn"):
        st.session_state.last_nav_type = "back"
        last_item = st.session_state.history_stack.pop()
        # Restore the previous ID and the timeframe it was using
        load_account_data(last_item['id'], last_item['months'], save_to_history=False)
        st.rerun()

if st.session_state.display_name:
    st.title(f"{st.session_state.display_name}*nugpay.app 🪙")
else:
    st.title("NUGpay User Analytics")

if st.session_state.stellar_data:
    df = pd.DataFrame(st.session_state.stellar_data)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['month_year'] = df['timestamp'].dt.strftime('%B %Y')
    df['day'] = df['timestamp'].dt.day

    # --- KPI SECTION ---
    st.subheader("Current Balance")
    d_bal, n_bal = fetch_balances(st.session_state.target_id)
    b1, b2, _ = st.columns([1, 1, 2])
    b1.metric("DMMK", f"{d_bal:,.2f}")
    b2.metric("nUSDT", f"{n_bal:,.7f}")
    st.markdown("---")

    # --- INTERACTIVE FILTERS RESTORED ---
    st.subheader("Interactive Filters")
    f_mode = st.radio("Date Filter Mode", ["Standard (Month/Week)", "Custom Date Range"], horizontal=True)
    
    t1, t2, t3 = st.columns(3)
    start_date, end_date = None, None

    if f_mode == "Standard (Month/Week)":
        with t1:
            m_list = df.sort_values('timestamp', ascending=False)['month_year'].unique().tolist()
            sel_m = st.selectbox("Filter by Month", ["All Months"] + m_list)
        with t2:
            if sel_m == "All Months":
                sel_w = st.selectbox("Filter by Week", ["All Weeks"], disabled=True)
            else:
                m_parts = sel_m.split(" ")
                m_idx = list(calendar.month_name).index(m_parts[0])
                _, last_day = calendar.monthrange(int(m_parts[1]), m_idx)
                w_list = ["1 - 7 (First Week)", "8 - 14 (Second Week)", "15 - 21 (Third Week)", f"22 - {last_day} (Fourth Week)"]
                sel_w = st.selectbox("Filter by Week", ["All Weeks"] + w_list)
    else:
        with t1:
            dr = st.date_input("Select Range", value=(df['timestamp'].min().date(), df['timestamp'].max().date()))
            if isinstance(dr, tuple) and len(dr) == 2: start_date, end_date = dr

    with t3:
        rec = st.radio("Quick Tracker", ["Full History", "Last 7 Days", "Last 24 Hours"], horizontal=True)
        st.markdown('<a href="#summary-section" class="subtle-jump">Jump to Account Summary</a>', unsafe_allow_html=True)

    assets = st.pills("Filter Assets", options=["DMMK", "nUSDT"], default=["DMMK", "nUSDT"], selection_mode="multi")

    # --- FILTER LOGIC ---
    f_df = df.copy()
    if f_mode == "Standard (Month/Week)":
        if sel_m != "All Months":
            f_df = f_df[f_df['month_year'] == sel_m]
            if sel_w != "All Weeks":
                bounds = sel_w.split(" (")[0].split(" - ")
                f_df = f_df[f_df['day'].between(int(bounds[0]), int(bounds[1]))]
    elif start_date and end_date:
        f_df = f_df[(f_df['timestamp'].dt.date >= start_date) & (f_df['timestamp'].dt.date <= end_date)]
    
    now = datetime.now(timezone.utc)
    if rec == "Last 7 Days": f_df = f_df[f_df['timestamp'] >= (now - timedelta(days=7))]
    elif rec == "Last 24 Hours": f_df = f_df[f_df['timestamp'] >= (now - timedelta(hours=24))]

    f_df = f_df[f_df['asset'].isin(assets)]

    if f_df.empty:
        st.warning("No data found for this selection.")
    else:
        # --- TRANSACTION TABLE ---
        disp = f_df.copy()
        disp['Date/Time'] = disp['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
        
        def create_link(row):
            q_name = urllib.parse.quote(str(row['other_account']))
            return f'<a class="account-link" href="/?target_account={row["other_account_id"]}&name={q_name}&months={st.session_state.analysis_months}" target="_self">{row["other_account"]}</a>'
        
        disp['Account'] = disp.apply(create_link, axis=1)
        disp['Amount_Disp'] = disp.apply(lambda r: f"{r['amount']:,.2f}" if r['asset'] == "DMMK" else f"{r['amount']:,.7f}", axis=1)
        
        st.write("**Transaction History**")
        st.markdown(disp[['Date/Time', 'direction', 'Account', 'Amount_Disp', 'asset']].rename(columns={'direction':'Direction','Amount_Disp':'Amount','asset':'Asset'}).to_html(escape=False, index=False, classes="dataframe"), unsafe_allow_html=True)
        
        # --- SUMMARY SECTION ---
        st.markdown("<div id='summary-section' style='padding-top:20px;'></div>", unsafe_allow_html=True)
        st.markdown("---")
        st.subheader("Summary by Account")
        
        f_df['In'] = f_df.apply(lambda x: x['amount'] if x['direction'] == "INCOMING" else 0, axis=1)
        f_df['Out'] = f_df.apply(lambda x: x['amount'] if x['direction'] == "OUTGOING" else 0, axis=1)

        summary = f_df.groupby(['other_account', 'other_account_id', 'asset']).agg(
            Outgoing=('Out', 'sum'), Incoming=('In', 'sum'),
            Total_Volume=('amount', 'sum'), Tx_Count=('amount', 'count')
        ).reset_index().sort_values('Total_Volume', ascending=False).head(10)

        disp_sum = summary.copy()
        disp_sum['Account'] = disp_sum.apply(create_link, axis=1)
        for c in ['Total_Volume', 'Incoming', 'Outgoing']: disp_sum[c] = disp_sum[c].apply(lambda x: f"{x:,.2f}")
        
        st.markdown(disp_sum[['Account', 'asset', 'Total_Volume', 'Incoming', 'Outgoing', 'Tx_Count']].to_html(escape=False, index=False, classes="dataframe"), unsafe_allow_html=True)

        st.markdown('<a href="#top-anchor" class="back-top">↑ Back to Top</a>', unsafe_allow_html=True)
else:
    st.info("Search for an account to get started.")
