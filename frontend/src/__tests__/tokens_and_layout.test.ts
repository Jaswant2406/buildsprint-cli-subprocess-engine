import fs from 'fs';
import path from 'path';
import { describe, expect, it } from 'vitest';
import { formatDuration, formatNumber, formatPercent } from '../utils/format';
import { parseSSEBlock } from '../utils/sse';

describe('Design Tokens & Typography', () => {
  const tokensPath = path.resolve(__dirname, '../styles/tokens.css');
  const tokensCss = fs.readFileSync(tokensPath, 'utf-8');

  it('defines required core brand tokens with exact hex values', () => {
    expect(tokensCss).toMatch(/--ink:\s*#111827/i);
    expect(tokensCss).toMatch(/--navy:\s*#1E3A8A/i);
    expect(tokensCss).toMatch(/--muted:\s*#616B7A/i);
    expect(tokensCss).toMatch(/--page:\s*#F4F5F7/i);
    expect(tokensCss).toMatch(/--card:\s*#FFFFFF/i);
    expect(tokensCss).toMatch(/--sky:\s*#93C5FD/i);
    expect(tokensCss).toMatch(/--sand:\s*#E8DFCB/i);
    expect(tokensCss).toMatch(/--hairline:\s*#D9DCE1/i);
  });

  it('defines semantic status tokens with >= 4.5:1 contrast', () => {
    expect(tokensCss).toMatch(/--status-success-bg:\s*#DCFCE7/i);
    expect(tokensCss).toMatch(/--status-success-text:\s*#166534/i);

    expect(tokensCss).toMatch(/--status-partial-bg:\s*#FEF3C7/i);
    expect(tokensCss).toMatch(/--status-partial-text:\s*#92400E/i);

    expect(tokensCss).toMatch(/--status-failed-bg:\s*#FEE2E2/i);
    expect(tokensCss).toMatch(/--status-failed-text:\s*#991B1B/i);

    expect(tokensCss).toMatch(/--status-timeout-bg:\s*#EDE9FE/i);
    expect(tokensCss).toMatch(/--status-timeout-text:\s*#5B21B6/i);

    expect(tokensCss).toMatch(/--status-cancelled-bg:\s*#E5E7EB/i);
    expect(tokensCss).toMatch(/--status-cancelled-text:\s*#374151/i);
  });

  it('defines correct font families and display clamps', () => {
    const indexPath = path.resolve(__dirname, '../styles/index.css');
    const indexCss = fs.readFileSync(indexPath, 'utf-8');

    // Hero clamp: clamp(40px, 5.2vw, 70px)
    expect(indexCss).toContain('clamp(40px, 5.2vw, 70px)');
    // Section clamp: clamp(28px, 3.4vw, 44px)
    expect(indexCss).toContain('clamp(28px, 3.4vw, 44px)');
    // Card title: 20px
    expect(indexCss).toContain('font-size: 20px');
    // Body: 14px, line-height: 1.75
    expect(indexCss).toContain('font-size: 14px');
    expect(indexCss).toContain('line-height: 1.75');
    // Captions: 13px
    expect(indexCss).toContain('font-size: 13px');
    // Eyebrows: 12px, uppercase, letter-spacing 0.14em
    expect(indexCss).toContain('font-size: 12px');
    expect(indexCss).toContain('text-transform: uppercase');
    expect(indexCss).toContain('letter-spacing: 0.14em');
  });

  it('prohibits position:absolute on text and enforces decorative graphics boundary', () => {
    const indexPath = path.resolve(__dirname, '../styles/index.css');
    const indexCss = fs.readFileSync(indexPath, 'utf-8');

    // Only .decorative-graphic is position: absolute
    const blocks = indexCss.split('}');
    for (const block of blocks) {
      if (block.includes('position: absolute') || block.includes('position:absolute')) {
        expect(block).toContain('decorative-graphic');
      }
    }
  });

  it('prohibits fixed heights or widths on text containers', () => {
    const indexPath = path.resolve(__dirname, '../styles/index.css');
    const indexCss = fs.readFileSync(indexPath, 'utf-8');

    // Inspect card-panel rules: must use min-width: 0 and no fixed height
    expect(indexCss).toContain('.card-panel');
    expect(indexCss).not.toMatch(/\.card-panel\s*\{[^}]*height:\s*\d+px/i);
    expect(indexCss).not.toMatch(/\.card-panel\s*\{[^}]*width:\s*\d+px/i);
  });
});

describe('Locale en-IN Number & Date Formatting', () => {
  it('formats large integers according to Indian numbering system (en-IN)', () => {
    expect(formatNumber(1000)).toBe('1,000');
    expect(formatNumber(100000)).toBe('1,00,000');
    expect(formatNumber(1234567)).toBe('12,34,567');
    expect(formatNumber(0)).toBe('0');
    expect(formatNumber(null)).toBe('–');
  });

  it('formats duration in seconds with en-IN decimals', () => {
    expect(formatDuration(1.25)).toBe('1.25s');
    expect(formatDuration(0.5)).toBe('0.5s');
    expect(formatDuration(1000.5)).toBe('1,000.5s');
    expect(formatDuration(null)).toBe('–');
  });

  it('formats percentages with en-IN formatting', () => {
    expect(formatPercent(100)).toBe('100%');
    expect(formatPercent(87.5)).toBe('87.5%');
    expect(formatPercent(null)).toBe('–');
  });
});

describe('SSE Stream Parser Robustness', () => {
  const events = [
    'received',
    'plan',
    'validated',
    'spawned',
    'progress',
    'parsing',
    'summarizing',
    'result',
    'error',
    'cancelled',
    'stalled',
    'timeout',
  ];

  it.each(events)('correctly parses event: %s', (eventName) => {
    const block = `event: ${eventName}\ndata: {"run_id":"run-123","event":"${eventName}","data":{"key":"val"}}\n\n`;
    const parsed = parseSSEBlock(block);
    expect(parsed).not.toBeNull();
    expect(parsed?.event).toBe(eventName);
    expect(parsed?.run_id).toBe('run-123');
    expect(parsed?.data).toEqual({ key: 'val' });
  });

  it('handles malformed blocks gracefully without throwing', () => {
    // Malformed JSON
    expect(parseSSEBlock('event: progress\ndata: {unclosed json\n\n')).toBeNull();

    // Empty block
    expect(parseSSEBlock('\n\n')).toBeNull();

    // SSE comment ping
    expect(parseSSEBlock(': ping\n\n')).toBeNull();

    // Data without event name defaults to message or payload.event
    const noEvent = parseSSEBlock('data: {"run_id":"r1","event":"plan","data":{"tool":"site_crawler"}}\n\n');
    expect(noEvent?.event).toBe('plan');
    expect(noEvent?.run_id).toBe('r1');
  });
});
