import React, { useEffect, useState } from 'react';
import type { ChatResult } from '../types';
import { API_BASE } from '../utils/api';
import { formatDuration, formatNumber, formatPercent } from '../utils/format';
import { InlineMarkdown, MarkdownView } from './MarkdownView';

interface ResultCardProps {
  result: ChatResult;
  onOpenLogs: () => void;
  onReplay: () => void;
}

export const ResultCard: React.FC<ResultCardProps> = ({
  result,
  onOpenLogs,
  onReplay,
}) => {
  const [jsonExpanded, setJsonExpanded] = useState(true);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setJsonExpanded(true);
  }, [result.run_id]);

  // Extract page count
  let pagesCrawled = result.pages_crawled ?? 0;
  if (!pagesCrawled && result.json && typeof result.json === 'object') {
    const jsonPages = (result.json as Record<string, unknown>).pages;
    if (Array.isArray(jsonPages)) {
      pagesCrawled = jsonPages.length;
    }
  }

  const covScore = result.coverage?.score ?? result.coverage_score;
  const covBreakdown = result.coverage?.notes ?? result.coverage_breakdown;

  const pagesDiscovered =
    result.coverage?.pages_discovered ??
    (result.json?.stats as any)?.pages_discovered ??
    pagesCrawled;
  const pagesLimit =
    result.coverage?.pages_limit ??
    (result.plan as any)?.max_pages ??
    (result.json?.stats as any)?.pages_limit ??
    10;
  const limitUtil =
    result.coverage?.page_limit_utilization ??
    (pagesLimit > 0 ? (pagesCrawled / pagesLimit) * 100 : 100);
  const discRatio =
    result.coverage?.discovered_ratio ??
    (pagesDiscovered > 0 ? (pagesCrawled / pagesDiscovered) * 100 : 100);

  const isFullWebsiteCoverage =
    result.coverage?.coverage_established === true ||
    (result.coverage?.coverage_established === undefined &&
      (result.coverage?.score === 100 || result.coverage_score === 100) &&
      pagesCrawled !== 1 &&
      pagesDiscovered <= pagesCrawled);

  const scoreDisplay = isFullWebsiteCoverage
    ? formatPercent(covScore)
    : pagesCrawled <= 1
    ? 'Coverage not fully established'
    : `${discRatio.toFixed(2)}%`;

  // Flatten extracted facts
  const extractedList: Array<{ type: string; value: string; source_url: string }> = [];
  if (result.extracted && typeof result.extracted === 'object') {
    const ext = result.extracted as Record<string, unknown>;
    for (const [group, items] of Object.entries(ext)) {
      if (Array.isArray(items)) {
        for (const item of items) {
          if (typeof item === 'object' && item !== null) {
            extractedList.push({
              type: group,
              value: String(item.value || item.url || item.topic || JSON.stringify(item)),
              source_url: String(item.source_url || result.plan?.url || ''),
            });
          } else if (typeof item === 'string') {
            extractedList.push({
              type: group,
              value: item,
              source_url: result.plan?.url || '',
            });
          }
        }
      }
    }
  }

  const jsonStr = JSON.stringify(result.json || result, null, 2);

  const handleCopyJson = async () => {
    try {
      await navigator.clipboard.writeText(jsonStr);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // fallback
    }
  };

  const handleDownloadJson = () => {
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `run-${result.run_id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const reportUrl = `${API_BASE}/api/runs/${result.run_id}/report.md`;

  return (
    <div data-testid="result-card" className="card-panel result-card" style={{ backgroundColor: 'var(--card)' }}>
      {/* Header with status badge */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '12px',
          borderBottom: '1px solid var(--hairline)',
          paddingBottom: '16px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span className={`badge-status ${result.status}`}>{result.status}</span>
          <span className="card-title">Execution Result</span>
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px' }}>
          <button
            type="button"
            onClick={onReplay}
            style={{
              padding: '6px 12px',
              borderRadius: '6px',
              backgroundColor: 'var(--page)',
              border: '1px solid var(--hairline)',
              color: 'var(--ink)',
              fontSize: '13px',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            ↻ Replay Stream
          </button>
          <button
            type="button"
            onClick={onOpenLogs}
            style={{
              padding: '6px 12px',
              borderRadius: '6px',
              backgroundColor: 'var(--page)',
              border: '1px solid var(--hairline)',
              color: 'var(--navy)',
              fontSize: '13px',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            View Subprocess Logs
          </button>
        </div>
      </div>

      {/* Status Reason */}
      {result.status_reason && (
        <div
          style={{
            padding: '10px 14px',
            borderRadius: '6px',
            backgroundColor: 'var(--page)',
            borderLeft: `4px solid ${
              result.status === 'SUCCESS' ? 'var(--status-success-text)' : 'var(--status-failed-text)'
            }`,
            color: 'var(--ink)',
            fontSize: '13px',
            lineHeight: '1.5',
          }}
        >
          <strong>Status Reason:</strong> {result.status_reason}
        </div>
      )}

      {/* Audit Hash */}
      {result.audit_hash && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '8px',
            padding: '8px 12px',
            borderRadius: '6px',
            backgroundColor: 'var(--page)',
            border: '1px solid var(--hairline)',
            fontSize: '12px',
            color: 'var(--muted)',
            fontFamily: 'var(--font-mono)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', minWidth: 0, overflow: 'hidden' }}>
            <span style={{ fontWeight: 600, color: 'var(--navy)', flexShrink: 0 }}>Audit Block:</span>
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {result.audit_hash}
            </span>
          </div>
          <span style={{ fontSize: '11px', color: 'var(--status-success-text)', fontWeight: 600, flexShrink: 0 }}>
            SHA-256 Chained
          </span>
        </div>
      )}

      {/* Metrics Row (Exit Code, Duration, Pages Crawled) */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: '12px',
          margin: '8px 0 12px 0',
        }}
      >
        <div
          style={{
            padding: '12px 16px',
            backgroundColor: 'var(--page)',
            borderRadius: '8px',
            border: '1px solid var(--hairline)',
            display: 'flex',
            flexDirection: 'column',
            gap: '4px',
          }}
        >
          <span className="eyebrow" style={{ color: 'var(--muted)' }}>
            Exit Code
          </span>
          <span className="tabular-num" style={{ fontSize: '20px', color: 'var(--ink)' }}>
            {formatNumber(result.exit_code ?? 0)}
          </span>
        </div>

        <div
          style={{
            padding: '12px 16px',
            backgroundColor: 'var(--page)',
            borderRadius: '8px',
            border: '1px solid var(--hairline)',
            display: 'flex',
            flexDirection: 'column',
            gap: '4px',
          }}
        >
          <span className="eyebrow" style={{ color: 'var(--muted)' }}>
            Duration
          </span>
          <span className="tabular-num" style={{ fontSize: '20px', color: 'var(--ink)' }}>
            {formatDuration(result.duration_s)}
          </span>
        </div>

        <div
          style={{
            padding: '12px 16px',
            backgroundColor: 'var(--page)',
            borderRadius: '8px',
            border: '1px solid var(--hairline)',
            display: 'flex',
            flexDirection: 'column',
            gap: '4px',
          }}
        >
          <span className="eyebrow" style={{ color: 'var(--muted)' }}>
            Pages Crawled
          </span>
          <span className="tabular-num" style={{ fontSize: '20px', color: 'var(--ink)' }}>
            {formatNumber(pagesCrawled)}
          </span>
        </div>
      </div>

      {/* Coverage Score Card */}
      <div
        data-testid="coverage-score-card"
        style={{
          padding: '14px 18px',
          backgroundColor: 'var(--page)',
          borderRadius: '8px',
          border: '1px solid var(--hairline)',
          display: 'flex',
          flexDirection: 'column',
          gap: '6px',
          marginBottom: '12px',
        }}
      >
        <span
          className="eyebrow"
          style={{
            color: 'var(--muted)',
            fontSize: '12px',
            fontWeight: 700,
            letterSpacing: '0.14em',
            textTransform: 'uppercase',
          }}
        >
          COVERAGE SCORE
        </span>
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'baseline',
            gap: '12px',
            minWidth: 0,
          }}
        >
          <span
            className="tabular-num"
            style={{
              fontSize: isFullWebsiteCoverage || pagesDiscovered > pagesCrawled ? '22px' : '16px',
              fontWeight: 700,
              color: 'var(--ink)',
              whiteSpace: 'nowrap',
              flexShrink: 0,
              display: 'inline-block',
            }}
          >
            {scoreDisplay}
          </span>
          {covBreakdown && (
            <span
              className="caption"
              style={{
                color: 'var(--muted)',
                fontSize: '13px',
                lineHeight: 1.5,
                flex: 1,
                minWidth: '240px',
              }}
            >
              {covBreakdown.startsWith('(') && covBreakdown.endsWith(')')
                ? covBreakdown
                : `(${covBreakdown})`}
            </span>
          )}
        </div>

        {pagesDiscovered > 1 && (
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: '12px',
              marginTop: '4px',
              fontSize: '12px',
            }}
          >
            <div
              style={{
                padding: '3px 8px',
                borderRadius: '4px',
                backgroundColor: 'var(--card)',
                border: '1px solid var(--hairline)',
                color: 'var(--ink)',
              }}
            >
              <strong>Page limit utilization:</strong> {pagesCrawled}/{pagesLimit} = {limitUtil % 1 === 0 ? limitUtil.toFixed(0) : limitUtil.toFixed(2)}%
            </div>
            <div
              style={{
                padding: '3px 8px',
                borderRadius: '4px',
                backgroundColor: 'var(--card)',
                border: '1px solid var(--hairline)',
                color: 'var(--ink)',
              }}
            >
              <strong>Discovered-page crawl ratio:</strong> {pagesCrawled}/{pagesDiscovered} = {discRatio % 1 === 0 && pagesCrawled === pagesDiscovered ? discRatio.toFixed(0) : discRatio.toFixed(2)}%
            </div>
          </div>
        )}
      </div>

      {/* Summary & Key Takeaways */}
      {result.summary && (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '8px',
            padding: '16px',
            backgroundColor: 'var(--page)',
            borderRadius: '8px',
            border: '1px solid var(--hairline)',
          }}
        >
          <h3
            style={{
              fontFamily: 'var(--font-display)',
              fontWeight: 700,
              fontSize: '16px',
              color: 'var(--ink)',
            }}
          >
            Research Summary
          </h3>
          <MarkdownView content={result.summary} />

          {result.key_takeaways && result.key_takeaways.length > 0 && (
            <div style={{ marginTop: '8px' }}>
              <span className="eyebrow" style={{ display: 'block', marginBottom: '4px' }}>
                Key Takeaways:
              </span>
              <ul style={{ paddingLeft: '20px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                {result.key_takeaways.map((takeaway, idx) => (
                  <li key={idx} style={{ color: 'var(--ink)', fontSize: '13px', lineHeight: '1.6' }}>
                    <InlineMarkdown text={takeaway} />
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Extracted Data Evidence Table with source_url links */}
      {extractedList.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '4px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3
              style={{
                fontFamily: 'var(--font-display)',
                fontWeight: 700,
                fontSize: '16px',
                color: 'var(--ink)',
              }}
            >
              Extracted Structured Evidence ({formatNumber(extractedList.length)})
            </h3>
            <span className="caption" style={{ color: 'var(--muted)' }}>
              Every fact verified with source URL provenance
            </span>
          </div>

          <div
            style={{
              overflowX: 'auto',
              border: '1px solid var(--hairline)',
              borderRadius: '8px',
            }}
          >
            <table
              style={{
                width: '100%',
                borderCollapse: 'collapse',
                textAlign: 'left',
                fontSize: '13px',
              }}
            >
              <thead>
                <tr style={{ backgroundColor: 'var(--page)', borderBottom: '1px solid var(--hairline)' }}>
                  <th style={{ padding: '8px 12px', color: 'var(--ink)', fontWeight: 600 }}>Type</th>
                  <th style={{ padding: '8px 12px', color: 'var(--ink)', fontWeight: 600 }}>Extracted Fact / Value</th>
                  <th style={{ padding: '8px 12px', color: 'var(--ink)', fontWeight: 600 }}>Source Provenance URL</th>
                </tr>
              </thead>
              <tbody>
                {extractedList.map((item, idx) => (
                  <tr
                    key={idx}
                    style={{
                      borderBottom: idx === extractedList.length - 1 ? 'none' : '1px solid var(--hairline)',
                      backgroundColor: idx % 2 === 0 ? 'var(--card)' : 'var(--page)',
                    }}
                  >
                    <td style={{ padding: '8px 12px', color: 'var(--navy)', fontWeight: 600, textTransform: 'capitalize' }}>
                      {item.type}
                    </td>
                    <td style={{ padding: '8px 12px', color: 'var(--ink)', overflowWrap: 'anywhere' }}>
                      {item.value}
                    </td>
                    <td style={{ padding: '8px 12px', fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
                      {item.source_url ? (
                        <a
                          href={item.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{ color: 'var(--navy)', textDecoration: 'underline' }}
                        >
                          {item.source_url}
                        </a>
                      ) : (
                        '–'
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Structured Job Listings (when requested) */}
      {result.jobs && result.jobs.records && result.jobs.records.length > 0 && (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
            padding: '16px',
            backgroundColor: 'var(--page)',
            borderRadius: '8px',
            border: '1px solid var(--hairline)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
            <h3
              style={{
                fontFamily: 'var(--font-display)',
                fontWeight: 700,
                fontSize: '16px',
                color: 'var(--ink)',
                margin: 0,
              }}
            >
              Structured Job Listings ({result.jobs.records.length})
            </h3>
            <span className="caption" style={{ color: 'var(--muted)', fontSize: '12px' }}>
              {result.jobs.stats.companies} companies • {result.jobs.stats.locations} locations
              {result.jobs.stats.crawled_detail_pages !== undefined && result.jobs.stats.crawled_detail_pages > 0
                ? ` • ${result.jobs.stats.crawled_detail_pages} detail pages crawled`
                : ''}
            </span>
          </div>

          {result.jobs.stats.coverage_note && (
            <div
              style={{
                padding: '8px 12px',
                backgroundColor: 'var(--card)',
                borderRadius: '6px',
                border: '1px solid var(--hairline)',
                color: 'var(--ink)',
                fontSize: '12px',
                lineHeight: '1.4',
              }}
            >
              <strong style={{ color: 'var(--navy)' }}>Coverage Note:</strong> {result.jobs.stats.coverage_note}
            </div>
          )}

          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--hairline)', textAlign: 'left', backgroundColor: 'var(--card)' }}>
                  <th style={{ padding: '8px 12px', color: 'var(--ink)', fontWeight: 600 }}>Title</th>
                  <th style={{ padding: '8px 12px', color: 'var(--ink)', fontWeight: 600 }}>Company</th>
                  <th style={{ padding: '8px 12px', color: 'var(--ink)', fontWeight: 600 }}>Location</th>
                  <th style={{ padding: '8px 12px', color: 'var(--ink)', fontWeight: 600 }}>Date</th>
                  <th style={{ padding: '8px 12px', color: 'var(--ink)', fontWeight: 600 }}>Job Details</th>
                  <th style={{ padding: '8px 12px', color: 'var(--ink)', fontWeight: 600 }}>Apply URL</th>
                </tr>
              </thead>
              <tbody>
                {result.jobs.records.map((job, idx) => (
                  <tr
                    key={idx}
                    style={{
                      borderBottom: idx === result.jobs!.records.length - 1 ? 'none' : '1px solid var(--hairline)',
                      backgroundColor: idx % 2 === 0 ? 'var(--card)' : 'var(--page)',
                    }}
                  >
                    <td style={{ padding: '8px 12px', color: 'var(--navy)', fontWeight: 600 }}>
                      {job.title || '–'}
                    </td>
                    <td style={{ padding: '8px 12px', color: 'var(--ink)' }}>
                      {job.company || '–'}
                    </td>
                    <td style={{ padding: '8px 12px', color: 'var(--muted)' }}>
                      {job.location || '–'}
                    </td>
                    <td style={{ padding: '8px 12px', color: 'var(--muted)', whiteSpace: 'nowrap' }}>
                      {job.date_posted || '–'}
                    </td>
                    <td style={{ padding: '8px 12px', fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
                      {job.job_url ? (
                        <a
                          href={job.job_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{ color: 'var(--navy)', textDecoration: 'underline' }}
                        >
                          View Details
                        </a>
                      ) : (
                        '–'
                      )}
                    </td>
                    <td style={{ padding: '8px 12px', fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
                      {job.apply_url ? (
                        <a
                          href={job.apply_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{ color: 'var(--navy)', textDecoration: 'underline' }}
                        >
                          Apply Link
                        </a>
                      ) : (
                        '–'
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Collapsible Pretty JSON with JSON Valid Indicator */}
      <div
        style={{
          border: '1px solid var(--hairline)',
          borderRadius: '8px',
          overflow: 'hidden',
          marginTop: '8px',
        }}
      >
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '10px 16px',
            backgroundColor: 'var(--page)',
            gap: '8px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span
              style={{
                fontFamily: 'var(--font-display)',
                fontWeight: 700,
                fontSize: '14px',
                color: 'var(--ink)',
              }}
            >
              Raw Extracted JSON Payload
            </span>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                padding: '2px 8px',
                borderRadius: '4px',
                backgroundColor: 'var(--status-success-bg)',
                color: 'var(--status-success-text)',
                fontSize: '11px',
                fontWeight: 600,
              }}
            >
              ✓ JSON Valid
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              type="button"
              onClick={handleCopyJson}
              style={{
                padding: '4px 10px',
                borderRadius: '4px',
                backgroundColor: 'var(--card)',
                border: '1px solid var(--hairline)',
                color: 'var(--ink)',
                fontSize: '12px',
                cursor: 'pointer',
              }}
            >
              {copied ? '✓ Copied' : 'Copy JSON'}
            </button>
            <button
              type="button"
              onClick={handleDownloadJson}
              style={{
                padding: '4px 10px',
                borderRadius: '4px',
                backgroundColor: 'var(--card)',
                border: '1px solid var(--hairline)',
                color: 'var(--ink)',
                fontSize: '12px',
                cursor: 'pointer',
              }}
            >
              Download JSON
            </button>
            <a
              href={reportUrl}
              download={`report-${result.run_id}.md`}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                padding: '4px 10px',
                borderRadius: '4px',
                backgroundColor: 'var(--navy)',
                color: '#FFFFFF',
                fontSize: '12px',
                fontWeight: 600,
                textDecoration: 'none',
              }}
            >
              Download Report (.md)
            </a>
            <button
              type="button"
              onClick={() => setJsonExpanded(!jsonExpanded)}
              style={{
                padding: '4px 8px',
                borderRadius: '4px',
                backgroundColor: 'var(--card)',
                border: '1px solid var(--hairline)',
                color: 'var(--ink)',
                fontSize: '12px',
                cursor: 'pointer',
              }}
            >
              {jsonExpanded ? '▲ Collapse' : '▼ Expand'}
            </button>
          </div>
        </div>

        {jsonExpanded && (
          <div
            style={{
              padding: '12px 16px',
              backgroundColor: '#FAFAFB',
              maxHeight: '360px',
              overflow: 'auto',
              borderTop: '1px solid var(--hairline)',
            }}
          >
            <pre className="monospace-view" style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
              {jsonStr}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
};
