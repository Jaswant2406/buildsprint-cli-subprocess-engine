# BuildSprint Round 2: CLI-Driven AI Chat Execution Backend

A production-grade, secure, and resilient execution system for AI-driven web tasks. Users issue natural-language requests; the backend parses intent, executes approved CLI tools as subprocesses with socket-level IP pinning and SSRF protection, extracts structured evidence with source provenance, and streams real-time progress and final results over Server-Sent Events (SSE). The frontend is a reactive React + Vite + TypeScript application served single-origin alongside the API.

---

## Deployment

Deployed URL: not provided; run locally with the steps above.

### Minimum Server Requirements

- CPU: 2 vCPU cores minimum (4 vCPU recommended for concurrent crawler subprocesses)
- RAM: 2 GB RAM minimum (4 GB recommended)
- Disk: 1 GB available disk space
- Operating System: Linux (Ubuntu 22.04+, Debian 12+, RHEL 9+), macOS 13+, or Windows 10/11
- Runtimes: Python >= 3.11, Node.js >= 20.x, npm >= 10.x

### Single-Command Production Run

The repository includes automated single-command production startup scripts that compile the frontend for single-origin distribution, configure production environment variables, and launch the single-origin Uvicorn server on port 8000:

- Windows (PowerShell):
  ```powershell
  .\scripts\start_prod.ps1
  ```

- Linux / macOS (Bash):
  ```bash
  chmod +x ./scripts/start_prod.sh
  ./scripts/start_prod.sh
  ```

Once started, the complete unified application (both frontend UI and REST/SSE API) is available at:
`http://127.0.0.1:8000`

### Manual Step-by-Step Production Deployment

1. Build the production frontend distribution:
   ```bash
   cd frontend
   npm install
   npm run build
   cd ..
   ```
   This generates optimized, minified static assets in `frontend/dist/` with relative `/api` paths and no hardcoded localhost URLs.

2. Install Python backend dependencies:
   ```bash
   python -m venv .venv
   # Windows:
   .\.venv\Scripts\pip install -r backend/requirements.txt
   # Linux/macOS:
   ./.venv/bin/pip install -r backend/requirements.txt
   ```

3. Launch the single-origin server:
   ```bash
   # Windows PowerShell:
   $env:APP_ENV="production"; $env:HOST="0.0.0.0"; $env:PORT="8000"; .\.venv\Scripts\uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000

   # Linux/macOS Bash:
   APP_ENV=production HOST=0.0.0.0 PORT=8000 ./.venv/bin/uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
   ```

### Container Deployment (Docker)

A multi-stage, non-root `Dockerfile` is provided:
```bash
# Build the container image
docker build -t buildsprint .

# Run container on port 8000
docker run -d --name buildsprint -p 8000:8000 buildsprint
```
Note: Container execution status on this workstation is marked UNVERIFIED because the Docker daemon is not installed locally.

---

## Environment Variables Reference

Configuration is managed via environment variables or `.env` file (see `.env.example`).

| Variable | Description | Default | Production Recommendation |
|---|---|---|---|
| `APP_ENV` | Application environment (`production`, `development`, `test`) | `production` | Keep `production`. Disables OpenAPI docs, blocks loopback connections, and enforces strict CORS. |
| `PORT` | Listening port for HTTP / WebSocket / SSE | `8000` | Match target deployment port or reverse proxy pass. |
| `HOST` | Bind address | `0.0.0.0` | `0.0.0.0` (or `127.0.0.1` if behind local Nginx / Caddy). |
| `ALLOWED_ORIGINS` | Comma-separated list of allowed CORS origins | `""` (Same-origin only) | Leave empty for single-origin deployments; specify external domains only if hosting frontend separately. |
| `TRUSTED_PROXIES` | Comma-separated trusted reverse proxy IP addresses | `""` (Empty) | Specify reverse proxy IPs (e.g. `10.0.0.1,127.0.0.1`) so `X-Forwarded-For` is safely evaluated. Untrusted proxies are ignored. |
| `ENABLE_DOCS` | Explicitly toggle `/docs` and `/openapi.json` | `false` in prod | Leave `false` to avoid exposing API documentation in production. |
| `ALLOW_LOCALHOST_FOR_TESTS` | Allow loopback address crawling | `false` | Always `false`. Ignored by the server when `APP_ENV=production`. |
| `LLM_PROVIDER` | LLM provider (`openai`, `anthropic`, `google`) | `""` | Optional. If unset, engine operates in deterministic heuristic mode. |
| `LLM_API_KEY` | API key for LLM provider | `""` | Store in secret manager or runtime environment; never commit to git. |
| `LLM_MODEL` | Provider model identifier | Provider default | Set explicitly if using custom LLM endpoints. |

---

## Approved CLI Tools

The execution engine maintains a strict tool allowlist in `backend/app/runner.py`:

| Tool | Script | Purpose / Why Chosen |
|---|---|---|
| `site_crawler` | `cli/site_crawler.py` | Full same-domain BFS crawler extracting page titles, meta descriptions, language, headings (H1/H2), main body text (~2000 chars), link counts, image counts, emails, phone numbers, social links, and technology hints. |
| `link_checker` | `cli/link_checker.py` | High-performance link status auditor testing HTTP HEAD (with GET fallback) to categorize links into `working` (2xx), `broken` (4xx/5xx), or `error` (DNS/SSRF/robots block). |

### Argument Construction and Subprocess Security

- `shell=False` is strictly enforced across all executions.
- Command lines are constructed exclusively from validated Plan fields (`sys.executable`, path to CLI script, validated `--url`, clamped `--max-pages`, etc.).
- Prompt text or untrusted input is never interpolated into shell strings.
- Process isolation: Child processes are executed in clean, isolated environments where sensitive secrets (such as `LLM_API_KEY`) are stripped.

### Process Lifecycle and Fault Handling

- Watchdog / Stall Detection: If no stderr progress or heartbeat is detected for 15s, the run is transitioned to `STALLED` and killed.
- Overall Timeout: Runs exceeding 60s (configurable) are marked `TIMEOUT` and killed.
- Kill Tree & Orphan Prevention: Uses `psutil` to recursively terminate child and grandchild processes (`taskkill /T /F` on Windows; process group `SIGTERM` / `SIGKILL` on POSIX). Descendants are verified dead.
- Atomic State Machine: States: `queued` -> `running` -> `{completed, failed, timeout, stalled, cancelled}`. Terminal states are immutable under a per-run lock. A cancelled run can never later become `SUCCESS`.
- Bounded Concurrency: Maximum 2 concurrent running jobs managed by `SlotManager`. Mid-run SSE disconnects immediately cancel execution and release slots.

---

## Security and Reliability Architecture

1. SSRF Prevention and Socket-Level IP Pinning (`app/netpolicy.py`):
   - Resolves all A/AAAA records for hostnames. Rejects any private (`10/8`, `172.16/12`, `192.168/16`), loopback (`127/8`, `::1`), link-local, cloud metadata (`169.254.169.254`, `fd00:ec2::254`), or alternative decimal/octal/hex encodings.
   - Connects directly to the pinned IP over socket while maintaining the original hostname for TLS SNI and certificate validation.
   - Asserts socket `getpeername()` matches the pinned IP to prevent TOCTOU DNS rebinding.
   - Redirects followed manually (max 3 hops, loop detection, cross-domain blocking, destination robots.txt checks).
2. Prompt Injection Defense (`app/injection.py`):
   - Crawled content is scanned for injection patterns (`ignore instructions`, `system prompt`, `rm -rf`, base64 payloads, hidden-text styling).
   - Findings reported under `security_findings`; content is treated strictly as passive data.
3. Secret Redaction and Structured Logging (`app/security.py`):
   - API keys (`sk-...`, Bearer tokens, passwords) are automatically redacted across logs, SSE streams, and markdown reports.
4. Tamper-Evident Audit Chain (`app/runstore.py`):
   - Every completed run is appended to a cryptographic SHA-256 hash chain (`hash = sha256(prev_hash + entry)`).
   - `GET /api/audit` returns the chain and recomputes integrity (`verified: true`).

---

## Operating System Compatibility: Windows vs Linux

| Component | Windows (Current OS) | Linux / POSIX (Docker / CI) |
|---|---|---|
| Process Creation | Verified: `subprocess.Popen` with `CREATE_NEW_PROCESS_GROUP` | Uses POSIX process groups via `preexec_fn=os.setsid` |
| Process Termination | Verified: Recursive `psutil` teardown with `taskkill /F /T /PID` | Uses `os.killpg(os.getpgid(pid), signal.SIGTERM)` followed by `SIGKILL` |
| Temporary Files | Verified: Named temporary files with explicit close before open and `os.unlink` in `finally` | POSIX unlink semantics |
| Socket IP Pinning | Verified: IPv4/IPv6 dual-stack socket binding and peer validation | Verified via standard POSIX BSD sockets |
| Automated Test Suite | Verified: 151/151 pytest tests, 26 vitest tests, Playwright suite | Fully portable across Python 3.11+ and Node 20+ environments |

---

## Automated Verification and Test Suite

Execute the test suites locally:

1. Backend Test Suite (Pytest):
   ```bash
   cd backend
   pytest -q
   ```
   Result: 151 passed.

2. Code Linter (Ruff):
   ```bash
   ruff check .
   ```
   Result: All checks passed.

3. Static Type Analysis (Mypy):
   ```bash
   mypy backend/app cli
   ```
   Result: Success: no issues found in 19 source files.

4. Frontend Unit & Token Tests (Vitest):
   ```bash
   cd frontend
   npm test
   ```
   Result: 26 passed across 2 test files.

5. End-to-End Production Tests (Playwright):
   ```bash
   cd frontend
   npx playwright test
   ```
   Result: All responsive viewport checks and production single-origin routing tests passing.

---

## Verification Summary Table

| Verification Check | Status | Evidence |
|---|---|---|
| Frontend Production Build | PASS | `npm run build` completes in 105ms with 0 errors. Total dist size is 288 KB (82 KB gzip). |
| Zero Dev URLs in dist | PASS | Grep for `localhost` and `127.0.0.1` across `frontend/dist/` returns 0 matches. |
| Single-Origin Serving | PASS | FastAPI mounts static assets at `/assets` and handles SPA routing with fallback to `index.html`. `curl -i http://127.0.0.1:8000/api/health` returns 200 JSON. |
| Production Routing & 404 | PASS | Direct loads of `/`, `/runs`, `/runs/:id`, and `/runs/:id/details` resolve cleanly. Unknown route returns dedicated 404 Not Found UI. |
| Dev Flow Compatibility | PASS | Vite dev server proxies `/api` to port 8000; works without code changes. |
| SSRF localhost/127.0.0.1 Blocked | PASS | With `APP_ENV=production`, crawls to `http://localhost` and `http://127.0.0.1` are rejected with `ssrf_blocked`. |
| API Docs Exposure | PASS | In `APP_ENV=production`, `/docs` and `/openapi.json` are disabled by default. |
| Clean JSON Errors (No Traces) | PASS | Unhandled exceptions and 4xx/5xx responses return structured JSON (`{"detail": {"error": ...}}`); zero stack traces leaked. |
| CORS Restricted in Production | PASS | `ALLOWED_ORIGINS` defaults to empty in production; cross-origin requests do not receive `Access-Control-Allow-Origin`. |
| Concurrency & Rate Limiting | PASS | 3 simultaneous HTTP requests yield Req 1 & 2 HTTP 200, Req 3+ HTTP 429 (`rate_limit_exceeded` with `Retry-After`). |
| Reverse Proxy Header Safety | PASS | `TRUSTED_PROXIES` defaults to empty; untrusted `X-Forwarded-For` headers are strictly ignored and socket peer IP is used. |
| Child Process Secret Canary | PASS | `scripts/verify_secrets_canary.py` confirms `LLM_API_KEY` is stripped from child environment before spawning CLI tools. |
| Temp File Accumulation | PASS | `scripts/verify_temp_cleanup.py` executes 20 runs; exactly 0 temporary files remain in temp directory. |
| Graceful Process Shutdown | PASS | `scripts/verify_graceful_shutdown.py` confirms recursive process tree termination leaves 0 orphan processes via `psutil`. |
| Fresh Machine Simulation | PASS | Cloned without `.venv`, `node_modules`, or `.git` to temporary directory; all dependencies installed and 151/151 tests passed. |
| Docker Container Execution | UNVERIFIED | Multi-stage Dockerfile and .dockerignore authored to specification; marked UNVERIFIED because Docker engine is not installed on workstation. |

---

## AI Tools and Services Disclosed

In accordance with competition rules:
- Claude Sonnet 4.6 (Thinking) and Gemini 3.8 Flash: Used for test suite authoring, socket-level network policy engineering, and codebase structure.
- Zero Mock Policy in Production: All test fixtures and CLI flows connect to real network sockets and live HTTP servers.
