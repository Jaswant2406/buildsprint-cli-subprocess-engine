import React from 'react';
import type { RunEventPayload, RunStatus } from '../types';
import { formatNumber, formatTimestamp } from '../utils/format';

interface ExecutionTimelineProps {
  events: RunEventPayload[];
  runId: string;
  isRunning: boolean;
  terminalStatus?: RunStatus;
  onCancel: () => void;
}

interface StepDefinition {
  id: string;
  label: string;
  description: (latestMatchingEvent: RunEventPayload | undefined) => string;
}

export const ExecutionTimeline: React.FC<ExecutionTimelineProps> = ({
  events,
  runId,
  isRunning,
  terminalStatus,
  onCancel,
}) => {
  // Extract info from events
  const planEvent = events.find((e) => e.event === 'plan');
  const validatedEvent = events.find((e) => e.event === 'validated');
  const spawnedEvent = events.find((e) => e.event === 'spawned');
  const progressEvents = events.filter((e) => e.event === 'progress');
  const latestProgress = progressEvents[progressEvents.length - 1];
  const parsingEvent = events.find((e) => e.event === 'parsing');
  const summarizingEvent = events.find((e) => e.event === 'summarizing');
  const resultEvent = events.find((e) => e.event === 'result');
  const errorEvent = events.find((e) => e.event === 'error');
  const cancelEvent = events.find((e) => e.event === 'cancelled');

  const steps: StepDefinition[] = [
    {
      id: 'validate',
      label: '1. Validate Intent & URL Scheme',
      description: () => {
        if (validatedEvent) {
          const u = (validatedEvent.data.url as string) || '';
          return `Target verified: ${u}`;
        }
        if (planEvent) return 'Intent parsed, validating target URL...';
        return 'Analyzing prompt intent and bounds...';
      },
    },
    {
      id: 'robots',
      label: '2. SSRF Check & Robots.txt NetPolicy',
      description: () => {
        if (spawnedEvent || latestProgress) {
          return 'DNS resolved, public IP pinned, robots.txt allow verified';
        }
        if (validatedEvent) return 'Resolving hostname and enforcing IP pinning...';
        return 'Pending network policy verification';
      },
    },
    {
      id: 'spawn',
      label: '3. Spawn Allowlisted CLI Subprocess',
      description: () => {
        if (spawnedEvent) {
          const pid = spawnedEvent.data.pid;
          const tool = spawnedEvent.data.tool as string;
          const argv = Array.isArray(spawnedEvent.data.argv)
            ? spawnedEvent.data.argv.join(' ')
            : '';
          return `PID ${formatNumber(pid as number)} | Tool: ${tool} | shell=False [${argv.slice(0, 60)}${argv.length > 60 ? '...' : ''}]`;
        }
        return 'Acquiring concurrency slot (max 2)...';
      },
    },
    {
      id: 'crawl',
      label: '4. Execute Web Navigation & Crawl',
      description: () => {
        if (resultEvent) {
          const res = resultEvent.data;
          const json = res.json as Record<string, unknown> | undefined;
          if (json && 'links' in json) {
            const stats = json.stats as Record<string, number> | undefined;
            const checked = stats?.checked ?? 0;
            const total = stats?.total_links ?? checked;
            const broken = stats?.broken ?? 0;
            return `Checked ${formatNumber(checked)} of ${formatNumber(total)} links (${formatNumber(broken)} broken)`;
          }
          const pagesCrawled = (res.pages_crawled as number | undefined) ?? (Array.isArray(json?.pages) ? json.pages.length : 0);
          const maxPages = (planEvent?.data?.max_pages as number | undefined) ?? (planEvent?.data?.tool_args as any)?.max_pages ?? ((res.plan as any)?.max_pages as number | undefined) ?? pagesCrawled;
          const displayTotal = maxPages > 0 ? maxPages : pagesCrawled;
          return `Crawled ${formatNumber(pagesCrawled)} of ${formatNumber(displayTotal)} discoverable pages`;
        }
        if (latestProgress) {
          const current = latestProgress.data.pages_so_far ?? latestProgress.data.pages ?? latestProgress.data.pages_crawled ?? latestProgress.data.current ?? (latestProgress.data.index != null ? (latestProgress.data.index as number) + 1 : 0);
          const total = latestProgress.data.max_pages ?? latestProgress.data.total_pages ?? latestProgress.data.total ?? (planEvent?.data?.max_pages as number | undefined) ?? (planEvent?.data?.tool_args as any)?.max_pages ?? 0;
          const url = (latestProgress.data.url as string) || '';
          if (Number(total) > 0) {
            return `Crawled ${formatNumber(Number(current))} of ${formatNumber(Number(total))} pages ${url ? `(${url})` : ''}`;
          }
          return `Crawled ${formatNumber(Number(current))} pages ${url ? `(${url})` : ''}`;
        }
        if (spawnedEvent) return 'Subprocess active, navigating pages...';
        return 'Pending crawl execution';
      },
    },
    {
      id: 'parse',
      label: '5. Schema Validation & JSON Parsing',
      description: () => {
        if (parsingEvent || summarizingEvent || resultEvent) {
          return 'CLI stdout captured, JSON schema validated, exit code verified';
        }
        return 'Awaiting subprocess stdout JSON payload';
      },
    },
    {
      id: 'summarize',
      label: '6. Evidence Extraction & Grounded Summary',
      description: () => {
        if (resultEvent) {
          return 'Structured facts extracted with source_url provenance, summary generated';
        }
        if (summarizingEvent) return 'Synthesizing key takeaways and extracting facts...';
        return 'Pending post-processing';
      },
    },
  ];

  // Helper to determine step state
  const getStepState = (
    index: number
  ): 'pending' | 'active' | 'done' | 'failed' => {
    if (errorEvent || terminalStatus === 'FAILED' || terminalStatus === 'TIMEOUT') {
      // Find where failure occurred
      if (!validatedEvent && index === 0) return 'failed';
      if (validatedEvent && !spawnedEvent && index <= 1) return index === 1 ? 'failed' : 'done';
      if (spawnedEvent && !latestProgress && index <= 2) return index === 2 ? 'failed' : 'done';
      if (latestProgress && !parsingEvent && index <= 3) return index === 3 ? 'failed' : 'done';
      if (parsingEvent && !resultEvent && index <= 4) return index === 4 ? 'failed' : 'done';
    }

    if (cancelEvent || terminalStatus === 'CANCELLED') {
      if (index === 0 && !validatedEvent) return 'failed';
      if (index === 3 && isRunning) return 'failed';
    }

    if (resultEvent) return 'done';

    // Active progression
    if (index === 0) return validatedEvent ? 'done' : isRunning ? 'active' : 'pending';
    if (index === 1) return spawnedEvent ? 'done' : validatedEvent ? 'active' : 'pending';
    if (index === 2) return spawnedEvent ? 'done' : 'pending';
    if (index === 3) return parsingEvent || resultEvent ? 'done' : spawnedEvent ? 'active' : 'pending';
    if (index === 4) return summarizingEvent || resultEvent ? 'done' : parsingEvent ? 'active' : 'pending';
    if (index === 5) return resultEvent ? 'done' : summarizingEvent ? 'active' : 'pending';

    return 'pending';
  };

  return (
    <div
      className="card-panel"
      style={{ backgroundColor: 'var(--card)' }}
      aria-live="polite"
      aria-atomic="false"
    >
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '8px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className="card-title">Live Execution Timeline</span>
          {runId && (
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '11px',
                color: 'var(--muted)',
                backgroundColor: 'var(--page)',
                padding: '2px 6px',
                borderRadius: '4px',
                border: '1px solid var(--hairline)',
              }}
            >
              Run: {runId.slice(0, 8)}...
            </span>
          )}
        </div>

        {isRunning && (
          <button
            type="button"
            onClick={onCancel}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 14px',
              borderRadius: '6px',
              backgroundColor: 'var(--status-failed-bg)',
              color: 'var(--status-failed-text)',
              border: '1px solid var(--status-failed-text)',
              fontSize: '13px',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            ■ Cancel Subprocess
          </button>
        )}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '8px' }}>
        {steps.map((step, idx) => {
          const state = getStepState(idx);
          const latestEvent = events[events.length - 1];

          let icon = '○';
          let iconColor = 'var(--muted)';
          let bgColor = 'var(--page)';
          let borderColor = 'var(--hairline)';

          if (state === 'done') {
            icon = '✓';
            iconColor = 'var(--status-success-text)';
            bgColor = 'var(--status-success-bg)';
            borderColor = 'var(--status-success-text)';
          } else if (state === 'active') {
            icon = '▶';
            iconColor = '#FFFFFF';
            bgColor = 'var(--navy)';
            borderColor = 'var(--navy)';
          } else if (state === 'failed') {
            icon = '✕';
            iconColor = 'var(--status-failed-text)';
            bgColor = 'var(--status-failed-bg)';
            borderColor = 'var(--status-failed-text)';
          }

          return (
            <div
              key={step.id}
              style={{
                display: 'grid',
                gridTemplateColumns: '32px 1fr auto',
                gap: '12px',
                alignItems: 'start',
                minWidth: 0,
              }}
            >
              {/* State icon container */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '28px',
                  height: '28px',
                  borderRadius: '50%',
                  backgroundColor: bgColor,
                  border: `1px solid ${borderColor}`,
                  color: iconColor,
                  fontWeight: 700,
                  fontSize: '13px',
                }}
              >
                {icon}
              </div>

              {/* Step info */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', minWidth: 0 }}>
                <span
                  style={{
                    fontFamily: 'var(--font-display)',
                    fontWeight: 700,
                    fontSize: '14px',
                    color: state === 'active' ? 'var(--navy)' : 'var(--ink)',
                  }}
                >
                  {step.label}
                </span>
                <span className="caption" style={{ color: 'var(--muted)', overflowWrap: 'anywhere' }}>
                  {step.description(latestEvent)}
                </span>
              </div>

              {/* Timestamp */}
              <div style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                <span className="caption" style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--muted)' }}>
                  {latestEvent?.timestamp ? formatTimestamp(latestEvent.timestamp) : ''}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
