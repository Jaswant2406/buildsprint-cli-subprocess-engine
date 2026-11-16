import React from 'react';
import type { SecurityFinding } from '../types';
import { formatNumber } from '../utils/format';

interface SecurityFindingsPanelProps {
  findings: SecurityFinding[];
}

export const SecurityFindingsPanel: React.FC<SecurityFindingsPanelProps> = ({ findings }) => {
  if (!findings || findings.length === 0) {
    return null;
  }

  return (
    <div className="card-panel panel-sky" style={{ border: '1px solid #60A5FA' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '24px',
              height: '24px',
              borderRadius: '50%',
              backgroundColor: 'var(--navy)',
              color: '#FFFFFF',
              fontWeight: 700,
              fontSize: '13px',
            }}
          >
            !
          </span>
          <span className="card-title" style={{ color: 'var(--ink)' }}>
            Security Scanner Findings ({formatNumber(findings.length)})
          </span>
        </div>
        <span
          style={{
            fontSize: '11px',
            fontWeight: 600,
            textTransform: 'uppercase',
            backgroundColor: '#FFFFFF',
            color: 'var(--navy)',
            padding: '2px 8px',
            borderRadius: '4px',
            border: '1px solid #60A5FA',
          }}
        >
          Untrusted Content Quarantined
        </span>
      </div>

      <p style={{ color: 'var(--ink)', fontSize: '13px', lineHeight: '1.5' }}>
        The injection detection engine scanned the target content and identified potentially malicious
        patterns. The content has been delimited inside untrusted text markers and prevented from executing.
      </p>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '4px' }}>
        {findings.map((finding, idx) => (
          <div
            key={idx}
            style={{
              padding: '10px 14px',
              backgroundColor: '#FFFFFF',
              borderRadius: '6px',
              border: '1px solid #BFDBFE',
              display: 'flex',
              flexDirection: 'column',
              gap: '4px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontWeight: 600, fontSize: '13px', color: 'var(--navy)' }}>
                Pattern: {finding.pattern}
              </span>
              <span
                style={{
                  fontSize: '11px',
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  color: 'var(--status-failed-text)',
                  backgroundColor: 'var(--status-failed-bg)',
                  padding: '2px 6px',
                  borderRadius: '4px',
                }}
              >
                {finding.severity || 'HIGH'}
              </span>
            </div>

            {finding.page_url && (
              <span style={{ fontSize: '12px', color: 'var(--ink)', fontFamily: 'var(--font-mono)' }}>
                Page: {finding.page_url}
              </span>
            )}

            <div
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '12px',
                backgroundColor: 'var(--page)',
                padding: '6px 10px',
                borderRadius: '4px',
                color: 'var(--ink)',
                overflowWrap: 'anywhere',
              }}
            >
              Snippet: &quot;{finding.snippet}&quot;
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
