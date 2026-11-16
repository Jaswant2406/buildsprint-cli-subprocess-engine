import React, { useState } from 'react';

interface ChatInputProps {
  onSubmit: (prompt: string) => void;
  isRunning: boolean;
  onCancel: () => void;
}

const EXAMPLES = [
  {
    label: 'Mandatory Crawl',
    prompt:
      'Crawl https://example.com, extract the important information, give me a summary, and return the extracted data in JSON format.',
  },
  {
    label: 'Broken-Links Check',
    prompt: 'Check for broken links on https://example.com and report their status codes.',
  },
  {
    label: 'Bad Domain',
    prompt: 'Crawl https://this-domain-does-not-exist-123454321.com and extract information.',
  },
  {
    label: 'Injection Page',
    prompt: 'Crawl https://example.com/injection-test, summarize the content, and report any security issues.',
  },
  {
    label: 'Private IP (SSRF)',
    prompt: 'Crawl http://10.0.0.1/admin and return JSON.',
  },
];

export const ChatInput: React.FC<ChatInputProps> = ({ onSubmit, isRunning, onCancel }) => {
  const [prompt, setPrompt] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = prompt.trim();
    if (!trimmed || isRunning) return;
    onSubmit(trimmed);
  };

  const handleChipClick = (examplePrompt: string) => {
    // Spec: Chips fill the input; they do not auto-run.
    setPrompt(examplePrompt);
  };

  return (
    <div className="card-panel" style={{ backgroundColor: 'var(--card)' }}>
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <label
            htmlFor="chat-prompt-input"
            className="eyebrow"
            style={{ display: 'block' }}
          >
            Research Instruction / Prompt
          </label>
          <span className="caption" style={{ color: 'var(--muted)' }}>
            Max 1,000 characters
          </span>
        </div>

        <textarea
          id="chat-prompt-input"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="e.g. Crawl https://example.com, extract the important information, and return JSON..."
          rows={3}
          disabled={isRunning}
          maxLength={1000}
          style={{
            resize: 'vertical',
            minHeight: '80px',
            fontSize: '14px',
            lineHeight: '1.5',
            backgroundColor: isRunning ? 'var(--page)' : 'var(--card)',
          }}
        />

        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: '12px',
          }}
        >
          {/* Example chips */}
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'center',
              gap: '8px',
              minWidth: 0,
            }}
          >
            <span className="caption" style={{ fontWeight: 600, color: 'var(--ink)' }}>
              Examples:
            </span>
            {EXAMPLES.map((ex) => (
              <button
                type="button"
                key={ex.label}
                onClick={() => handleChipClick(ex.prompt)}
                disabled={isRunning}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  padding: '4px 10px',
                  borderRadius: '16px',
                  backgroundColor: 'var(--page)',
                  border: '1px solid var(--hairline)',
                  color: 'var(--ink)',
                  fontSize: '12px',
                  fontWeight: 500,
                  cursor: isRunning ? 'not-allowed' : 'pointer',
                  transition: 'background-color 0.15s ease',
                }}
              >
                {ex.label}
              </button>
            ))}
          </div>

          {/* Action buttons */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {isRunning && (
              <button
                type="button"
                onClick={onCancel}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  padding: '10px 18px',
                  borderRadius: '8px',
                  backgroundColor: 'var(--status-failed-bg)',
                  border: '1px solid var(--status-failed-text)',
                  color: 'var(--status-failed-text)',
                  fontSize: '14px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                ■ Cancel Run
              </button>
            )}

            <button
              type="submit"
              disabled={isRunning || !prompt.trim()}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '8px',
                padding: '10px 22px',
                borderRadius: '8px',
                backgroundColor: isRunning || !prompt.trim() ? 'var(--hairline)' : 'var(--navy)',
                border: 'none',
                color: isRunning || !prompt.trim() ? 'var(--muted)' : '#FFFFFF',
                fontSize: '14px',
                fontWeight: 600,
                cursor: isRunning || !prompt.trim() ? 'not-allowed' : 'pointer',
                transition: 'background-color 0.15s ease',
              }}
            >
              {isRunning ? (
                <>
                  <span
                    style={{
                      display: 'inline-block',
                      width: '12px',
                      height: '12px',
                      borderRadius: '50%',
                      border: '2px solid #FFFFFF',
                      borderTopColor: 'transparent',
                      animation: 'spin 0.8s linear infinite',
                    }}
                  />
                  Executing...
                </>
              ) : (
                'Run Subprocess →'
              )}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
};
