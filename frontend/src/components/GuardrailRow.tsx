import React from 'react';
import type { HealthResponse, ToolConfig } from '../types';

interface GuardrailRowProps {
  tools: ToolConfig[];
  health: HealthResponse | null;
}

export const GuardrailRow: React.FC<GuardrailRowProps> = ({ tools, health }) => {
  const allowedToolNames = tools.length > 0 ? tools.map((t) => t.name).join(', ') : 'site_crawler, link_checker';
  const timeoutLimit = tools[0]?.timeout_s || 60;

  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        gap: '8px',
        width: '100%',
        minWidth: 0,
      }}
      aria-label="Security and Execution Guardrails"
    >
      <span className="eyebrow" style={{ marginRight: '4px' }}>
        Active Guardrails:
      </span>

      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '6px',
          padding: '4px 10px',
          borderRadius: '16px',
          backgroundColor: 'var(--card)',
          border: '1px solid var(--hairline)',
          fontSize: '12px',
          color: 'var(--ink)',
          fontWeight: 500,
        }}
      >
        <span style={{ color: 'var(--navy)', fontWeight: 600 }}>Allowlist:</span> {allowedToolNames}
      </span>

      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '6px',
          padding: '4px 10px',
          borderRadius: '16px',
          backgroundColor: 'var(--card)',
          border: '1px solid var(--hairline)',
          fontSize: '12px',
          color: 'var(--ink)',
          fontWeight: 500,
        }}
      >
        <span style={{ color: 'var(--navy)', fontWeight: 600 }}>Exec:</span> shell=False (Direct Argv)
      </span>

      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '6px',
          padding: '4px 10px',
          borderRadius: '16px',
          backgroundColor: 'var(--card)',
          border: '1px solid var(--hairline)',
          fontSize: '12px',
          color: 'var(--ink)',
          fontWeight: 500,
        }}
      >
        <span style={{ color: 'var(--navy)', fontWeight: 600 }}>Limits:</span> Max 25 pgs / Depth 3 / {timeoutLimit}s
      </span>

      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '6px',
          padding: '4px 10px',
          borderRadius: '16px',
          backgroundColor: 'var(--card)',
          border: '1px solid var(--hairline)',
          fontSize: '12px',
          color: 'var(--ink)',
          fontWeight: 500,
        }}
      >
        <span style={{ color: 'var(--navy)', fontWeight: 600 }}>NetPolicy:</span> IP Pinning + SSRF Defense
      </span>

      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '6px',
          padding: '4px 10px',
          borderRadius: '16px',
          backgroundColor: 'var(--card)',
          border: '1px solid var(--hairline)',
          fontSize: '12px',
          color: 'var(--ink)',
          fontWeight: 500,
        }}
      >
        <span style={{ color: 'var(--navy)', fontWeight: 600 }}>Parser:</span> {health?.llm_mode === 'llm' ? 'LLM Assisted' : 'Heuristic Regex'}
      </span>
    </div>
  );
};
