import os
import pandas as pd
from datetime import datetime, timedelta, timezone
from stellar_sdk import Server
from stellar_sdk.client.requests_client import RequestsClient
from decimal import Decimal, getcontext
import requests
import concurrent.futures
from functools import lru_cache

# Fixed-point precision for blockchain math
getcontext().prec = 28 

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

def _extract_amount_and_parties(record):
    """
    FIX #2: Safely extract amount, sender, and receiver from a payment record
    regardless of operation type (payment, path_payment_strict_send/receive).
    Blockdaemon may return path_payment operations that have different field names.
    """
    op_type = record.get("type", "payment")

    # For path_payment_strict_send, the destination receives 'amount'
    # For path_payment_strict_receive, the source sends 'source_amount'
    # For regular payment, 'amount' is always present
    if op_type == "path_payment_strict_send":
        amount = record.get("amount", "0")          # amount received by destination
    elif op_type == "path_payment_strict_receive":
        amount = record.get("amount", "0")          # amount received; source_amount is what was sent
    else:
        amount = record.get("amount", "0")

    sender = record.get("from") or record.get("source_account", "")
    receiver = record.get("to") or record.get("destination", "")

    return amount, sender, receiver

def analyze_stellar_account(account_id, months=1):
    bd_api_key = os.environ.get("BLOCKDAEMON_API_KEY")
    bd_url = "https://svc.blockdaemon.com/stellar/mainnet/native"

    client = RequestsClient()
    if bd_api_key:
        # FIX: Stellar SDK uses '_session' internally, not 'session'
        session = getattr(client, '_session', None) or getattr(client, 'session', None)
        if session:
            session.headers.update({"Authorization": f"Bearer {bd_api_key}"})
        else:
            # Fallback: set auth via requests directly on whichever attr exists
            client._session = requests.Session()
            client._session.headers.update({"Authorization": f"Bearer {bd_api_key}"})
    else:
        print("WARNING: No BLOCKDAEMON_API_KEY found in environment. "
              "Blockdaemon requires a valid Bearer token — requests will be "
              "rejected with HTTP 401, which appears as empty results.")

    server = Server(bd_url, client=client)
    now_utc = datetime.now(timezone.utc)
    start_date = now_utc - timedelta(days=30 * months)
    
    federation_url = get_federation_server()
    
    raw_data = []
    unique_other_accounts = set()
    stop_fetching = False  # flag to break outer loop cleanly

    try:
        payments_call = (
            server.payments()
            .for_account(account_id)
            .order(desc=True)
            .limit(200)
        )

        # FIX #1: Robust first-page fetch with explicit error surfacing
        try:
            records = payments_call.call()
        except Exception as first_call_err:
            print(f"ERROR: Initial Blockdaemon call failed: {first_call_err}")
            print("Check that BLOCKDAEMON_API_KEY is set correctly and the "
                  "account ID is valid on Stellar mainnet.")
            return None

        # Step 1: Collect all transactions as fast as possible
        while not stop_fetching:
            page_records = records.get('_embedded', {}).get('records', [])
            if not page_records:
                break

            for record in page_records:
                dt = datetime.strptime(
                    record['created_at'], "%Y-%m-%dT%H:%M:%SZ"
                ).replace(tzinfo=timezone.utc)

                if dt < start_date:
                    stop_fetching = True
                    break

                asset_code = record.get('asset_code')
                if asset_code not in ["DMMK", "nUSDT"]:
                    continue

                # FIX #2: Use the safe extractor for all operation types
                raw_amount_str, sender, receiver = _extract_amount_and_parties(record)

                raw_val = Decimal(raw_amount_str or '0')
                final_val = (
                    raw_val * Decimal('1000') if asset_code == "DMMK" else raw_val
                )
                is_sender = sender == account_id
                raw_other_account = receiver if is_sender else sender

                if not raw_other_account:
                    continue  # skip malformed records

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

            if stop_fetching:
                break

            # FIX #1: Guard .next() — Blockdaemon can return None or raise
            # instead of returning an empty records list like Horizon does.
            try:
                next_page = payments_call.next()
                if next_page is None:
                    print("DEBUG: payments_call.next() returned None — end of pages.")
                    break
                next_records = next_page.get('_embedded', {}).get('records', [])
                if not next_records:
                    break
                records = next_page
            except StopIteration:
                # Some SDK versions raise StopIteration at end of pages
                break
            except Exception as page_err:
                print(f"DEBUG: Pagination stopped: {page_err}")
                break

        # Step 2: Resolve names concurrently (Multithreading)
        name_mapping = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = {
                executor.submit(fetch_account_name, acc, federation_url): acc
                for acc in unique_other_accounts
            }
            for future in concurrent.futures.as_completed(futures):
                acc_id = futures[future]
                try:
                    name_mapping[acc_id] = future.result()
                except Exception as name_err:
                    print(f"Name resolution failed for {acc_id}: {name_err}")
                    name_mapping[acc_id] = f"{acc_id[:8]}*******{acc_id[-8:]}"

        # Step 3: Map the names back to the records
        for row in raw_data:
            row["other_account"] = name_mapping.get(
                row["other_account_id"], row["other_account_id"]
            )

        if not raw_data:
            print(
                f"INFO: No DMMK or nUSDT transactions found for account {account_id} "
                f"in the last {months} month(s). "
                "Verify the account has activity on Blockdaemon mainnet and that "
                "the API key has the correct permissions."
            )

        return raw_data

    except Exception as e:
        # FIX #3: Print the real error instead of silently returning None
        print(f"CRITICAL ERROR in analyze_stellar_account: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None
