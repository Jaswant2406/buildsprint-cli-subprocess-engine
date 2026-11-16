export type RunState =
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'timeout'
  | 'stalled'
  | 'cancelled';

export type RunStatus = 'SUCCESS' | 'PARTIAL' | 'FAILED' | 'TIMEOUT' | 'CANCELLED';

export interface Plan {
  task_type: string;
  tool: 'site_crawler' | 'link_checker';
  tool_reason: string;
  url: string;
  max_pages: number;
  max_depth: number;
  wants_summary: boolean;
  wants_json: boolean;
  extract_focus: string;
  max_links: number;
}

export interface SecurityFinding {
  pattern: string;
  severity: string;
  snippet: string;
  page_url?: string;
}

export interface ExtractedFact {
  fact_type: string;
  value: string;
  source_url: string;
  context?: string;
}

export interface CoverageBreakdown {
  score?: number | null;
  pages_crawled?: number;
  pages_discovered?: number;
  pages_limit?: number;
  page_limit_utilization?: number;
  discovered_ratio?: number;
  coverage_established?: boolean;
  error_ratio?: number;
  robots_skips?: number;
  redirects_blocked?: number;
  notes?: string;
}

export interface JobRecord {
  title?: string | null;
  company?: string | null;
  location?: string | null;
  date_posted?: string | null;
  description?: string | null;
  job_url?: string | null;
  apply_url?: string | null;
  source_url: string;
}

export interface JobExtractionStats {
  total_jobs: number;
  companies: number;
  locations: number;
  with_job_url?: number;
  with_apply_url: number;
  with_date: number;
  with_description: number;
  crawled_detail_pages?: number;
  is_partial_crawl?: boolean;
  coverage_note?: string;
}

export interface JobExtractionResult {
  records: JobRecord[];
  stats: JobExtractionStats;
}

export interface ChatResult {
  run_id: string;
  status: RunStatus;
  status_reason: string;
  plan?: Plan;
  exit_code?: number;
  duration_s?: number;
  pages_crawled?: number;
  json?: Record<string, unknown>;
  summary?: string;
  key_takeaways?: string[];
  extracted?: {
    emails?: ExtractedFact[];
    phones?: ExtractedFact[];
    socials?: ExtractedFact[];
    topics?: ExtractedFact[];
    facts?: ExtractedFact[];
    [key: string]: unknown;
  };
  security_findings?: SecurityFinding[];
  coverage?: CoverageBreakdown;
  coverage_score?: number;
  coverage_breakdown?: string;
  jobs?: JobExtractionResult;
  audit_hash?: string;
}

export interface RunEventPayload {
  run_id: string;
  event: string;
  data: Record<string, unknown>;
  timestamp?: string;
}

export interface AuditRecord {
  run_id: string;
  tool: string;
  argv: string[];
  exit_code: number;
  stdout_sha256: string;
  state: string;
  timestamp: string;
  prev_hash: string;
  hash: string;
}

export interface AuditChain {
  verified: boolean;
  length?: number;
  entries?: AuditRecord[];
  records?: AuditRecord[];
}

export interface HealthResponse {
  llm_mode: string;
  version: string;
  status: string;
}

export interface ToolConfig {
  name: string;
  description: string;
  executable: string;
  max_concurrency: number;
  timeout_s: number;
  shell: boolean;
}

export interface RunListItem {
  run_id: string;
  prompt: string;
  state: RunState;
  status?: RunStatus;
  created_at: string;
  duration_s?: number;
  pages_crawled?: number;
}
