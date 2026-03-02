"""
🔍 Connection Test Script
Run this to test IG + Telegram connections
"""
import os
import requests

print("=" * 40)
print("🔍 CONNECTION TEST")
print("=" * 40)

# ── Test 1: Check all secrets loaded ─────
print("\n📋 Step 1: Checking secrets...")
username   = os.environ.get("IG_USERNAME", "")
password   = os.environ.get("IG_PASSWORD", "")
api_key    = os.environ.get("IG_API_KEY", "")
acc_number = os.environ.get("IG_ACC_NUMBER", "")
tg_token   = os.environ.get("TELEGRAM_TOKEN", "")
tg_chat    = os.environ.get("TELEGRAM_CHAT_ID", "")

print(f"IG_USERNAME:    {'✅ SET → ' + username[:4] + '****' if username else '❌ EMPTY!'}")
print(f"IG_PASSWORD:    {'✅ SET → ' + '*' * 8 if password else '❌ EMPTY!'}")
print(f"IG_API_KEY:     {'✅ SET → ' + api_key[:4] + '****' if api_key else '❌ EMPTY!'}")
print(f"IG_ACC_NUMBER:  {'✅ SET → ' + acc_number if acc_number else '❌ EMPTY!'}")
print(f"TELEGRAM_TOKEN: {'✅ SET → ' + tg_token[:6] + '****' if tg_token else '❌ EMPTY!'}")
print(f"TELEGRAM_CHAT:  {'✅ SET → ' + tg_chat if tg_chat else '❌ EMPTY!'}")

# ── Test 2: Test IG Login ─────────────────
print("\n📋 Step 2: Testing IG Login...")
try:
    url = "https://demo-api.ig.com/gateway/deal/session"
    headers = {
        "X-IG-API-KEY": api_key,
        "Content-Type": "application/json; charset=UTF-8",
        "Accept":       "application/json; charset=UTF-8",
        "Version":      "2"
    }
    payload = {
        "identifier":        username,
        "password":          password,
        "encryptedPassword": False
    }
    r = requests.post(url, headers=headers, json=payload, timeout=15)
    print(f"Status Code: {r.status_code}")
    print(f"Response: {r.text[:300]}")

    if r.status_code == 200:
        print("✅ IG LOGIN SUCCESS!")
        cst  = r.headers.get("CST")
        x_st = r.headers.get("X-SECURITY-TOKEN")
        print(f"CST token: {cst[:10]}****")
    else:
        print(f"❌ IG LOGIN FAILED!")
        print(f"Reason: {r.text}")
except Exception as e:
    print(f"❌ IG Connection Error: {e}")

# ── Test 3: Test Telegram ─────────────────
print("\n📋 Step 3: Testing Telegram...")
try:
    url  = f"https://api.telegram.org/bot{tg_token}/sendMessage"
    data = {
        "chat_id": tg_chat,
        "text":    "✅ IG Bot test message! Connection working!"
    }
    r = requests.post(url, data=data, timeout=10)
    print(f"Telegram Status: {r.status_code}")
    if r.status_code == 200:
        print("✅ TELEGRAM SUCCESS!")
    else:
        print(f"❌ TELEGRAM FAILED: {r.text}")
except Exception as e:
    print(f"❌ Telegram Error: {e}")

print("\n" + "=" * 40)
print("🔍 TEST COMPLETE")
print("=" * 40)
