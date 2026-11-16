import type { RunEventPayload } from '../types';

/**
 * Pure SSE chunk parser that splits on double newlines and extracts events and JSON payloads.
 * Tolerates malformed lines, partial chunks, and empty lines.
 */
export function parseSSEBlock(block: string): RunEventPayload | null {
  const lines = block.split(/\r?\n/);
  let eventName = '';
  let dataStr = '';

  for (const line of lines) {
    if (!line || line.startsWith(':')) {
      // Ignore comments and empty lines
      continue;
    }
    if (line.startsWith('event:')) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith('data:')) {
      dataStr = line.slice(5).trim();
    }
  }

  if (!dataStr) {
    return null;
  }

  try {
    const parsed = JSON.parse(dataStr);
    const event = eventName || parsed.event || 'message';
    const run_id = parsed.run_id || '';
    const data = parsed.data !== undefined ? parsed.data : parsed;
    return {
      run_id,
      event,
      data: typeof data === 'object' && data !== null ? data : { raw: data },
      timestamp: new Date().toISOString(),
    };
  } catch {
    // Malformed JSON: return null or ignore safely
    return null;
  }
}

/**
 * Stream reader that converts a ReadableStream of Uint8Array into RunEventPayloads.
 */
export async function consumeSSEStream(
  stream: ReadableStream<Uint8Array>,
  onEvent: (event: RunEventPayload) => void,
  signal?: AbortSignal
): Promise<void> {
  const reader = stream.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  try {
    while (true) {
      if (signal?.aborted) {
        break;
      }
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split(/\r?\n\r?\n/);

      // The last element is the remaining partial chunk
      buffer = blocks.pop() || '';

      for (const block of blocks) {
        if (!block.trim()) continue;
        const parsed = parseSSEBlock(block);
        if (parsed) {
          onEvent(parsed);
        }
      }
    }

    // Flush any leftover in buffer
    if (buffer.trim()) {
      const parsed = parseSSEBlock(buffer);
      if (parsed) {
        onEvent(parsed);
      }
    }
  } finally {
    reader.releaseLock();
  }
}
