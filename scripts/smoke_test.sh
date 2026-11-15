#!/usr/bin/env bash
set -e

BASE_URL="http://127.0.0.1:8000"
FAILED=0

echo "============================================================"
echo "BuildSprint Bash Smoke Test Suite (curl + jq)"
echo "Target: $BASE_URL"
echo "============================================================"

# Check health
echo -n "[TEST] 1. Health check (/api/health)... "
HEALTH=$(curl -s "$BASE_URL/api/health")
STATUS=$(echo "$HEALTH" | jq -r '.status // empty')
if [ "$STATUS" = "ok" ]; then
    echo "PASS"
else
    echo "FAIL ($HEALTH)"
    FAILED=1
fi

# Real crawl of example.com
echo -n "[TEST] 2. Crawl https://example.com... "
CRAWL_OUT=$(curl -s -X POST "$BASE_URL/api/chat" \
    -H "Content-Type: application/json" \
    -d '{"prompt":"Crawl https://example.com, extract info and return JSON"}')
if echo "$CRAWL_OUT" | grep -q "SUCCESS"; then
    echo "PASS"
else
    echo "FAIL"
    FAILED=1
fi

# Bad domain
echo -n "[TEST] 3. Bad domain detection... "
BAD_OUT=$(curl -s -X POST "$BASE_URL/api/chat" \
    -H "Content-Type: application/json" \
    -d '{"prompt":"Crawl https://invalid-domain-does-not-exist-xyz987.org"}')
if echo "$BAD_OUT" | grep -q -E "FAILED|error|ssrf_blocked"; then
    echo "PASS"
else
    echo "FAIL"
    FAILED=1
fi

# SSRF blocked localhost
echo -n "[TEST] 4. SSRF block http://localhost... "
SSRF_OUT=$(curl -s -X POST "$BASE_URL/api/chat" \
    -H "Content-Type: application/json" \
    -d '{"prompt":"Crawl http://localhost"}')
if echo "$SSRF_OUT" | grep -q -E "error|ssrf_blocked|FAILED"; then
    echo "PASS"
else
    echo "FAIL"
    FAILED=1
fi

# SSRF blocked metadata service
echo -n "[TEST] 5. SSRF block metadata 169.254.169.254... "
META_OUT=$(curl -s -X POST "$BASE_URL/api/chat" \
    -H "Content-Type: application/json" \
    -d '{"prompt":"Crawl http://169.254.169.254"}')
if echo "$META_OUT" | grep -q -E "error|ssrf_blocked|FAILED"; then
    echo "PASS"
else
    echo "FAIL"
    FAILED=1
fi

# Link checker run
echo -n "[TEST] 6. Link checker execution... "
LC_OUT=$(curl -s -X POST "$BASE_URL/api/chat" \
    -H "Content-Type: application/json" \
    -d '{"prompt":"Check for broken links on https://example.com"}')
if echo "$LC_OUT" | grep -q "link_checker"; then
    echo "PASS"
else
    echo "FAIL"
    FAILED=1
fi

# Rate limit 429
echo -n "[TEST] 7. Rate limit 429 enforcement... "
HIT_429=0
for i in {1..8}; do
    CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/chat" \
        -H "Content-Type: application/json" \
        -d '{"prompt":"Crawl https://example.com"}')
    if [ "$CODE" = "429" ]; then
        HIT_429=1
        break
    fi
done
if [ "$HIT_429" = "1" ]; then
    echo "PASS"
else
    echo "FAIL (did not hit 429)"
    FAILED=1
fi

echo "============================================================"
if [ "$FAILED" = "0" ]; then
    echo "ALL SMOKE TESTS PASSED"
    exit 0
else
    echo "SOME SMOKE TESTS FAILED"
    exit 1
fi
