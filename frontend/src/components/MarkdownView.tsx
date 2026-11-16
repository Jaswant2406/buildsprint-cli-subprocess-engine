import React from 'react';

interface MarkdownViewProps {
  content: string;
}

/**
 * Validates that a link URL uses safe protocols (http, https, relative).
 * Rejects javascript:, data:, and other dangerous schemes.
 */
function isSafeUrl(url: string): boolean {
  if (!url) return false;
  const trimmed = url.trim().toLowerCase();
  return trimmed.startsWith('https://') || trimmed.startsWith('http://') || trimmed.startsWith('/');
}

/**
 * Renders inline text formatting: bold, inline code, markdown links, and bare URLs.
 * Pure React JSX without dangerouslySetInnerHTML.
 */
export const InlineMarkdown: React.FC<{ text: string }> = ({ text }) => {
  if (!text) return null;

  // Un-escape escaped markdown characters if present (e.g. \**, \[, \], \_)
  const clean = text.replace(/\\([*_[\]()])/g, '$1');

  // Regex to match:
  // 1. Bold with markdown link: **[Title](url)**
  // 2. Bold text: **text**
  // 3. Markdown link: [Title](url)
  // 4. Inline code: `code`
  // 5. Bare URL: https://... or http://...
  const TOKEN_RE = /(\*\*\[(?:[^\]]+)\]\((?:[^)]+)\)\*\*|\*\*[^*]+\*\*|\[(?:[^\]]+)\]\((?:[^)]+)\)|`[^`]+`|https?:\/\/[^\s)\]]+)/g;

  const parts = clean.split(TOKEN_RE);

  return (
    <>
      {parts.map((part, idx) => {
        if (!part) return null;

        // 1. Bold with Link: **[Title](url)**
        const boldLinkMatch = part.match(/^\*\*\[([^\]]+)\]\(([^)]+)\)\*\*$/);
        if (boldLinkMatch) {
          const [, linkText, linkUrl] = boldLinkMatch;
          const safe = isSafeUrl(linkUrl);
          return (
            <strong key={idx} style={{ fontWeight: 700, color: 'var(--ink)' }}>
              {safe ? (
                <a
                  href={linkUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ color: 'var(--navy)', textDecoration: 'underline' }}
                >
                  {linkText}
                </a>
              ) : (
                linkText
              )}
            </strong>
          );
        }

        // 2. Bold text: **text**
        const boldMatch = part.match(/^\*\*([^*]+)\*\*$/);
        if (boldMatch) {
          return (
            <strong key={idx} style={{ fontWeight: 700, color: 'var(--ink)' }}>
              {boldMatch[1]}
            </strong>
          );
        }

        // 3. Markdown link: [Title](url)
        const linkMatch = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
        if (linkMatch) {
          const [, linkText, linkUrl] = linkMatch;
          const safe = isSafeUrl(linkUrl);
          if (safe) {
            return (
              <a
                key={idx}
                href={linkUrl}
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: 'var(--navy)', textDecoration: 'underline' }}
              >
                {linkText}
              </a>
            );
          }
          return <span key={idx}>{linkText}</span>;
        }

        // 4. Inline code: `code`
        const codeMatch = part.match(/^`([^`]+)`$/);
        if (codeMatch) {
          return (
            <code
              key={idx}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '12px',
                backgroundColor: 'var(--card)',
                padding: '2px 5px',
                borderRadius: '4px',
                border: '1px solid var(--hairline)',
                color: 'var(--ink)',
              }}
            >
              {codeMatch[1]}
            </code>
          );
        }

        // 5. Bare URL: https://...
        if (/^https?:\/\/[^\s)\]]+$/.test(part)) {
          // Check for trailing punctuation attached to bare URL (e.g. '.', ',')
          let href = part;
          let suffix = '';
          if (/[.,;]$/.test(href)) {
            suffix = href.slice(-1);
            href = href.slice(0, -1);
          }
          if (isSafeUrl(href)) {
            return (
              <React.Fragment key={idx}>
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ color: 'var(--navy)', textDecoration: 'underline' }}
                >
                  {href}
                </a>
                {suffix}
              </React.Fragment>
            );
          }
          return <span key={idx}>{part}</span>;
        }

        // Plain text node (automatically HTML-escaped by React)
        return <span key={idx}>{part}</span>;
      })}
    </>
  );
};

/**
 * Structured Markdown view for Research Summaries.
 * Converts markdown headings (###), bullet lists (- or *), bold, links,
 * and paragraphs into accessible, cleanly styled React components without external libraries.
 */
export const MarkdownView: React.FC<MarkdownViewProps> = ({ content }) => {
  if (!content) return null;

  // Split lines and normalize
  const rawLines = content.split('\n');

  type Block =
    | { type: 'h2'; text: string }
    | { type: 'h3'; text: string }
    | { type: 'h4'; text: string }
    | { type: 'list'; items: string[] }
    | { type: 'paragraph'; text: string };

  const blocks: Block[] = [];
  let currentList: string[] | null = null;
  let currentPara: string[] = [];

  const flushParagraph = () => {
    if (currentPara.length > 0) {
      blocks.push({ type: 'paragraph', text: currentPara.join(' ') });
      currentPara = [];
    }
  };

  const flushList = () => {
    if (currentList && currentList.length > 0) {
      blocks.push({ type: 'list', items: currentList });
      currentList = null;
    }
  };

  for (let i = 0; i < rawLines.length; i++) {
    let line = rawLines[i].trim();

    // Un-escape leading backslash before markdown characters (e.g. \### -> ###, \- -> -)
    line = line.replace(/^\\(#{1,6}\s)/, '$1').replace(/^\\([*-]\s)/, '$1');

    if (!line) {
      flushParagraph();
      flushList();
      continue;
    }

    // Headings
    if (line.startsWith('#### ')) {
      flushParagraph();
      flushList();
      blocks.push({ type: 'h4', text: line.slice(5).trim() });
      continue;
    }
    if (line.startsWith('### ')) {
      flushParagraph();
      flushList();
      blocks.push({ type: 'h3', text: line.slice(4).trim() });
      continue;
    }
    if (line.startsWith('## ')) {
      flushParagraph();
      flushList();
      blocks.push({ type: 'h2', text: line.slice(3).trim() });
      continue;
    }
    if (line.startsWith('# ')) {
      flushParagraph();
      flushList();
      blocks.push({ type: 'h2', text: line.slice(2).trim() });
      continue;
    }

    // Bullet lists (- item or * item)
    if (/^[-*]\s+/.test(line)) {
      flushParagraph();
      const itemText = line.replace(/^[-*]\s+/, '').trim();
      if (!currentList) {
        currentList = [];
      }
      currentList.push(itemText);
      continue;
    }

    // Normal text line
    flushList();
    currentPara.push(line);
  }

  flushParagraph();
  flushList();

  return (
    <div className="markdown-content" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {blocks.map((block, idx) => {
        switch (block.type) {
          case 'h2':
            return (
              <h3
                key={idx}
                style={{
                  fontFamily: 'var(--font-display)',
                  fontWeight: 700,
                  fontSize: '16px',
                  color: 'var(--ink)',
                  marginTop: idx === 0 ? '0' : '16px',
                  marginBottom: '6px',
                  borderBottom: '1px solid var(--hairline)',
                  paddingBottom: '4px',
                }}
              >
                <InlineMarkdown text={block.text} />
              </h3>
            );

          case 'h3':
            return (
              <h4
                key={idx}
                style={{
                  fontFamily: 'var(--font-display)',
                  fontWeight: 700,
                  fontSize: '14px',
                  color: 'var(--ink)',
                  marginTop: idx === 0 ? '0' : '14px',
                  marginBottom: '4px',
                }}
              >
                <InlineMarkdown text={block.text} />
              </h4>
            );

          case 'h4':
            return (
              <h5
                key={idx}
                style={{
                  fontFamily: 'var(--font-display)',
                  fontWeight: 600,
                  fontSize: '13px',
                  color: 'var(--ink)',
                  marginTop: idx === 0 ? '0' : '10px',
                  marginBottom: '4px',
                }}
              >
                <InlineMarkdown text={block.text} />
              </h5>
            );

          case 'list':
            return (
              <ul
                key={idx}
                style={{
                  paddingLeft: '20px',
                  margin: '4px 0 8px 0',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '6px',
                }}
              >
                {block.items.map((item, itemIdx) => (
                  <li
                    key={itemIdx}
                    style={{
                      color: 'var(--ink)',
                      fontSize: '13px',
                      lineHeight: '1.6',
                    }}
                  >
                    <InlineMarkdown text={item} />
                  </li>
                ))}
              </ul>
            );

          case 'paragraph':
            return (
              <p
                key={idx}
                className="body-text"
                style={{
                  color: 'var(--ink)',
                  margin: '0 0 6px 0',
                  lineHeight: '1.6',
                  fontSize: '13px',
                }}
              >
                <InlineMarkdown text={block.text} />
              </p>
            );

          default:
            return null;
        }
      })}
    </div>
  );
};
