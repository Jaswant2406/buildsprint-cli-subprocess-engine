import React, { useState } from 'react';
import { askRun } from '../utils/api';

interface AskBoxProps {
  runId: string;
}

export const AskBox: React.FC<AskBoxProps> = ({ runId }) => {
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [qaList, setQaList] = useState<
    Array<{ question: string; answer: string; citations: string[] }>
  >([]);

  const handleAsk = async (e: React.FormEvent) => {
    e.preventDefault();
    const q = question.trim();
    if (!q || loading) return;

    setLoading(true);
    setError(null);
    try {
      const res = await askRun(runId, q);
      setQaList((prev) => [
        ...prev,
        {
          question: q,
          answer: res.answer,
          citations: res.citations || [],
        },
      ]);
      setQuestion('');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to query crawl data');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card-panel" style={{ backgroundColor: 'var(--card)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 className="card-title">Follow-up Research Q&A</h3>
        <span className="caption" style={{ color: 'var(--muted)' }}>
          Queries extracted content with zero hallucination
        </span>
      </div>

      {qaList.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {qaList.map((item, idx) => (
            <div
              key={idx}
              style={{
                padding: '12px 16px',
                backgroundColor: 'var(--page)',
                borderRadius: '8px',
                border: '1px solid var(--hairline)',
                display: 'flex',
                flexDirection: 'column',
                gap: '6px',
              }}
            >
              <div style={{ fontWeight: 600, color: 'var(--ink)', fontSize: '13px' }}>
                Q: {item.question}
              </div>
              <p style={{ color: 'var(--ink)', fontSize: '13px', lineHeight: '1.6' }}>
                {item.answer}
              </p>
              {item.citations.length > 0 && (
                <div style={{ marginTop: '4px' }}>
                  <span className="eyebrow" style={{ fontSize: '11px', display: 'block' }}>
                    Citations:
                  </span>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '2px' }}>
                    {item.citations.map((cite, cIdx) => (
                      <a
                        key={cIdx}
                        href={cite}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{
                          fontSize: '11px',
                          fontFamily: 'var(--font-mono)',
                          color: 'var(--navy)',
                          textDecoration: 'underline',
                          backgroundColor: '#FFFFFF',
                          padding: '2px 6px',
                          borderRadius: '4px',
                          border: '1px solid var(--hairline)',
                        }}
                      >
                        {cite}
                      </a>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <form onSubmit={handleAsk} style={{ display: 'flex', gap: '8px' }}>
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question about the crawled data..."
          disabled={loading}
          style={{ flex: 1 }}
        />
        <button
          type="submit"
          disabled={loading || !question.trim()}
          style={{
            padding: '10px 18px',
            backgroundColor: loading || !question.trim() ? 'var(--hairline)' : 'var(--navy)',
            color: loading || !question.trim() ? 'var(--muted)' : '#FFFFFF',
            border: 'none',
            borderRadius: '8px',
            fontWeight: 600,
            cursor: loading || !question.trim() ? 'not-allowed' : 'pointer',
            whiteSpace: 'nowrap',
          }}
        >
          {loading ? 'Querying...' : 'Ask →'}
        </button>
      </form>

      {error && (
        <span className="caption" style={{ color: 'var(--status-failed-text)' }}>
          {error}
        </span>
      )}
    </div>
  );
};
