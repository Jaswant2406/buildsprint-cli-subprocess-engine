import type {
  AuditChain,
  HealthResponse,
  RunEventPayload,
  RunListItem,
  ToolConfig,
} from '../types';
import { consumeSSEStream } from './sse';

export const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

export interface ApiError {
  status: number;
  message: string;
  retry_after_s?: number;
}

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE}/api/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return res.json();
}

export async function fetchAudit(): Promise<AuditChain> {
  const res = await fetch(`${API_BASE}/api/audit`);
  if (!res.ok) throw new Error(`Audit chain failed: ${res.status}`);
  return res.json();
}

export async function fetchTools(): Promise<ToolConfig[]> {
  const res = await fetch(`${API_BASE}/api/tools`);
  if (!res.ok) throw new Error(`Tools query failed: ${res.status}`);
  const data = await res.json();
  return data.tools || [];
}

export async function fetchRuns(): Promise<RunListItem[]> {
  const res = await fetch(`${API_BASE}/api/runs`);
  if (!res.ok) throw new Error(`Runs query failed: ${res.status}`);
  const data = await res.json();
  if (Array.isArray(data)) {
    return data.map((item: Record<string, any>) => ({
      run_id: item.run_id,
      prompt: item.plan?.url || (Array.isArray(item.argv) ? item.argv.join(' ') : '') || item.run_id,
      state: item.state,
      status: item.result?.status,
      created_at: item.events?.[0]?.ts
        ? new Date(item.events[0].ts * 1000).toISOString()
        : new Date().toISOString(),
      duration_s: item.duration_s,
    }));
  }
  return data.runs || [];
}

export async function fetchRun(runId: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/api/runs/${runId}`);
  if (!res.ok) throw new Error(`Run query failed: ${res.status}`);
  return res.json();
}

export async function fetchLogs(runId: string): Promise<{ stdout: string; stderr: string; events: unknown[] }> {
  const res = await fetch(`${API_BASE}/api/runs/${runId}/logs`);
  if (!res.ok) throw new Error(`Logs query failed: ${res.status}`);
  return res.json();
}

export async function cancelRun(runId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/runs/${runId}/cancel`, {
    method: 'POST',
  });
  if (!res.ok && res.status !== 409) {
    throw new Error(`Cancel failed with status ${res.status}`);
  }
}

export async function askRun(runId: string, question: string): Promise<{ answer: string; citations: string[] }> {
  const res = await fetch(`${API_BASE}/api/runs/${runId}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail?.error || `Ask failed with status ${res.status}`);
  }
  return res.json();
}

export async function replayRunStream(
  runId: string,
  onEvent: (event: RunEventPayload) => void,
  signal?: AbortSignal
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/runs/${runId}/replay`, {
    method: 'POST',
    signal,
  });
  if (!res.ok || !res.body) {
    throw new Error(`Replay failed with status ${res.status}`);
  }
  await consumeSSEStream(res.body, onEvent, signal);
}

export async function startChatStream(
  prompt: string,
  onEvent: (event: RunEventPayload) => void,
  signal?: AbortSignal
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt }),
      signal,
    });
  } catch (err: unknown) {
    if (signal?.aborted) return;
    throw new Error(err instanceof Error ? err.message : 'Backend unreachable');
  }

  if (!res.ok) {
    let errorDetail = `Request failed: ${res.status}`;
    let retryAfter: number | undefined;

    try {
      const errJson = await res.json();
      if (errJson.detail) {
        if (typeof errJson.detail === 'string') {
          errorDetail = errJson.detail;
        } else if (errJson.detail.error) {
          errorDetail = errJson.detail.error;
          if (errJson.detail.retry_after_s) {
            retryAfter = Number(errJson.detail.retry_after_s);
          }
        }
      }
    } catch {
      // ignore json parse error
    }

    const errObj: ApiError = {
      status: res.status,
      message: errorDetail,
      retry_after_s: retryAfter,
    };
    throw errObj;
  }

  if (!res.body) {
    throw new Error('No response body received from chat stream');
  }

  await consumeSSEStream(res.body, onEvent, signal);
}
