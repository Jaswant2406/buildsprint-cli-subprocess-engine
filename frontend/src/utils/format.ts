/**
 * Formatting utilities using en-IN locale as required by the specification.
 */

export function formatNumber(val: number | string | null | undefined): string {
  if (val === null || val === undefined || val === '') return '–';
  const num = typeof val === 'string' ? Number(val) : val;
  if (isNaN(num)) return String(val);
  return num.toLocaleString('en-IN');
}

export function formatDuration(seconds: number | string | null | undefined): string {
  if (seconds === null || seconds === undefined || seconds === '') return '–';
  const num = typeof seconds === 'string' ? Number(seconds) : seconds;
  if (isNaN(num)) return String(seconds);
  return `${num.toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 2 })}s`;
}

export function formatPercent(score: number | string | null | undefined): string {
  if (score === null || score === undefined || score === '') return '–';
  const num = typeof score === 'string' ? Number(score) : score;
  if (isNaN(num)) return String(score);
  return `${num.toLocaleString('en-IN', { maximumFractionDigits: 1 })}%`;
}

export function formatTimestamp(isoOrTime: string | number | null | undefined): string {
  if (!isoOrTime) return '';
  try {
    const d = typeof isoOrTime === 'number' ? new Date(isoOrTime) : new Date(String(isoOrTime));
    if (isNaN(d.getTime())) return String(isoOrTime);
    return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return String(isoOrTime);
  }
}
