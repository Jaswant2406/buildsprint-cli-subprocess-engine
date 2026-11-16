import React from 'react';

export const HeroSection: React.FC = () => {
  return (
    <section
      className="card-panel"
      style={{
        overflow: 'hidden',
        position: 'relative',
        backgroundColor: 'var(--card)',
        border: '1px solid var(--hairline)',
      }}
    >
      {/* Decorative background geometry */}
      <div className="decorative-graphic" aria-hidden="true">
        <svg
          width="100%"
          height="100%"
          viewBox="0 0 800 300"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          style={{ opacity: 0.12 }}
        >
          <circle cx="700" cy="50" r="180" fill="var(--sky)" />
          <circle cx="780" cy="180" r="140" fill="var(--sand)" />
        </svg>
      </div>

      <div className="card-content-wrapper">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className="eyebrow">Enterprise Web Research</span>
          <span
            style={{
              fontSize: '11px',
              fontWeight: 600,
              padding: '2px 8px',
              borderRadius: '12px',
              backgroundColor: 'var(--sky)',
              color: 'var(--navy)',
            }}
          >
            Zero Mock Data
          </span>
        </div>

        <h1 className="hero-headline">
          Autonomous Web Intelligence.
          <span className="accent-navy">CLI-Driven Execution.</span>
        </h1>

        <p className="body-text" style={{ maxWidth: '720px' }}>
          Execute verified, sandboxed CLI subprocesses to crawl target websites, validate HTTP links,
          extract structured evidence with source provenance, and audit network traffic with deterministic
          IP pinning and SSRF defense.
        </p>
      </div>
    </section>
  );
};
