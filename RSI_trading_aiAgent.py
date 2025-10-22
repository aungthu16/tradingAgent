import os
import time
import json
import hmac
import hashlib
import base64
import requests
from groq import Groq
from dotenv import load_dotenv

# ================================================================
# 1️⃣  CONFIGURATION
# ================================================================
load_dotenv()

BITGET_API_KEY = os.getenv("BITGET_API_KEY")
BITGET_SECRET = os.getenv("BITGET_SECRET")
BITGET_PASSPHRASE = os.getenv("BITGET_PASSPHRASE")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
TAAPI_SECRET = os.getenv("TAAPI_SECRET")

BASE_URL = "https://api.bitget.com"
PAPER_TRADING = True   # True = Paper Trading mode
SYMBOL = "ETHUSDT"

TAAPI_URL = (
    f"https://api.taapi.io/rsi?"
    f"secret={TAAPI_SECRET}"
    "&exchange=binance&symbol=ETH/USDT&interval=5m"
)

# ================================================================
# 2️⃣  BITGET SIGNATURE + ORDER
# ================================================================
def generate_signature(timestamp, method, request_path, body, secret_key):
    body_str = json.dumps(body, separators=(",", ":")) if body else ""
    pre_hash = f"{timestamp}{method.upper()}{request_path}{body_str}"
    mac = hmac.new(secret_key.encode("utf-8"), pre_hash.encode("utf-8"), hashlib.sha256)
    return base64.b64encode(mac.digest()).decode("utf-8")

def bitget_request(method, endpoint, payload):
    """Send authenticated Bitget request."""
    timestamp = str(int(time.time() * 1000))
    signature = generate_signature(timestamp, method, endpoint, payload, BITGET_SECRET)
    headers = {
        "ACCESS-KEY": BITGET_API_KEY,
        "ACCESS-SIGN": signature,
        "ACCESS-PASSPHRASE": BITGET_PASSPHRASE,
        "ACCESS-TIMESTAMP": timestamp,
        "Content-Type": "application/json",
        "locale": "en-US",
        "paptrading": "1" if PAPER_TRADING else "0",
    }

    url = BASE_URL + endpoint
    response = requests.request(method, url, headers=headers, data=json.dumps(payload))
    try:
        result = response.json()
    except Exception:
        result = {"error": response.text}
    print(f"➡️ {method} {endpoint} → {response.status_code}")
    print(json.dumps(result, indent=4))
    return result

def close_position(side):
    """Close opposite position before opening a new one."""
    opposite_side = "buy" if side == "sell" else "sell"
    payload = {
        "symbol": SYMBOL,
        "productType": "USDT-FUTURES",
        "marginMode": "isolated",
        "marginCoin": "USDT",
        "size": "1000",
        "side": opposite_side,
        "tradeSide": "close",
        "orderType": "market",
        "force": "gtc"
    }
    bitget_request("POST", "/api/v2/mix/order/place-order", payload)

def open_position(side):
    """Open new position in given direction."""
    payload = {
        "symbol": SYMBOL,
        "productType": "USDT-FUTURES",
        "marginMode": "isolated",
        "marginCoin": "USDT",
        "size": "0.05",
        "side": side,
        "tradeSide": "open",
        "orderType": "market",
        "force": "gtc"
    }
    bitget_request("POST", "/api/v2/mix/order/place-order", payload)

# ================================================================
# 3️⃣  TAAPI + AI DECISION
# ================================================================
def get_rsi_value():
    """Fetch RSI value from TAAPI.io."""
    try:
        r = requests.get(TAAPI_URL)
        data = r.json()
        return float(data["value"])
    except Exception as e:
        print(f"❌ Failed to fetch RSI: {e}")
        return None

def get_ai_decision(rsi_value):
    """Ask Groq AI what to do based on RSI."""
    groq_client = Groq(api_key=GROQ_API_KEY)
    system_prompt = "You are a world expert at crypto trading."
    user_prompt = (
        f"The current Relative Strength Index (RSI) for Ethereum (ETH) is {rsi_value}. "
        "Based on this, decide if you should BUY, SELL or do NOTHING. "
        "Respond with one word only: BUY, SELL or NOTHING."
    )

    try:
        chat = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            model=GROQ_MODEL,
        )
        decision = chat.choices[0].message.content.strip().upper()
        print(f"🧠 AI Decision: {decision}")
        return decision
    except Exception as e:
        print(f"❌ Groq API Error: {e}")
        return "NOTHING"

# ================================================================
# 4️⃣  MAIN LOOP (runs every 5 minutes)
# ================================================================
def main():
    print("🚀 Starting ETHUSDT RSI-based AI Trading Bot (5m loop)")
    while True:
        print("\n===========================================")
        print(f"🕒 Checking market... {time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        rsi = get_rsi_value()
        if rsi is None:
            print("Skipping this cycle (no RSI data).")
            time.sleep(300)
            continue

        print(f"📈 Current RSI (5m): {rsi}")

        decision = get_ai_decision(rsi)
        if decision == "BUY":
            close_position("buy")   # close any sell
            open_position("buy")
        elif decision == "SELL":
            close_position("sell")  # close any buy
            open_position("sell")
        else:
            print("⏸ AI decided to do NOTHING — no action this cycle.")

        print("✅ Cycle complete. Waiting 5 minutes...")
        time.sleep(300)  # 5 minutes

# ================================================================
# 5️⃣  RUN BOT
# ================================================================
if __name__ == "__main__":
    main()
