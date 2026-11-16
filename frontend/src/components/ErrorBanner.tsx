import React, { useEffect, useState } from 'react';

interface ErrorBannerProps {
  error: string | null;
  retryAfterSeconds?: number;
  onDismiss: () => void;
}

export const ErrorBanner: React.FC<ErrorBannerProps> = ({
  error,
  retryAfterSeconds,
  onDismiss,
}) => {
  const [countdown, setCountdown] = useState<number | null>(null);

  useEffect(() => {
    if (retryAfterSeconds && retryAfterSeconds > 0) {
      setCountdown(retryAfterSeconds);
      const timer = setInterval(() => {
        setCountdown((prev) => {
          if (prev === null || prev <= 1) {
            clearInterval(timer);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
      return () => clearInterval(timer);
    } else {
      setCountdown(null);
    }
  }, [retryAfterSeconds]);

  if (!error) return null;

  return (
    <div
      role="alert"
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        gap: '12px',
        padding: '12px 18px',
        borderRadius: '8px',
        backgroundColor: 'var(--status-failed-bg)',
        border: '1px solid var(--status-failed-text)',
        color: 'var(--status-failed-text)',
        fontSize: '13px',
        lineHeight: '1.5',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
        <span style={{ fontWeight: 700, fontSize: '15px' }}>⚠</span>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <strong style={{ color: 'var(--status-failed-text)' }}>
            {(() => {
              const lower = error.toLowerCase();
              if (
                lower.includes('dns') ||
                lower.includes('getaddrinfo') ||
                lower.includes('name or service not known') ||
                lower.includes('could not resolve') ||
                lower.includes('unreachable')
              ) {
                return 'DNS / Network Resolution Error:';
              }
              if (
                lower.includes('ssrf') ||
                lower.includes('forbidden address') ||
                lower.includes('private address') ||
                lower.includes('loopback')
              ) {
                return 'Security Policy Error (SSRF Protection):';
              }
              if (lower.includes('rate limit') || lower.includes('concurrency') || lower.includes('busy')) {
                return 'Concurrency / Rate Limit Notice:';
              }
              return 'Execution Guardrail / Policy Error:';
            })()}
          </strong>
          <span style={{ color: 'var(--status-failed-text)', overflowWrap: 'anywhere' }}>
            {error}
          </span>
          {countdown !== null && (
            <span style={{ fontWeight: 600, marginTop: '2px' }}>
              {countdown > 0
                ? `Rate limit active: retry available in ${countdown}s`
                : 'Rate limit cooled down. You may retry now.'}
            </span>
          )}
        </div>
      </div>

      <button
        onClick={onDismiss}
        style={{
          background: 'none',
          border: 'none',
          color: 'var(--status-failed-text)',
          cursor: 'pointer',
          fontWeight: 700,
          fontSize: '16px',
          padding: '4px',
        }}
        aria-label="Dismiss error"
      >
        ✕
      </button>
    </div>
  );
};
