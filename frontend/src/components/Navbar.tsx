import React from 'react';
import type { AuditChain, HealthResponse } from '../types';
import { formatNumber } from '../utils/format';

interface NavbarProps {
  health: HealthResponse | null;
  audit: AuditChain | null;
  backendOnline: boolean;
  onToggleSidebar: () => void;
  onRefreshHistory: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  health,
  audit,
  backendOnline,
  onToggleSidebar,
  onRefreshHistory,
}) => {
  return (
    <header
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: '16px',
        padding: '16px 24px',
        backgroundColor: 'var(--card)',
        borderBottom: '1px solid var(--hairline)',
        boxSizing: 'border-box',
        width: '100%',
        minWidth: 0,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px', minWidth: 0 }}>
        <button
          onClick={onToggleSidebar}
          aria-label="Toggle Run History Sidebar"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '8px 12px',
            backgroundColor: 'transparent',
            border: '1px solid var(--hairline)',
            borderRadius: '6px',
            color: 'var(--ink)',
            cursor: 'pointer',
          }}
        >
          <span style={{ fontSize: '16px', marginRight: '6px' }}>☰</span> Runs
        </button>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span
              style={{
                fontFamily: 'var(--font-display)',
                fontWeight: 800,
                fontSize: '18px',
                color: 'var(--ink)',
                letterSpacing: '-0.02em',
              }}
            >
              BuildSprint
            </span>
            <span
              style={{
                fontFamily: 'var(--font-body)',
                fontWeight: 600,
                fontSize: '11px',
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
                color: 'var(--navy)',
                backgroundColor: 'var(--page)',
                padding: '2px 8px',
                borderRadius: '4px',
                border: '1px solid var(--hairline)',
              }}
            >
              CLI Subprocess Engine
            </span>
          </div>
          <span className="caption" style={{ color: 'var(--muted)' }}>
            Real-time research agent with verified network policy
          </span>
        </div>
      </div>

      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          gap: '12px',
          minWidth: 0,
        }}
      >
        {/* Backend Connectivity Status */}
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            padding: '4px 10px',
            borderRadius: '16px',
            fontSize: '12px',
            fontWeight: 600,
            backgroundColor: backendOnline ? 'var(--status-success-bg)' : 'var(--status-failed-bg)',
            color: backendOnline ? 'var(--status-success-text)' : 'var(--status-failed-text)',
          }}
        >
          <span
            style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              backgroundColor: backendOnline ? 'var(--status-success-text)' : 'var(--status-failed-text)',
            }}
          />
          {backendOnline ? 'Backend Online' : 'Backend Disconnected'}
        </div>

        {/* LLM / Heuristic Mode Badge */}
        {health && (
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '4px 10px',
              borderRadius: '6px',
              backgroundColor: 'var(--page)',
              border: '1px solid var(--hairline)',
              color: 'var(--ink)',
              fontSize: '12px',
              fontWeight: 500,
            }}
          >
            <span>Mode:</span>
            <strong style={{ color: 'var(--navy)', fontWeight: 600 }}>
              {health.llm_mode.toUpperCase()}
            </strong>
            <span style={{ color: 'var(--muted)', fontSize: '11px' }}>
              v{health.version}
            </span>
          </div>
        )}

        {/* Audit Chain Badge */}
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            padding: '4px 10px',
            borderRadius: '6px',
            backgroundColor: audit?.verified ? 'var(--status-success-bg)' : 'var(--page)',
            color: audit?.verified ? 'var(--status-success-text)' : 'var(--ink)',
            border: '1px solid var(--hairline)',
            fontSize: '12px',
            fontWeight: 600,
          }}
          title="Cryptographic SHA-256 hash chaining of all execution logs"
        >
          <span>🔒 Audit Chain:</span>
          <span>
            {audit?.verified ? `Verified (${formatNumber(audit.length)} blocks)` : 'Checking...'}
          </span>
        </div>

        <button
          onClick={onRefreshHistory}
          title="Refresh runs and audit chain"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            padding: '6px 12px',
            backgroundColor: 'var(--page)',
            border: '1px solid var(--hairline)',
            borderRadius: '6px',
            color: 'var(--ink)',
            fontSize: '12px',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          ↻ Refresh
        </button>
      </div>
    </header>
  );
};
