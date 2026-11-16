import React from 'react';
import type { Plan } from '../types';
import { formatNumber } from '../utils/format';

interface PlanCardProps {
  plan: Plan;
}

export const PlanCard: React.FC<PlanCardProps> = ({ plan }) => {
  return (
    <div className="card-panel panel-sand" style={{ border: '1px solid #D3C4A5' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span className="eyebrow" style={{ color: 'var(--navy)' }}>
          Parsed Execution Plan
        </span>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '12px',
            backgroundColor: '#FFFFFF',
            padding: '2px 8px',
            borderRadius: '4px',
            color: 'var(--ink)',
            border: '1px solid #D3C4A5',
          }}
        >
          Tool: {plan.tool}
        </span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', minWidth: 0 }}>
          <strong style={{ color: 'var(--ink)', fontSize: '14px', whiteSpace: 'nowrap' }}>
            Target URL:
          </strong>
          <a
            href={plan.url}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              color: 'var(--navy)',
              fontFamily: 'var(--font-mono)',
              fontSize: '13px',
              textDecoration: 'underline',
              overflowWrap: 'anywhere',
            }}
          >
            {plan.url}
          </a>
        </div>

        <p style={{ color: 'var(--ink)', fontSize: '13px', lineHeight: '1.5' }}>
          <strong>Reason:</strong> {plan.tool_reason}
        </p>

        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '12px',
            paddingTop: '6px',
            borderTop: '1px dashed #C8B896',
          }}
        >
          <span style={{ fontSize: '12px', color: 'var(--ink)' }}>
            <strong>Max Pages:</strong>{' '}
            <span className="tabular-num">{formatNumber(plan.max_pages)}</span>
          </span>
          <span style={{ fontSize: '12px', color: 'var(--ink)' }}>
            <strong>Max Depth:</strong>{' '}
            <span className="tabular-num">{formatNumber(plan.max_depth)}</span>
          </span>
          {plan.max_links && (
            <span style={{ fontSize: '12px', color: 'var(--ink)' }}>
              <strong>Max Links:</strong>{' '}
              <span className="tabular-num">{formatNumber(plan.max_links)}</span>
            </span>
          )}
          {plan.extract_focus && (
            <span style={{ fontSize: '12px', color: 'var(--ink)' }}>
              <strong>Focus:</strong> {plan.extract_focus}
            </span>
          )}
          <span style={{ fontSize: '12px', color: 'var(--ink)' }}>
            <strong>Summary:</strong> {plan.wants_summary ? 'Yes' : 'No'}
          </span>
          <span style={{ fontSize: '12px', color: 'var(--ink)' }}>
            <strong>JSON:</strong> {plan.wants_json ? 'Yes' : 'No'}
          </span>
        </div>
      </div>
    </div>
  );
};
