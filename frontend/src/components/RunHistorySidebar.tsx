import React from 'react';
import type { RunListItem } from '../types';
import { formatTimestamp } from '../utils/format';

interface RunHistorySidebarProps {
  runs: RunListItem[];
  activeRunId: string | null;
  onSelectRun: (runId: string) => void;
  isOpen: boolean;
  onClose: () => void;
}

export const RunHistorySidebar: React.FC<RunHistorySidebarProps> = ({
  runs,
  activeRunId,
  onSelectRun,
  isOpen,
  onClose,
}) => {
  if (!isOpen) return null;

  return (
    <aside
      className="run-history-sidebar"
      style={{
        width: '300px',
        maxWidth: '85vw',
        backgroundColor: 'var(--card)',
        borderRight: '1px solid var(--hairline)',
        display: 'flex',
        flexDirection: 'column',
        boxSizing: 'border-box',
        overflow: 'hidden',
        height: '100%',
        flexShrink: 0,
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '16px',
          borderBottom: '1px solid var(--hairline)',
          backgroundColor: 'var(--page)',
        }}
      >
        <span className="eyebrow" style={{ color: 'var(--ink)' }}>
          Run History ({runs.length})
        </span>
        <button
          onClick={onClose}
          aria-label="Close Sidebar"
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            fontSize: '16px',
            color: 'var(--ink)',
            padding: '4px',
          }}
        >
          ✕
        </button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '12px' }}>
        {runs.length === 0 ? (
          <p className="caption" style={{ textAlign: 'center', marginTop: '20px' }}>
            No past runs recorded yet.
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {runs.map((r) => {
              const isSelected = r.run_id === activeRunId;
              const statusClass = r.status || (r.state === 'completed' ? 'SUCCESS' : r.state === 'running' ? 'PARTIAL' : 'FAILED');

              return (
                <div
                  key={r.run_id}
                  onClick={() => onSelectRun(r.run_id)}
                  style={{
                    padding: '10px 12px',
                    borderRadius: '8px',
                    border: isSelected ? '2px solid var(--navy)' : '1px solid var(--hairline)',
                    backgroundColor: isSelected ? 'var(--page)' : 'var(--card)',
                    cursor: 'pointer',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '4px',
                    transition: 'border-color 0.15s ease',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: '11px',
                        color: 'var(--navy)',
                        fontWeight: 600,
                      }}
                    >
                      {r.run_id.slice(0, 8)}...
                    </span>
                    <span className={`badge-status ${statusClass}`} style={{ fontSize: '10px', padding: '2px 6px' }}>
                      {statusClass}
                    </span>
                  </div>

                  <p
                    style={{
                      fontSize: '12px',
                      color: 'var(--ink)',
                      lineHeight: '1.4',
                      margin: 0,
                      display: '-webkit-box',
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: 'vertical',
                      overflow: 'hidden',
                    }}
                  >
                    {r.prompt || '(empty prompt)'}
                  </p>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '2px' }}>
                    <span className="caption" style={{ fontSize: '11px', color: 'var(--muted)' }}>
                      {formatTimestamp(r.created_at)}
                    </span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      {r.pages_crawled !== undefined && r.pages_crawled > 0 && (
                        <span className="tabular-num" style={{ fontSize: '11px', color: 'var(--navy)', fontWeight: 600 }}>
                          {r.pages_crawled} {r.pages_crawled === 1 ? 'page' : 'pages'} •
                        </span>
                      )}
                      {r.duration_s !== undefined && (
                        <span className="tabular-num" style={{ fontSize: '11px', color: 'var(--muted)' }}>
                          {r.duration_s.toFixed(1)}s
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </aside>
  );
};
