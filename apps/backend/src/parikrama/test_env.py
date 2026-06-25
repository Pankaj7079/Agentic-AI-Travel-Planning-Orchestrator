"""
PariKrama .env live key validator.
Run with: uv run python src/parikrama/test_env.py
"""

import asyncio
import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

# Force UTF-8 output on Windows
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Load .env ─────────────────────────────────────────────────────────────────
env_path = Path("d:/PariKrama_Agentic-AI-Travel-Planning-Orchestrator/.env")
for line in env_path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

results = []


def ok(name, detail=""):
    results.append((name, "PASS", detail))
    print(f"  [PASS] {name:<22} {detail}")


def fail(name, detail=""):
    results.append((name, "FAIL", detail))
    print(f"  [FAIL] {name:<22} {detail}")


def warn(name, detail=""):
    results.append((name, "WARN", detail))
    print(f"  [WARN] {name:<22} {detail}")


# ── 1. Gemini ─────────────────────────────────────────────────────────────────
print("\nTesting Gemini...", flush=True)
try:
    from google import genai as google_genai

    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        fail("GEMINI", "GEMINI_API_KEY is empty")
    else:
        client = google_genai.Client(api_key=key)
        model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite-preview-06-17")
        r = client.models.generate_content(model=model_name, contents="Reply with exactly: OK")
        ok("GEMINI", f"Model={model_name} | Response: {r.text.strip()[:30]}")
except ImportError:
    # Try legacy package
    try:
        import google.generativeai as genai

        key = os.environ.get("GEMINI_API_KEY", "")
        genai.configure(api_key=key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        r = model.generate_content("Reply with exactly: OK")
        warn(
            "GEMINI",
            f"Works via OLD package (google.generativeai) - should upgrade to google-genai. Response: {r.text.strip()[:20]}",
        )
    except Exception as e2:
        fail("GEMINI", str(e2)[:120])
except Exception as e:
    fail("GEMINI", str(e)[:120])

# ── 2. Groq ───────────────────────────────────────────────────────────────────
print("Testing Groq...", flush=True)
try:
    from groq import Groq

    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        fail("GROQ", "GROQ_API_KEY is empty")
    else:
        client = Groq(api_key=key)
        model = os.environ.get("GROQ_PRIMARY_MODEL", "llama-3.1-70b-versatile")
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply with exactly: OK"}],
            max_tokens=5,
        )
        ok("GROQ", f"Model={model} | {r.choices[0].message.content.strip()[:30]}")
except Exception as e:
    fail("GROQ", str(e)[:120])

# ── 3. PostgreSQL ─────────────────────────────────────────────────────────────
print("Testing PostgreSQL...", flush=True)


async def _test_pg():
    try:
        import asyncpg

        db_url = os.environ.get("DATABASE_URL", "").replace("+asyncpg", "")
        conn = await asyncpg.connect(db_url, timeout=5)
        ver = await conn.fetchval("SELECT version()")
        tables = await conn.fetchval(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
        )
        await conn.close()
        ok("POSTGRES", f"{ver[:45]} | {tables} public tables")
    except Exception as e:
        fail("POSTGRES", str(e)[:120])


asyncio.run(_test_pg())

# ── 4. Redis ──────────────────────────────────────────────────────────────────
print("Testing Redis...", flush=True)


async def _test_redis():
    try:
        import redis.asyncio as aioredis

        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        r = aioredis.from_url(url, socket_connect_timeout=3)
        await r.ping()
        info = await r.info("server")
        await r.aclose()
        ok("REDIS", f"v{info.get('redis_version', '?')} PONG received")
    except Exception as e:
        fail("REDIS", str(e)[:120])


asyncio.run(_test_redis())

# ── 5. OpenWeatherMap ─────────────────────────────────────────────────────────
print("Testing OpenWeatherMap...", flush=True)
try:
    key = os.environ.get("OPENWEATHERMAP_API_KEY", "")
    if not key:
        warn("OPENWEATHERMAP", "Empty - weather in itinerary disabled")
    else:
        url = f"https://api.openweathermap.org/data/2.5/weather?q=Delhi&appid={key}"
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read())
        temp_c = round(data["main"]["temp"] - 273.15, 1)
        desc = data["weather"][0]["description"]
        ok("OPENWEATHERMAP", f"Delhi: {temp_c}C, {desc}")
except Exception as e:
    fail("OPENWEATHERMAP", str(e)[:120])

# ── 6. Resend ─────────────────────────────────────────────────────────────────
print("Testing Resend...", flush=True)
try:
    key = os.environ.get("RESEND_API_KEY", "")
    if not key:
        warn("RESEND", "Empty - email notifications disabled")
    else:
        req = urllib.request.Request(
            "https://api.resend.com/domains",
            headers={"Authorization": f"Bearer {key}"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            ok("RESEND", f"Key valid | HTTP {resp.status}")
except Exception as e:
    fail("RESEND", str(e)[:120])

# ── 7. LangSmith ─────────────────────────────────────────────────────────────
print("Testing LangSmith...", flush=True)
try:
    key = os.environ.get("LANGCHAIN_API_KEY", "")
    tracing = os.environ.get("LANGCHAIN_TRACING_V2", "false")
    if not key:
        warn("LANGSMITH", "Key empty - agent tracing disabled")
    else:
        req = urllib.request.Request(
            "https://api.smith.langchain.com/ok",
            headers={"x-api-key": key},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            tracing_str = (
                "tracing=ON" if tracing == "true" else "tracing=OFF (set LANGCHAIN_TRACING_V2=true)"
            )
            ok("LANGSMITH", f"Key valid | {tracing_str}")
except Exception as e:
    fail("LANGSMITH", str(e)[:120])

# ── 8. Sentry ─────────────────────────────────────────────────────────────────
print("Checking Sentry DSN...", flush=True)
dsn = os.environ.get("SENTRY_DSN", "")
if dsn.startswith("https://") and "@" in dsn and "sentry.io" in dsn:
    ok("SENTRY", f"DSN valid | sample_rate={os.environ.get('SENTRY_TRACES_SAMPLE_RATE', '0.1')}")
elif not dsn:
    warn("SENTRY", "DSN empty - error monitoring disabled")
else:
    fail("SENTRY", f"DSN malformed: {dsn[:50]}")

# ── 9. ElevenLabs ─────────────────────────────────────────────────────────────
print("Testing ElevenLabs...", flush=True)
try:
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not key:
        warn("ELEVENLABS", "Empty - using free/local TTS fallback")
    else:
        req = urllib.request.Request(
            "https://api.elevenlabs.io/v1/user",
            headers={"xi-api-key": key},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
            plan = data.get("subscription", {}).get("tier", "unknown")
            ok("ELEVENLABS", f"Key valid | plan={plan}")
except Exception as e:
    fail("ELEVENLABS", str(e)[:120])

# ── 10. Google OAuth ──────────────────────────────────────────────────────────
print("Checking Google OAuth...", flush=True)
gcid = os.environ.get("GOOGLE_CLIENT_ID", "")
gcs = os.environ.get("GOOGLE_CLIENT_SECRET", "")
if gcid and gcs and gcid != "":
    ok("GOOGLE_OAUTH", f"Client ID=...{gcid[-20:]}")
elif not gcid:
    warn("GOOGLE_OAUTH", "GOOGLE_CLIENT_ID empty - Google Sign-In disabled")
else:
    warn("GOOGLE_OAUTH", "GOOGLE_CLIENT_SECRET missing")

# ── 11. Google Places ─────────────────────────────────────────────────────────
gpa = os.environ.get("GOOGLE_PLACES_API_KEY", "")
if not gpa:
    warn("GOOGLE_PLACES", "Empty - hotel/restaurant enrichment disabled")
else:
    ok("GOOGLE_PLACES", f"Set: ...{gpa[-8:]}")

# ── 12. FCM ───────────────────────────────────────────────────────────────────
fcm = os.environ.get("FCM_CREDENTIALS_PATH", "")
if not fcm:
    warn("FCM", "Empty - push notifications disabled")
elif Path(fcm).exists():
    ok("FCM", f"File found: {fcm}")
else:
    fail("FCM", f"Path set but FILE NOT FOUND: {fcm}")

# ── 13. Security keys ─────────────────────────────────────────────────────────
print("Checking security keys...", flush=True)
jwt_key = os.environ.get("JWT_SECRET_KEY", "")
secret_key = os.environ.get("SECRET_KEY", "")
weak = ["change-this", "change_this", "secret", "dev", "default", "production"]

if any(w in jwt_key.lower() for w in weak) or len(jwt_key) < 32:
    fail("JWT_SECRET_KEY", f"INSECURE default value! len={len(jwt_key)}")
else:
    ok("JWT_SECRET_KEY", f"Strong ({len(jwt_key)} chars)")

if any(w in secret_key.lower() for w in weak) or len(secret_key) < 16:
    fail("SECRET_KEY", f"INSECURE default value! value={secret_key[:30]}")
else:
    ok("SECRET_KEY", f"Strong ({len(secret_key)} chars)")

# ── 14. LiveKit ───────────────────────────────────────────────────────────────
lk_key = os.environ.get("LIVEKIT_API_KEY", "devkey")
lk_secret = os.environ.get("LIVEKIT_API_SECRET", "secret")
lk_url = os.environ.get("LIVEKIT_URL", "")
if lk_key in ("devkey", "dev", "") or lk_secret in ("secret", ""):
    warn("LIVEKIT", "Using dev defaults - voice won't work in production")
else:
    ok("LIVEKIT", f"URL={lk_url} | custom credentials set")

# ── 15. DB_LOG ────────────────────────────────────────────────────────────────
db_log = os.environ.get("DB_LOG", "false")
if db_log.lower() == "true":
    warn(
        "DB_LOG",
        "SQL logging ENABLED - will fill database.log fast in dev. Set DB_LOG=false for prod.",
    )
else:
    ok("DB_LOG", "SQL logging OFF (good for production)")

# ── Summary ───────────────────────────────────────────────────────────────────
print()
print("=" * 72)
passed = sum(1 for _, s, _ in results if s == "PASS")
warned = sum(1 for _, s, _ in results if s == "WARN")
failed = sum(1 for _, s, _ in results if s == "FAIL")
print(f"  RESULT:  {passed} PASS  |  {warned} WARN (optional)  |  {failed} FAIL (action needed)")
print(f"  Tested:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 72)

if failed:
    print("\n  CRITICAL - Fix these immediately:")
    for name, status, detail in results:
        if status == "FAIL":
            print(f"    -> {name}: {detail}")

if warned:
    print("\n  OPTIONAL - These features are disabled:")
    for name, status, detail in results:
        if status == "WARN":
            print(f"    -> {name}: {detail}")

print()
