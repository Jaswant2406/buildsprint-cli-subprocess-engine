import React from 'react';
import type { ChatResult, RunEventPayload, RunStatus } from '../types';
import { formatNumber, formatTimestamp } from '../utils/format';

interface ExecutionTimelineProps {
  events: RunEventPayload[];
  runId: string;
  isRunning: boolean;
  terminalStatus?: RunStatus;
  onCancel: () => void;
}

type StepState = 'pending' | 'active' | 'done' | 'failed' | 'not_executed' | 'skipped';

interface StepDefinition {
  id: string;
  label: string;
  getDescription: (state: StepState, latestMatchingEvent: RunEventPayload | undefined) => string;
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

  const errorMsg = errorEvent ? String(errorEvent.data?.error || '') : '';
  const errorReason = errorEvent ? String(errorEvent.data?.reason || '') : '';

  const isDnsError =
    errorReason === 'dns_resolution_failed' ||
    errorMsg.toLowerCase().includes('dns resolution') ||
    errorMsg.toLowerCase().includes('getaddrinfo') ||
    errorMsg.toLowerCase().includes('name or service not known') ||
    errorMsg.toLowerCase().includes('could not resolve') ||
    (errorMsg.toLowerCase().includes('unreachable') && !errorMsg.toLowerCase().includes('ssrf'));

  const isSsrfError =
    errorReason === 'ssrf_blocked' ||
    errorMsg.toLowerCase().includes('ssrf') ||
    errorMsg.toLowerCase().includes('forbidden address') ||
    errorMsg.toLowerCase().includes('forbidden ip') ||
    errorMsg.toLowerCase().includes('loopback');

  const isTerminated =
    !!errorEvent ||
    terminalStatus === 'FAILED' ||
    terminalStatus === 'TIMEOUT' ||
    terminalStatus === 'CANCELLED' ||
    !!cancelEvent;

  // Determine the state of each step index
  const getStepState = (index: number): StepState => {
    // 1. Terminal Failure / Cancellation / Timeout cases
    if (isTerminated) {
      if (cancelEvent || terminalStatus === 'CANCELLED') {
        if (!spawnedEvent) {
          if (index === 0) return planEvent ? 'done' : 'failed';
          if (index === 1) return validatedEvent ? 'done' : 'skipped';
          if (index === 2) return 'not_executed';
          return 'skipped';
        }
        if (index <= 2) return 'done';
        if (index === 3) return 'failed';
        return 'skipped';
      }

      if (terminalStatus === 'TIMEOUT') {
        if (!spawnedEvent) {
          if (index === 0) return planEvent ? 'done' : 'failed';
          if (index === 1) return validatedEvent ? 'done' : 'skipped';
          if (index === 2) return 'not_executed';
          return 'skipped';
        }
        if (index <= 2) return 'done';
        if (index === 3) return 'failed';
        return 'skipped';
      }

      // errorEvent or terminalStatus === 'FAILED'
      if (!validatedEvent) {
        // Failure occurred during URL validation (either syntax or DNS / SSRF resolution)
        if (isDnsError || isSsrfError) {
          // Syntax was valid, DNS or NetPolicy check failed at step 1
          if (index === 0) return 'done';
          if (index === 1) return 'failed';
          if (index === 2) return 'not_executed';
          return 'skipped';
        }
        // Generic or URL scheme/syntax validation failure at step 0
        if (index === 0) return 'failed';
        if (index === 1) return 'skipped';
        if (index === 2) return 'not_executed';
        return 'skipped';
      }

      if (!spawnedEvent) {
        // Validation passed, but failed before/at spawning (e.g. concurrency slot timeout)
        if (index === 0) return 'done';
        if (index === 1) return 'done';
        if (index === 2) return 'failed';
        return 'skipped';
      }

      if (spawnedEvent && !latestProgress && !parsingEvent && !resultEvent) {
        // Subprocess launched, but crawler failed immediately during execution
        if (index <= 2) return 'done';
        if (index === 3) return 'failed';
        return 'skipped';
      }

      if (latestProgress && !parsingEvent && !resultEvent) {
        // Crawler made progress but encountered terminal failure
        if (index <= 2) return 'done';
        if (index === 3) return 'failed';
        return 'skipped';
      }

      if (parsingEvent && !resultEvent) {
        // Crawl completed, but schema validation or parsing failed
        if (index <= 3) return 'done';
        if (index === 4) return 'failed';
        return 'skipped';
      }
    }

    // 2. Success completion
    if (resultEvent) return 'done';

    // 3. Normal Active progression
    if (index === 0) return validatedEvent ? 'done' : isRunning ? 'active' : 'pending';
    if (index === 1) return spawnedEvent ? 'done' : validatedEvent ? 'active' : 'pending';
    if (index === 2) return spawnedEvent ? 'done' : 'pending';
    if (index === 3) return parsingEvent || resultEvent ? 'done' : spawnedEvent ? 'active' : 'pending';
    if (index === 4) return summarizingEvent || resultEvent ? 'done' : parsingEvent ? 'active' : 'pending';
    if (index === 5) return resultEvent ? 'done' : summarizingEvent ? 'active' : 'pending';

    return 'pending';
  };

  const steps: StepDefinition[] = [
    {
      id: 'validate',
      label: '1. Validate Intent & URL Scheme',
      getDescription: (state) => {
        if (state === 'failed') {
          return errorMsg || 'Target URL scheme validation failed';
        }
        if (validatedEvent) {
          const u = (validatedEvent.data.url as string) || '';
          return `Target verified: ${u}`;
        }
        if (planEvent) return 'Intent parsed, valid URL scheme accepted';
        if (isRunning) return 'Analyzing prompt intent and bounds...';
        return 'Pending prompt intent analysis';
      },
    },
    {
      id: 'robots',
      label: '2. SSRF Check & Robots.txt NetPolicy',
      getDescription: (state) => {
        if (state === 'failed') {
          if (isDnsError) {
            return errorMsg || 'DNS resolution failed: host unreachable or domain does not exist';
          }
          if (isSsrfError) {
            return errorMsg || 'SSRF policy violation: IP address is forbidden';
          }
          return errorMsg || 'Network policy check failed';
        }
        if (state === 'skipped') {
          return 'Skipped due to prior validation error';
        }
        if (spawnedEvent || latestProgress || state === 'done') {
          return 'DNS resolved, public IP pinned, robots.txt allow verified';
        }
        if (state === 'active') return 'Resolving hostname and enforcing IP pinning...';
        return 'Pending network policy verification';
      },
    },
    {
      id: 'spawn',
      label: '3. Spawn Allowlisted CLI Subprocess',
      getDescription: (state) => {
        if (state === 'not_executed') {
          return 'No CLI subprocess was launched (execution rejected prior to spawning).';
        }
        if (state === 'failed') {
          return errorMsg || 'Could not spawn subprocess (concurrency full or system error)';
        }
        if (spawnedEvent) {
          const pid = spawnedEvent.data.pid;
          const tool = spawnedEvent.data.tool as string;
          const argv = Array.isArray(spawnedEvent.data.argv)
            ? spawnedEvent.data.argv.join(' ')
            : '';
          return `PID ${formatNumber(pid as number)} | Tool: ${tool} | shell=False [${argv.slice(0, 60)}${argv.length > 60 ? '...' : ''}]`;
        }
        if (state === 'skipped') return 'Not executed (pipeline stopped)';
        return 'Acquiring concurrency slot (max 2)...';
      },
    },
    {
      id: 'crawl',
      label: '4. Execute Web Navigation & Crawl',
      getDescription: (state) => {
        if (state === 'skipped') return 'Skipped (no navigation attempted)';
        if (state === 'failed') {
          if (cancelEvent || terminalStatus === 'CANCELLED') {
            return 'Crawl subprocess cancelled by user';
          }
          if (terminalStatus === 'TIMEOUT') {
            return 'Crawl subprocess timed out';
          }
          return errorMsg || 'Subprocess execution failed during navigation';
        }
        if (resultEvent) {
          const res = resultEvent.data as unknown as Partial<ChatResult>;
          const json = res.json as Record<string, unknown> | undefined;
          if (json && 'links' in json) {
            const stats = json.stats as Record<string, number> | undefined;
            const checked = stats?.checked ?? 0;
            const total = stats?.total_links ?? checked;
            const broken = stats?.broken ?? 0;
            return `Checked ${formatNumber(checked)} of ${formatNumber(total)} links (${formatNumber(broken)} broken)`;
          }
          const pagesCrawled =
            (res.coverage?.pages_crawled as number | undefined) ??
            (res.pages_crawled as number | undefined) ??
            (Array.isArray(json?.pages) ? json.pages.length : 0);
          const pagesDiscovered =
            (res.coverage?.pages_discovered as number | undefined) ??
            (json?.stats as any)?.pages_discovered ??
            pagesCrawled;
          const pagesLimit =
            (res.coverage?.pages_limit as number | undefined) ??
            (planEvent?.data?.max_pages as number | undefined) ??
            (planEvent?.data?.tool_args as any)?.max_pages ??
            ((res.plan as any)?.max_pages as number | undefined) ??
            10;
          return `Crawled ${formatNumber(pagesCrawled)} of ${formatNumber(pagesDiscovered)} discovered page${pagesDiscovered === 1 ? '' : 's'} (limit: ${formatNumber(pagesLimit)})`;
        }
        if (latestProgress) {
          const current =
            latestProgress.data.pages_so_far ??
            latestProgress.data.pages ??
            latestProgress.data.pages_crawled ??
            latestProgress.data.current ??
            (latestProgress.data.index != null ? (latestProgress.data.index as number) + 1 : 0);
          const total =
            latestProgress.data.max_pages ??
            latestProgress.data.total_pages ??
            latestProgress.data.total ??
            (planEvent?.data?.max_pages as number | undefined) ??
            (planEvent?.data?.tool_args as any)?.max_pages ??
            0;
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
      getDescription: (state) => {
        if (state === 'skipped') return 'Skipped (no output to validate)';
        if (state === 'failed') {
          return errorMsg || 'CLI stdout parsing or JSON schema validation failed';
        }
        if (parsingEvent || summarizingEvent || resultEvent) {
          return 'CLI stdout captured, JSON schema validated, exit code verified';
        }
        return 'Awaiting subprocess stdout JSON payload';
      },
    },
    {
      id: 'summarize',
      label: '6. Evidence Extraction & Grounded Summary',
      getDescription: (state) => {
        if (state === 'skipped') return 'Skipped (no extracted data to summarize)';
        if (resultEvent) {
          return 'Structured facts extracted with source_url provenance, summary generated';
        }
        if (summarizingEvent) return 'Synthesizing key takeaways and extracting facts...';
        return 'Pending post-processing';
      },
    },
  ];

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

      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '12px' }}>
        {steps.map((step, idx) => {
          const state = getStepState(idx);
          const latestEvent = events[events.length - 1];

          let icon = '○';
          let iconColor = 'var(--muted)';
          let bgColor = 'var(--page)';
          let borderColor = 'var(--hairline)';
          let badgeLabel = 'Pending';
          let badgeBg = 'var(--page)';
          let badgeColor = 'var(--muted)';
          let badgeBorder = '1px solid var(--hairline)';

          if (state === 'done') {
            icon = '✓';
            iconColor = 'var(--status-success-text)';
            bgColor = 'var(--status-success-bg)';
            borderColor = 'var(--status-success-text)';
            badgeLabel = 'Done';
            badgeBg = 'var(--status-success-bg)';
            badgeColor = 'var(--status-success-text)';
            badgeBorder = '1px solid var(--status-success-text)';
          } else if (state === 'active') {
            icon = '▶';
            iconColor = '#FFFFFF';
            bgColor = 'var(--navy)';
            borderColor = 'var(--navy)';
            badgeLabel = 'In Progress';
            badgeBg = 'var(--navy)';
            badgeColor = '#FFFFFF';
            badgeBorder = '1px solid var(--navy)';
          } else if (state === 'failed') {
            icon = '✕';
            iconColor = 'var(--status-failed-text)';
            bgColor = 'var(--status-failed-bg)';
            borderColor = 'var(--status-failed-text)';
            badgeLabel = 'Failed';
            badgeBg = 'var(--status-failed-bg)';
            badgeColor = 'var(--status-failed-text)';
            badgeBorder = '1px solid var(--status-failed-text)';
          } else if (state === 'not_executed') {
            icon = '⊘';
            iconColor = 'var(--muted)';
            bgColor = 'var(--page)';
            borderColor = 'var(--hairline)';
            badgeLabel = 'Not Executed';
            badgeBg = 'var(--page)';
            badgeColor = 'var(--muted)';
            badgeBorder = '1px solid var(--hairline)';
          } else if (state === 'skipped') {
            icon = '↷';
            iconColor = 'var(--muted)';
            bgColor = 'var(--page)';
            borderColor = 'var(--hairline)';
            badgeLabel = 'Skipped';
            badgeBg = 'var(--page)';
            badgeColor = 'var(--muted)';
            badgeBorder = '1px solid var(--hairline)';
          }

          return (
            <div
              key={step.id}
              data-testid={`timeline-step-${step.id}`}
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
              <div style={{ display: 'flex', flexDirection: 'column', gap: '3px', minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
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
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: '10px',
                      fontWeight: 700,
                      textTransform: 'uppercase',
                      padding: '1px 6px',
                      borderRadius: '4px',
                      backgroundColor: badgeBg,
                      color: badgeColor,
                      border: badgeBorder,
                    }}
                  >
                    {badgeLabel}
                  </span>
                </div>
                <span
                  className="caption"
                  style={{
                    color: state === 'failed' ? 'var(--status-failed-text)' : 'var(--muted)',
                    overflowWrap: 'anywhere',
                    lineHeight: '1.4',
                  }}
                >
                  {step.getDescription(state, latestEvent)}
                </span>
              </div>

              {/* Timestamp */}
              <div style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                <span
                  className="caption"
                  style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--muted)' }}
                >
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
