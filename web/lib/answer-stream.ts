import type { StreamEvent } from '@/lib/types';

export function decodeEventLines(input: string): {
  events: StreamEvent[];
  remainder: string;
} {
  const lines = input.split('\n');
  const remainder = lines.pop() ?? '';
  const events = lines
    .filter((line) => line.trim().length > 0)
    .map((line) => JSON.parse(line) as StreamEvent);
  return { events, remainder };
}

export async function readAnswerStream(
  response: Response,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  if (!response.body) {
    throw new Error('The API returned an empty response.');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  const abort = () => void reader.cancel();
  signal?.addEventListener('abort', abort, { once: true });

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (signal?.aborted)
        throw new DOMException('Search cancelled', 'AbortError');
      buffer += decoder.decode(value, { stream: !done });
      const decoded = decodeEventLines(buffer);
      buffer = decoded.remainder;
      decoded.events.forEach(onEvent);

      if (done) {
        if (buffer.trim()) onEvent(JSON.parse(buffer) as StreamEvent);
        return;
      }
    }
  } finally {
    signal?.removeEventListener('abort', abort);
  }
}
