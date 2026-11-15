# BuildSprint Round 2: Architecture Documentation

## Overview

BuildSprint Round 2 delivers a **CLI-Driven AI Chat Execution Backend**. Users issue natural language research prompts (e.g., *"Crawl https://example.com, extract important information, summarize it, and return JSON"*). The backend parses intent, enforces strict multi-layered network security, acquires an execution slot, executes an approved CLI subprocess, captures and validates output, extracts structured evidence with source provenance, scans for prompt injections, generates summaries, and streams progress + final results via Server-Sent Events (SSE).

---

## Architecture Diagram

```mermaid
flowchart TD
    Client["Client / User"] -->|POST /api/chat {prompt}| MainAPI["FastAPI Routes (main.py)"]
    
    subgraph Ingress & Protection
        MainAPI -->|IP & Window Check| RateLimiter["Rate Limiter (ratelimit.py)<br/>5 req / 60s per IP"]
        RateLimiter -->|Prompt| IntentParser["Intent Parser (intent.py)<br/>LLM + Heuristic Regex"]
        IntentParser -->|Plan| Validator["Input Validator (validators.py)<br/>Scheme, Credentials, Limits"]
    end

    subgraph Concurrency & Subprocess Execution
        Validator -->|Acquire Slot| SlotManager["Slot Manager (runner.py)<br/>Max 2 concurrent runs"]
        SlotManager -->|Spawn Subprocess| SubprocessRunner["Subprocess Engine (runner.py)<br/>Process Group, Env Isolation, Heartbeat"]
        
        SubprocessRunner -->|Run Allowlisted CLI| CLI["CLI Tool (cli/site_crawler.py / link_checker.py)"]
        
        CLI -->|HTTP Requests| NetPolicy["Shared NetPolicy (netpolicy.py)<br/>SSRF, DNS Resolve, IP Pinning, Robots.txt, Max 3 Hops"]
        NetPolicy -->|Pinned Socket TLS| TargetWeb["Target Website (e.g. example.com)"]
    end

    subgraph Output Validation & Enrichment
        CLI -->|JSON stdout / out-file| PostProcess["Postprocessor (postprocess.py)<br/>Schema Validation, Status, Coverage Score"]
        PostProcess -->|Crawl Data| Extractor["Evidence Extractor (extractor.py)<br/>Every fact with source_url"]
        PostProcess -->|Text Content| InjectionScanner["Injection Detector (injection.py)<br/>Regex & Base64 Scan"]
        PostProcess -->|Untrusted Content| Summarizer["Summarizer (summarizer.py)<br/>Delimited Data Prompt / Heuristic"]
    end

    subgraph Audit & Delivery
        PostProcess -->|Hash Record| AuditLog["Tamper-Evident Audit Chain (runstore.py)<br/>SHA-256 Hash Chaining"]
        AuditLog -->|Final Record| SSEStream["SSE Event Stream (main.py)<br/>received, plan, validated, spawned, progress, parsing, result"]
        SSEStream -->|Streamed Response| Client
    end
```

---

## Core Components

### 1. Intent Parsing & Tool Selection (`app/intent.py`)
- Evaluates the user prompt using LLM if configured; automatically falls back to an exact keyword/regex parser.
- Dispatches `"crawl"`, `"extract"`, `"summarize"` tasks to `site_crawler`.
- Dispatches `"broken links"`, `"dead links"`, `"404"` tasks to `link_checker`.
- Automatically extracts target URLs, focus flags (e.g., `"only emails"`), and clamps pagination and depth to safe boundaries.

### 2. Shared Network Security Policy (`app/netpolicy.py`)
- **Strict SSRF Prevention**: Prohibits private networks (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), loopbacks (`127.0.0.0/8`, `::1`), link-local (`169.254.0.0/16`), metadata IPs (`169.254.169.254`, `fd00:ec2::254`), alternative octal/hex encodings, and IPv4-mapped IPv6.
- **True IP Pinning**: Hostname is resolved once; all addresses are validated. The connection dials the pinned IP directly while preserving the original host header and TLS SNI for certificate validation. Post-connection peer IP verification eliminates DNS rebinding (TOCTOU).
- **Manual Redirects**: Strict maximum of 3 hops, redirect loop detection, destination host re-validation, destination robots.txt checks, and cross-domain redirect blocking unless explicitly allowlisted.
- **Robots.txt & Caps**: In-memory caching per host; 5xx/timeouts fail safe by disallowing; 1MB response body cap; skips non-HTML/XHTML content.

### 3. Subprocess Execution & State Machine (`app/runner.py`)
- Allowlist-only tool registry (`site_crawler`, `link_checker`).
- `shell=False` strictly enforced across all executions; commands constructed solely from validated plan fields.
- Minimal environment provided to child processes (explicitly stripping `LLM_API_KEY`, `LLM_PROVIDER`, etc.).
- Resource isolation with process groups and `psutil` tree-kill on cancellation or timeout.
- Heartbeat monitoring: kills stalled processes if no progress/heartbeat is observed within 15 seconds.
- Bounded concurrency via a 2-slot semaphore (`SlotManager`).

### 4. Post-Processing & Extraction (`app/postprocess.py`, `app/extractor.py`)
- Strict status transitions: `SUCCESS`, `PARTIAL`, `FAILED`, `TIMEOUT`, `CANCELLED`.
- `SUCCESS` is never assigned without parseable, schema-compliant JSON output.
- Coverage score (0–100) computed based on page targets, error ratios, robots skips, and blocked redirects.
- Consolidated `extracted` object where **every single fact** (emails, phones, social links, topics) carries its verified `source_url`.

### 5. Security Scanner & Untrusted Data Handling (`app/injection.py`, `app/summarizer.py`)
- Crawled content is treated strictly as **untrusted data**.
- Content scanned for prompt injection attacks (`"ignore previous instructions"`, system prompt overrides, destructive shell commands, hidden text styling, base64 payloads).
- Summarizer wraps crawled data inside explicit security delimiters (`<<<UNTRUSTED_CRAWLED_DATA_START>>>`) and runs with zero tool access.

### 6. Tamper-Evident Audit Chain (`app/runstore.py`)
- Each executed run generates an immutable audit record containing:
  `{run_id, tool, argv, exit_code, stdout_sha256, state, timestamp, prev_hash, hash}`
- Each block hashes the previous block's digest with its own data (`SHA-256`).
- Accessible via `GET /api/audit`, returning the entire chain along with an active cryptographic `verified` integrity boolean.
