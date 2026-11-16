import React, { useEffect, useState } from 'react';
import { fetchLogs } from '../utils/api';

interface LogsDrawerProps {
  runId: string;
  onClose: () => void;
}

export const LogsDrawer: React.FC<LogsDrawerProps> = ({ runId, onClose }) => {
  const [logs, setLogs] = useState<{ stdout: string; stderr: string; events: unknown[] } | null>(
    null
  );
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'stdout' | 'stderr' | 'events'>('stdout');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    fetchLogs(runId)
      .then((data) => {
        if (mounted) {
          setLogs(data);
          setError(null);
        }
      })
      .catch((err) => {
        if (mounted) {
          setError(err instanceof Error ? err.message : 'Failed to fetch logs');
        }
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, [runId]);

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        right: 0,
        bottom: 0,
        width: 'min(640px, 100vw)',
        backgroundColor: 'var(--card)',
        boxShadow: '-4px 0 24px rgba(0,0,0,0.15)',
        zIndex: 1000,
        display: 'flex',
        flexDirection: 'column',
        boxSizing: 'border-box',
        borderLeft: '1px solid var(--hairline)',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '16px 20px',
          borderBottom: '1px solid var(--hairline)',
          backgroundColor: 'var(--page)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <h3 className="card-title" style={{ fontSize: '18px' }}>
            Subprocess Audit Logs
          </h3>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '11px',
              color: 'var(--navy)',
              backgroundColor: '#FFFFFF',
              padding: '2px 6px',
              borderRadius: '4px',
              border: '1px solid var(--hairline)',
            }}
          >
            {runId.slice(0, 8)}...
          </span>
        </div>

        <button
          onClick={onClose}
          aria-label="Close Logs Drawer"
          style={{
            padding: '4px 10px',
            backgroundColor: 'transparent',
            border: '1px solid var(--hairline)',
            borderRadius: '6px',
            cursor: 'pointer',
            fontSize: '14px',
            fontWeight: 600,
            color: 'var(--ink)',
          }}
        >
          ✕ Close
        </button>
      </div>

      {/* Tabs */}
      <div
        style={{
          display: 'flex',
          gap: '8px',
          padding: '10px 20px',
          borderBottom: '1px solid var(--hairline)',
        }}
      >
        {(['stdout', 'stderr', 'events'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: '6px 14px',
              borderRadius: '6px',
              border: activeTab === tab ? '1px solid var(--navy)' : '1px solid var(--hairline)',
              backgroundColor: activeTab === tab ? 'var(--navy)' : 'var(--page)',
              color: activeTab === tab ? '#FFFFFF' : 'var(--ink)',
              fontSize: '13px',
              fontWeight: 600,
              cursor: 'pointer',
              textTransform: 'uppercase',
            }}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Content */}
      <div
        style={{
          flex: 1,
          padding: '16px 20px',
          overflow: 'auto',
          backgroundColor: '#0F172A',
          color: '#E2E8F0',
        }}
      >
        {loading && <p style={{ color: '#94A3B8' }}>Loading subprocess execution stream...</p>}
        {error && <p style={{ color: '#F87171' }}>Error: {error}</p>}
        {!loading && !error && logs && (
          <pre
            className="monospace-view"
            style={{
              color: activeTab === 'stderr' ? '#FCA5A5' : '#F1F5F9',
              whiteSpace: 'pre-wrap',
              margin: 0,
              fontSize: '12px',
              lineHeight: '1.6',
            }}
          >
            {activeTab === 'stdout' && (logs.stdout || '(no stdout recorded)')}
            {activeTab === 'stderr' && (logs.stderr || '(no stderr recorded)')}
            {activeTab === 'events' && JSON.stringify(logs.events, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
};
