"""
Live test for Resend, ElevenLabs, and Google Places API keys.
Run: uv run python src/parikrama/test_three_keys.py
"""
import sys, os, json, urllib.request, urllib.error
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path

# Load .env
for line in Path("d:/PariKrama_Agentic-AI-Travel-Planning-Orchestrator/.env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

SEP = "=" * 65

def _http(url, headers=None, method="GET", body=None):
    """Simple HTTP helper. Returns (status_code, response_body_dict_or_str)."""
    req = urllib.request.Request(url, headers=headers or {}, method=method)
    if body:
        req.data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw)
            except Exception:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw
    except Exception as e:
        return 0, str(e)


# ─────────────────────────────────────────────────────────────────────────────
# 1. RESEND
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("  TEST 1 : RESEND (Email Notifications)")
print(SEP)

resend_key = os.environ.get("RESEND_API_KEY", "")
from_email = os.environ.get("RESEND_FROM_EMAIL", "")
print(f"  Key    : {resend_key[:12]}...{resend_key[-6:]}")
print(f"  From   : {from_email}")

# Step A: List API keys (auth check)
status, data = _http(
    "https://api.resend.com/api-keys",
    headers={"Authorization": f"Bearer {resend_key}"},
)
print(f"\n  [A] GET /api-keys -> HTTP {status}")
if status == 200:
    keys = data.get("data", []) if isinstance(data, dict) else []
    print(f"      PASS - Account has {len(keys)} API key(s)")
    for k in keys[:3]:
        print(f"        - {k.get('name','?')} | created: {k.get('created_at','?')[:10]}")
elif status == 403:
    print(f"      FAIL - 403 Forbidden: key lacks 'Full Access' permission")
    print(f"      Detail: {str(data)[:150]}")
elif status == 401:
    print(f"      FAIL - 401 Unauthorized: key is invalid or revoked")
    print(f"      Detail: {str(data)[:150]}")
else:
    print(f"      FAIL - Unexpected response: {str(data)[:150]}")

# Step B: List domains
status2, data2 = _http(
    "https://api.resend.com/domains",
    headers={"Authorization": f"Bearer {resend_key}"},
)
print(f"\n  [B] GET /domains -> HTTP {status2}")
if status2 == 200:
    domains = data2.get("data", []) if isinstance(data2, dict) else []
    if domains:
        print(f"      PASS - {len(domains)} domain(s) configured:")
        for d in domains:
            status_str = d.get("status", "?")
            name = d.get("name", "?")
            print(f"        - {name} | status: {status_str}")
            if status_str != "verified":
                print(f"          WARNING: Domain not verified - emails may go to spam!")
    else:
        print(f"      WARN - No domains configured. Using noreply@parikrama.dev will fail.")
        print(f"             Add a domain at: https://resend.com/domains")
        print(f"             Or use Resend's test domain: onboarding@resend.dev (100 emails/day)")
else:
    print(f"      Status: {status2} | {str(data2)[:100]}")

# Step C: Send a test email (dry approach - just validate payload)
print(f"\n  [C] Summary:")
if status == 200:
    print(f"      KEY IS VALID")
    print(f"      NOTE: RESEND_FROM_EMAIL='{from_email}' needs a verified domain.")
    print(f"      If your domain is not verified, use: onboarding@resend.dev")
    print(f"      Action: Go to https://resend.com/domains -> Add & verify parikrama.dev")
elif status in (401, 403):
    print(f"      KEY IS INVALID OR RESTRICTED")
    print(f"      Action: Go to https://resend.com/api-keys -> Create new key with 'Full access'")


# ─────────────────────────────────────────────────────────────────────────────
# 2. ELEVENLABS
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("  TEST 2 : ELEVENLABS (Text-to-Speech)")
print(SEP)

el_key = os.environ.get("ELEVENLABS_API_KEY", "")
print(f"  Key    : {el_key[:12]}...{el_key[-6:]}")

# Step A: Get user info
status, data = _http(
    "https://api.elevenlabs.io/v1/user",
    headers={"xi-api-key": el_key},
)
print(f"\n  [A] GET /v1/user -> HTTP {status}")
if status == 200 and isinstance(data, dict):
    sub = data.get("subscription", {})
    tier = sub.get("tier", "unknown")
    char_used = sub.get("character_count", 0)
    char_limit = sub.get("character_limit", 0)
    next_reset = sub.get("next_character_count_reset_unix", 0)
    print(f"      PASS - Account active!")
    print(f"        Plan    : {tier}")
    print(f"        Chars   : {char_used:,} used / {char_limit:,} limit")
    print(f"        Resets  : at unix timestamp {next_reset}")
elif status == 401:
    print(f"      FAIL - 401 Unauthorized: key is invalid or expired")
    print(f"      Detail: {str(data)[:150]}")
elif status == 403:
    print(f"      FAIL - 403 Forbidden: key doesn't have required permissions")
else:
    print(f"      FAIL - HTTP {status}: {str(data)[:150]}")

# Step B: List available voices
status2, data2 = _http(
    "https://api.elevenlabs.io/v1/voices",
    headers={"xi-api-key": el_key},
)
print(f"\n  [B] GET /v1/voices -> HTTP {status2}")
if status2 == 200 and isinstance(data2, dict):
    voices = data2.get("voices", [])
    print(f"      PASS - {len(voices)} voice(s) available")
    for v in voices[:3]:
        print(f"        - {v.get('name','?')} | category: {v.get('category','?')}")
else:
    print(f"      Status: {status2}")

print(f"\n  [C] Summary:")
if status == 200:
    print(f"      KEY IS VALID - ElevenLabs TTS is ready")
else:
    print(f"      KEY IS INVALID")
    print(f"      Action: Go to https://elevenlabs.io -> Profile -> API Key -> generate new")


# ─────────────────────────────────────────────────────────────────────────────
# 3. GOOGLE PLACES API
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("  TEST 3 : GOOGLE PLACES API")
print(SEP)

places_key = os.environ.get("GOOGLE_PLACES_API_KEY", "")
print(f"  Key    : {places_key[:12]}...{places_key[-6:]}" if places_key else "  Key    : EMPTY")

if not places_key:
    print("\n  SKIP - GOOGLE_PLACES_API_KEY is empty")
else:
    # Step A: Text search for a hotel in Manali (real use case)
    url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query=hotels+in+Manali&key={places_key}"
    status, data = _http(url)
    print(f"\n  [A] Places Text Search (hotels in Manali) -> HTTP {status}")
    if status == 200 and isinstance(data, dict):
        api_status = data.get("status", "UNKNOWN")
        results = data.get("results", [])
        print(f"      API Status : {api_status}")
        if api_status == "OK":
            print(f"      PASS - {len(results)} results returned")
            for r in results[:3]:
                name = r.get("name", "?")
                rating = r.get("rating", "N/A")
                print(f"        - {name} | rating: {rating}")
        elif api_status == "REQUEST_DENIED":
            error_msg = data.get("error_message", "No error message")
            print(f"      FAIL - REQUEST_DENIED: {error_msg}")
            if "not activated" in error_msg.lower() or "Places API" in error_msg:
                print(f"      FIX : Enable 'Places API' in Google Cloud Console")
                print(f"            https://console.cloud.google.com/apis/library/places-backend.googleapis.com")
            elif "API key" in error_msg.lower():
                print(f"      FIX : Check API key restrictions in Google Cloud Console")
        elif api_status == "OVER_QUERY_LIMIT":
            print(f"      WARN - Quota exceeded for today")
        else:
            print(f"      Status: {api_status} | {str(data)[:100]}")
    else:
        print(f"      HTTP {status}: {str(data)[:150]}")

    # Step B: Nearby search for restaurants
    url2 = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?location=32.2396,77.1887&radius=2000&type=restaurant&key={places_key}"
    status2, data2 = _http(url2)
    print(f"\n  [B] Nearby Search (restaurants near Manali) -> HTTP {status2}")
    if status2 == 200 and isinstance(data2, dict):
        api_status2 = data2.get("status", "UNKNOWN")
        results2 = data2.get("results", [])
        if api_status2 == "OK":
            print(f"      PASS - {len(results2)} restaurants found")
        else:
            print(f"      Status: {api_status2}")
    else:
        print(f"      HTTP {status2}: {str(data2)[:100]}")

    print(f"\n  [C] Summary:")
    if status == 200 and isinstance(data, dict) and data.get("status") == "OK":
        print(f"      KEY IS VALID - Google Places API is working")
        print(f"      Billing: Places API costs $0.017/request - monitor usage!")
        print(f"      https://console.cloud.google.com/billing")
    else:
        print(f"      KEY HAS ISSUES - see details above")

print(f"\n{SEP}\n")
