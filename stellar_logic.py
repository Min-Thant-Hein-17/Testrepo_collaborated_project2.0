import pandas as pd
from datetime import datetime, timedelta, timezone
from stellar_sdk import Server
from decimal import Decimal, getcontext
import requests
import concurrent.futures
from functools import lru_cache

# Fixed-point precision for blockchain math
getcontext().prec = 28 

# Blockdaemon Private API Configuration
BLOCKDAEMON_API_KEY = "zpka_12ec9c7e59a64e369d8bccf69fcc5efc_0f65de58"

@lru_cache(maxsize=1)
def get_federation_server():
    """Fetches the federation URL dynamically and caches the result."""
    try:
        url = "https://nugpay.app/.well-known/stellar.toml"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            for line in response.text.splitlines():
                if "FEDERATION_SERVER" in line:
                    return line.split("=")[1].strip(' "\'')
    except Exception as e:
        print(f"TOML fetch error: {e}")
    return None

def resolve_username_to_id(username):
    """Translates 'name' or 'name*domain' into a G-Address."""
    if not username: return None
    
    full_address = username if "*" in username else f"{username}*nugpay.app"
    domain = full_address.split("*")[1]
    
    try:
        toml_url = f"https://{domain}/.well-known/stellar.toml"
        res = requests.get(toml_url, timeout=5)
        fed_url = None
        if res.status_code == 200:
            for line in res.text.splitlines():
                if "FEDERATION_SERVER" in line:
                    fed_url = line.split("=")[1].strip(' "\'')
                    break
        
        if fed_url:
            query = f"{fed_url}?q={full_address}&type=name"
            api_res = requests.get(query, timeout=5)
            if api_res.status_code == 200:
                return api_res.json().get("account_id")
    except Exception as e:
        print(f"Forward lookup error: {e}")
    return None

def resolve_id_to_name(account_id):
    """Translates a G-Address back into a username."""
    fed_url = get_federation_server()
    if not fed_url: return None
    try:
        url = f"{fed_url}?q={account_id}&type=id"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            addr = res.json().get("stellar_address", "")
            return addr.split("*")[0] if "*" in addr else None
    except:
        pass
    return None

@lru_cache(maxsize=2048)
def fetch_account_name(account_id, federation_url):
    """Fetches a single name and caches it globally in memory."""
    if not account_id or len(account_id) < 16: return account_id
    if federation_url:
        url = f"{federation_url}?q={account_id}&type=id"
        try:
            response = requests.get(url, timeout=3)
            if response.status_code == 200:
                stellar_address = response.json().get("stellar_address", "")
                if stellar_address and "*" in stellar_address:
                    return stellar_address.split("*")[0]
        except:
            pass
    return f"{account_id[:8]}*******{account_id[-8:]}"

def analyze_stellar_account(account_id, months=1):
    """Analyzes account history using Blockdaemon Ubiquity for all-time data access."""
    now_utc = datetime.now(timezone.utc)
    start_date = now_utc - timedelta(days=30 * months)
    
    federation_url = get_federation_server()
    
    raw_data = []
    unique_other_accounts = set()
    
    # Blockdaemon Ubiquity API Endpoint
    # This bypasses the 1-year limitation of standard Horizon nodes
    base_url = f"https://svc.blockdaemon.com/ubiquity/v1/stellar/mainnet/account/{account_id}/txs"
    headers = {
        "X-API-Key": BLOCKDAEMON_API_KEY,
        "accept": "application/json"
    }
    
    try:
        response = requests.get(base_url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"Blockdaemon API Error: {response.status_code}")
            return None
            
        items = response.json().get('items', [])

        # Step 1: Collect transactions from Blockdaemon items
        for tx in items:
            # Blockdaemon provides 'date' as a unix timestamp
            dt = datetime.fromtimestamp(tx['date'], tz=timezone.utc)
            
            if dt < start_date:
                continue
                
            # Each transaction can contain multiple events/transfers
            for event in tx.get('events', []):
                asset_code = event.get('asset_code')
                if asset_code not in ["DMMK", "nUSDT"]: continue

                raw_val = Decimal(event.get('amount', '0'))
                final_val = raw_val * Decimal('1000') if asset_code == "DMMK" else raw_val
                
                is_sender = event.get('from') == account_id
                raw_other_account = event.get('to') if is_sender else event.get('from')
                
                unique_other_accounts.add(raw_other_account)
                
                raw_data.append({
                    "timestamp": dt,
                    "date": dt.date(),
                    "month_name": dt.strftime("%B"),
                    "week_num": f"Week {dt.isocalendar()[1]}",
                    "direction": "OUTGOING" if is_sender else "INCOMING",
                    "other_account_id": raw_other_account,
                    "amount": float(final_val),
                    "asset": asset_code
                })
            
        # Step 2: Resolve names concurrently (Multithreading)
        name_mapping = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = {executor.submit(fetch_account_name, acc, federation_url): acc for acc in unique_other_accounts}
            for future in concurrent.futures.as_completed(futures):
                acc_id = futures[future]
                name_mapping[acc_id] = future.result()
                
        # Step 3: Map the names back to the records
        for row in raw_data:
            row["other_account"] = name_mapping.get(row["other_account_id"], row["other_account_id"])
            
        return raw_data
    except Exception as e:
        print(f"Blockdaemon Processing Error: {e}")
        return None
