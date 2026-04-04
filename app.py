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

# Custom CSS for UI styling
st.markdown("""
<style>
    html { scroll-behavior: smooth; }
    table.dataframe { width: 100%; border-collapse: collapse; border: none; font-family: sans-serif; }
    table.dataframe th, table.dataframe td { padding: 10px 12px; border-bottom: 1px solid rgba(128, 128, 128, 0.2); text-align: left; }
    table.dataframe th { font-size: 14px; color: rgba(128, 128, 128, 0.8); font-weight: 600; }
    table.dataframe tr:hover { background-color: rgba(128, 128, 128, 0.1); }
    a.account-link { text-decoration: none; color: #1f77b4; font-weight: 600; cursor: pointer; }
    a.account-link:hover { text-decoration: underline; }
    .subtle-jump { font-size: 0.85rem; color: #1f77b4 !important; text-decoration: none; border-bottom: 1px dashed #1f77b4; display: inline-block; margin-top: 5px; }
    .back-top { font-size: 0.8rem; color: #aaa !important; text-decoration: none; float: right; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem; }
    .stButton button { width: auto; }
</style>
""", unsafe_allow_html=True)

# 2. Session State Initialization
if 'stellar_data' not in st.session_state: st.session_state.stellar_data = None
if 'display_name' not in st.session_state: st.session_state.display_name = ""
if 'target_id' not in st.session_state: st.session_state.target_id = ""
if 'history_stack' not in st.session_state: st.session_state.history_stack = []

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

def load_account_data(identifier, months, is_back_nav=False):
    """Core function to navigate between accounts and manage the history stack."""
    # 1. Capture current state to history stack BEFORE switching (if moving forward)
    if not is_back_nav and st.session_state.target_id and st.session_state.target_id != identifier:
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
                # Persist state in URL
                st.query_params["target_account"] = target_id
                st.query_params["name"] = current_name
                st.query_params["months"] = str(months)
                return True
    return False

# --- CRITICAL: INTERCEPT LINK CLICKS BEFORE SIDEBAR RENDER ---
url_target = st.query_params.get("target_account")
if url_target and url_target != st.session_state.target_id:
    load_account_data(url_target, int(st.query_params.get("months", st.session_state.analysis_months)))
    st.rerun()

# 3. Sidebar
st.sidebar.header("Configuration")
input_method = st.sidebar.radio("Search By", ["Account Name", "Account ID"])
if input_method == "Account Name":
    user_input = st.sidebar.text_input("Enter Name", value=st.session_state.display_name)
else:
    user_input = st.sidebar.text_input("Enter Account ID", value=st.session_state.target_id)

analysis_months = st.sidebar.slider("Timeframe (Months)", 1, 12, st.session_state.analysis_months)
st.session_state.analysis_months = analysis_months 

col_side1, col_side2 = st.sidebar.columns(2)
if col_side1.button("Analyze Account", use_container_width=True) and user_input:
    load_account_data(user_input, analysis_months)
    st.rerun()

if col_side2.button("Clear Cache", use_container_width=True):
    st.session_state.clear()
    st.query_params.clear()
    st.rerun()

# 4. Main Dashboard
st.markdown("<div id='top-anchor'></div>", unsafe_allow_html=True)

# THE BACK BUTTON (Restores the Dashboard of the PREVIOUS account)
if st.session_state.history_stack:
    prev = st.session_state.history_stack[-1]
    if st.button(f"← Back to {prev['name']}", key="nav_back_btn"):
        last_item = st.session_state.history_stack.pop()
        load_account_data(last_item['id'], last_item['months'], is_back_nav=True)
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
    d1, n1 = fetch_balances(st.session_state.target_id)
    b1, b2, _ = st.columns([1, 1, 2])
    b1.metric("DMMK", f"{d1:,.2f}")
    b2.metric("nUSDT", f"{n1:,.7f}")
    st.markdown("---")

    # --- FILTERS ---
    st.subheader("Interactive Filters")
    filter_mode = st.radio("Date Filter Mode", ["Standard (Month/Week)", "Custom Date Range"], horizontal=True)
    t1, t2, t3 = st.columns(3)
    start_date, end_date = None, None

    if filter_mode == "Standard (Month/Week)":
        with t1:
            m_list = df.sort_values('timestamp', ascending=False)['month_year'].unique().tolist()
            sel_month = st.selectbox("Filter by Month", ["All Months"] + m_list)
        with t2:
            if sel_month != "All Months":
                m_parts = sel_month.split(" ")
                m_idx = list(calendar.month_name).index(m_parts[0])
                _, last_day = calendar.monthrange(int(m_parts[1]), m_idx)
                w_list = ["1 - 7 (W1)", "8 - 14 (W2)", "15 - 21 (W3)", f"22 - {last_day} (W4)"]
                sel_week = st.selectbox("Filter by Week", ["All Weeks"] + w_list)
            else:
                st.selectbox("Filter by Week", ["All Weeks"], disabled=True)
    else:
        with t1:
            dr = st.date_input("Select Range", value=(df['timestamp'].min().date(), df['timestamp'].max().date()))
            if isinstance(dr, tuple) and len(dr) == 2: start_date, end_date = dr

    with t3:
        recency = st.radio("Quick Tracker", ["Full History", "Last 7 Days", "Last 24 Hours"], horizontal=True)
        st.markdown('<a href="#summary-section" class="subtle-jump">Jump to Account Summary</a>', unsafe_allow_html=True)

    selected_assets = st.pills("Filter Assets", options=["DMMK", "nUSDT"], default=["DMMK", "nUSDT"], selection_mode="multi")

    # Applying Logic
    filtered_df = df.copy()
    if filter_mode == "Standard (Month/Week)" and sel_month != "All Months":
        filtered_df = filtered_df[filtered_df['month_year'] == sel_month]
        if 'sel_week' in locals() and sel_week != "All Weeks":
            bounds = sel_week.split(" (")[0].split(" - ")
            filtered_df = filtered_df[filtered_df['day'].between(int(bounds[0]), int(bounds[1]))]
    elif start_date and end_date:
        filtered_df = filtered_df[(filtered_df['timestamp'].dt.date >= start_date) & (filtered_df['timestamp'].dt.date <= end_date)]
    
    now = datetime.now(timezone.utc)
    if recency == "Last 7 Days": filtered_df = filtered_df[filtered_df['timestamp'] >= (now - timedelta(days=7))]
    elif recency == "Last 24 Hours": filtered_df = filtered_df[filtered_df['timestamp'] >= (now - timedelta(hours=24))]
    
    filtered_df = filtered_df[filtered_df['asset'].isin(selected_assets)]

    if filtered_df.empty:
        st.warning("No data found for this selection.")
    else:
        # --- TRANSACTION TABLE ---
        display_df = filtered_df.copy()
        display_df['Date/Time'] = display_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
        def create_link(row):
            safe_name = urllib.parse.quote(str(row['other_account']))
            return f'<a class="account-link" href="/?target_account={row["other_account_id"]}&name={safe_name}&months={st.session_state.analysis_months}" target="_self">{row["other_account"]}</a>'
        
        display_df['Other Account'] = display_df.apply(create_link, axis=1)
        display_df['Amount_Disp'] = display_df.apply(lambda r: f"{r['amount']:,.2f}" if r['asset'] == "DMMK" else f"{r['amount']:,.7f}", axis=1)
        st.write("**Transaction History**")
        st.markdown(display_df[['Date/Time', 'direction', 'Other Account', 'Amount_Disp', 'asset']].rename(columns={'direction':'Direction','Amount_Disp':'Amount','asset':'Asset'}).to_html(escape=False, index=False, classes="dataframe"), unsafe_allow_html=True)

        # --- SUMMARY SECTION ---
        st.markdown("<div id='summary-section' style='padding-top:20px;'></div>", unsafe_allow_html=True)
        st.markdown("---")
        st.subheader("Summary by Account")
        
        s1, s2 = st.columns([2, 1])
        sort_metric = s1.selectbox("Sort Summary By", options=["Tx_Count", "Total_Volume", "Net_Difference", "Incoming", "Outgoing"])
        sort_order = s2.radio("Order", ["Ascending", "Descending"], index=1, horizontal=True)
        
        filtered_df['Incoming'] = filtered_df.apply(lambda x: x['amount'] if x['direction'] == "INCOMING" else 0, axis=1)
        filtered_df['Outgoing'] = filtered_df.apply(lambda x: x['amount'] if x['direction'] == "OUTGOING" else 0, axis=1)

        account_summary = filtered_df.groupby(['other_account', 'other_account_id', 'asset']).agg(
            Outgoing=('Outgoing', 'sum'), Incoming=('Incoming', 'sum'),
            Total_Volume=('amount', 'sum'), Tx_Count=('amount', 'count')
        ).reset_index()
        account_summary['Net_Difference'] = account_summary['Incoming'] - account_summary['Outgoing']
        account_summary = account_summary.sort_values(sort_metric, ascending=(sort_order == "Ascending")).head(10)

        disp_sum = account_summary.copy()
        disp_sum['Other Account'] = disp_sum.apply(create_link, axis=1)
        for c in ['Total_Volume', 'Incoming', 'Outgoing', 'Net_Difference']: disp_sum[c] = disp_sum[c].apply(lambda x: f"{x:,.2f}")
        
        st.markdown(disp_sum[['Other Account', 'asset', 'Total_Volume', 'Incoming', 'Outgoing', 'Net_Difference', 'Tx_Count']].to_html(escape=False, index=False, classes="dataframe"), unsafe_allow_html=True)

        # --- EXPORT BUTTONS ---
        csv_h = filtered_df[['timestamp', 'direction', 'other_account', 'other_account_id', 'amount', 'asset']].to_csv(index=False).encode('utf-8')
        st.download_button("⬇️ Export History (CSV)", csv_h, f"{st.session_state.display_name}_history.csv", "text/csv")
        st.markdown('<a href="#top-anchor" class="back-top">↑ Back to Top</a>', unsafe_allow_html=True)
else:
    st.info("Enter an Account Name or ID in the sidebar to begin.")
