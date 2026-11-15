# BuildSprint Round 2: 6-Minute Walkthrough Video Script

**Format**: Screen recording with audio voiceover  
**Target Duration**: 06:00  

---

## Shot 1: The Problem (0:00 – 0:30)
- **Visual**: Show prompt screen and terminal.
- **Narrator**:
  > "Welcome to BuildSprint Round 2. Today's AI agents often hallucinate website content or dangerously execute untrusted code in uncontrolled shells. For this challenge, we built a fully autonomous, production-grade CLI-driven AI execution backend. Users submit high-level research requests, and our backend safely translates them into validated plans, executes real approved CLI subprocesses with military-grade network sandboxing, verifies every extracted fact with source URLs, and streams live progress over Server-Sent Events."

---

## Shot 2: Architecture & Security Model (0:30 – 1:15)
- **Visual**: Display `docs/architecture.md` diagram and `app/netpolicy.py`.
- **Point At**:
  - Show the mermaid pipeline: `Chat -> Intent -> Validator -> Rate Limit -> Runner -> NetPolicy -> Postprocess -> Extractor -> Summarizer -> SSE`.
  - Highlight IP pinning and SSRF defense in `netpolicy.py`.
- **Narrator**:
  > "Let's review the architecture. Notice our strict isolation: `shell=False` is enforced across all child executions. We implemented true IP pinning at the socket level to eliminate Time-of-Check to Time-of-Use DNS rebinding attacks. On every hop, we resolve all IP addresses, reject any private, loopback, link-local, or cloud metadata endpoints like 169.254.169.254, connect directly to the pinned IP while preserving TLS SNI and certificate validation, and assert the socket peer address. Redirects are capped at 3 hops with loop detection and robots.txt checks."

---

## Shot 3: Prompt to Plan & Tool Selection (1:15 – 2:00)
- **Visual**: Run `python scripts/demo.py` or execute a curl request against `/api/chat`.
- **Command**:
  ```bash
  curl -N -X POST http://127.0.0.1:8000/api/chat \
    -H "Content-Type: application/json" \
    -d '{"prompt": "Crawl https://example.com, extract the important information, give me a summary, and return the extracted data in JSON format."}'
  ```
- **Point At**:
  - Point to SSE events: `event: received`, `event: plan`, `event: validated`, `event: spawned`.
  - Point to plan details: `tool: "site_crawler"`, `tool_reason: "Task requires crawling and content extraction → site_crawler"`, `max_pages: 10`, `max_depth: 2`.
- **Narrator**:
  > "Here, our intent parser analyzes the natural-language task. Even without external LLM keys, our heuristic engine immediately parses the user's intent, selects the approved `site_crawler` tool, clamps pagination limits, validates the URL against our network policy, acquires an execution slot from our 2-run concurrency manager, and spawns the subprocess with its own isolated process group."

---

## Shot 4: Live Crawl & Structured Telemetry (2:00 – 3:00)
- **Visual**: Show live stderr heartbeat and progress streaming in terminal.
- **Point At**:
  - Point to stderr stream showing `{"event": "progress", "url": "https://example.com"}` and `{"event": "heartbeat"}` every 2 seconds.
  - Show PID assigned to the subprocess.
- **Narrator**:
  > "Watch the execution telemetry. The CLI emits JSON-line progress events and periodic heartbeats on stderr. If a subprocess hangs or fails to emit a heartbeat for 15 seconds, our watchdog terminates the entire process tree using psutil. Once the crawl finishes, output is captured directly from disk via `--out-file` with fallback to stdout."

---

## Shot 5: Summary, JSON Schema & Fact Provenance (3:00 – 3:45)
- **Visual**: Show the final `event: result` payload and markdown report (`GET /api/runs/{id}/report.md`).
- **Point At**:
  - Status `SUCCESS`, coverage score (e.g. `46/100`), status reason.
  - The `extracted` block: every email, phone, and key page displaying its exact `source_url`.
  - Executive summary and key takeaways.
- **Narrator**:
  > "Notice the result payload: status SUCCESS, duration, and a coverage score breakdown. Look at our consolidated `extracted` object: every single fact—whether it's site description, topics, contact emails, or social profiles—carries provenance with its verified source_url. Furthermore, the markdown report can be exported on demand at `/api/runs/{id}/report.md`."

---

## Shot 6: Failure & Fault Tolerance (3:45 – 4:30)
- **Visual**: Execute a request against an unreachable domain and an SSRF target.
- **Commands**:
  ```bash
  # Test 1: Unreachable domain
  curl -s -X POST http://127.0.0.1:8000/api/chat -H "Content-Type: application/json" -d '{"prompt": "Crawl http://invalid-domain-xyz987.org"}'
  
  # Test 2: SSRF blocked
  curl -s -X POST http://127.0.0.1:8000/api/chat -H "Content-Type: application/json" -d '{"prompt": "Crawl http://169.254.169.254"}'
  ```
- **Point At**:
  - Point to instant validation error: `"ssrf_blocked"` for `169.254.169.254`.
  - Show exit code `4 (unreachable)` for bad domains, and terminal state remaining immutable even if cancelled.
- **Narrator**:
  > "Now observe our defense in depth. When an attacker or user asks to crawl `169.254.169.254`, our validator and netpolicy block it immediately before any network packet can leave the machine. When given an unreachable domain, the engine detects DNS failure and sets status to FAILED with exit code 4. And our state machine ensures a cancelled run can never transition to success."

---

## Shot 7: Prompt Injection Detection & Sandboxing (4:30 – 5:15)
- **Visual**: Crawl `demo_site/injection.html`.
- **Command**:
  ```bash
  python cli/site_crawler.py --url http://127.0.0.1:8000/injection.html
  ```
- **Point At**:
  - Show `security_findings` populated with `pattern: "ignore_instructions"`, `pattern: "run_command"`.
  - Show the text treated strictly as data without executing any shell instructions.
  - Highlight the untrusted data delimiters in `summarizer.py`.
- **Narrator**:
  > "Websites often contain malicious prompt injection attempts. Here is our `demo_site/injection.html`. Notice that our `injection.py` detector spots the injection patterns and reports them under `security_findings`. The summarizer treats all crawled content as raw untrusted data enclosed in explicit boundary delimiters, preventing indirect prompt injection from affecting execution."

---

## Shot 8: Test Suite, Audit Chain & AI Tools Disclosed (5:15 – 6:00)
- **Visual**:
  - Run `pytest -v` across all 108 tests.
  - Show `GET /api/audit` displaying the cryptographic hash chain.
  - Show slide or screen with stack and AI tools disclosed.
- **Commands**:
  ```bash
  pytest -v
  curl http://127.0.0.1:8000/api/audit
  ```
- **Point At**:
  - 108 passed tests!
  - `verified: true` in the audit log response.
- **Narrator**:
  > "Finally, let's look at the test suite: 108 comprehensive unit and integration tests passing cleanly with zero errors. Our audit chain cryptographically hashes each run into a tamper-evident blockchain-style log, verifiable at `/api/audit`. The entire project is built with Python 3.11+, FastAPI, Pydantic v2, and httpx with zero external deployment dependencies. All code generation and design iterations were assisted by Claude Sonnet and Gemini models within Google Antigravity. Thank you!"
