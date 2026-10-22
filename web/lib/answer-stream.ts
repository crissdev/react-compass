import type { Answer, SourceExcerpt, StreamEvent } from '@/lib/types';

const INTERRUPTED_MESSAGE =
  'The answer stream was interrupted before completion. Please try again.';
const INVALID_EVENT_MESSAGE =
  'The API returned an invalid streamed response. Please try again.';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isSource(value: unknown): value is SourceExcerpt {
  return (
    isRecord(value) &&
    typeof value.id === 'string' &&
    typeof value.citation === 'number' &&
    Number.isInteger(value.citation) &&
    value.citation > 0 &&
    typeof value.title === 'string' &&
    (value.section === null || typeof value.section === 'string') &&
    typeof value.source_type === 'string' &&
    ['reference', 'learn', 'blog', 'github', 'unknown'].includes(
      value.source_type,
    ) &&
    typeof value.source_url === 'string' &&
    typeof value.excerpt === 'string'
  );
}

function isAnswer(value: unknown): value is Answer {
  return (
    isRecord(value) &&
    typeof value.kind === 'string' &&
    ['react_answer', 'no_match', 'scope_notice'].includes(value.kind) &&
    typeof value.message === 'string' &&
    Array.isArray(value.sources) &&
    value.sources.every(isSource) &&
    (value.suggestions === undefined ||
      (Array.isArray(value.suggestions) &&
        value.suggestions.every(
          (suggestion) => typeof suggestion === 'string',
        )))
  );
}

function normalizeAnswer(value: unknown): Answer | undefined {
  if (!isRecord(value) || !Array.isArray(value.sources)) return;

  // The API omits null fields when serializing streamed events.
  const answer = {
    ...value,
    sources: value.sources.map((source) =>
      isRecord(source) && source.section === undefined
        ? { ...source, section: null }
        : source,
    ),
  };
  return isAnswer(answer) ? answer : undefined;
}

function parseEvent(line: string): StreamEvent {
  let event: unknown;
  try {
    event = JSON.parse(line);
  } catch (cause) {
    throw new Error(INVALID_EVENT_MESSAGE, { cause });
  }

  if (isRecord(event)) {
    if (
      event.type === 'status' &&
      typeof event.stage === 'string' &&
      typeof event.message === 'string'
    ) {
      return { type: 'status', stage: event.stage, message: event.message };
    }
    if (event.type === 'result') {
      const data = normalizeAnswer(event.data);
      if (data) return { type: 'result', data };
    }
    if (event.type === 'error' && typeof event.message === 'string') {
      return { type: 'error', message: event.message };
    }
  }

  throw new Error(INVALID_EVENT_MESSAGE);
}

export async function readAnswerStream(
  response: Response,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const throwIfAborted = () => {
    if (signal?.aborted)
      throw new DOMException('Search cancelled', 'AbortError');
  };
  if (signal?.aborted) {
    void response.body?.cancel().catch(() => undefined);
    throwIfAborted();
  }

  if (!response.body) {
    throw new Error('The API returned an empty response.');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let ended = false;
  let cancelled = false;
  const cancel = () => {
    if (cancelled) return;
    cancelled = true;
    // Cancellation must not wait for an upstream cancel hook to finish.
    void reader.cancel().catch(() => undefined);
  };
  signal?.addEventListener('abort', cancel, { once: true });

  const deliver = (line: string): boolean => {
    throwIfAborted();
    if (!line.trim()) return false;
    const event = parseEvent(line);
    onEvent(event);
    return event.type !== 'status';
  };

  try {
    throwIfAborted();
    while (true) {
      let chunk: ReadableStreamReadResult<Uint8Array>;
      try {
        chunk = await reader.read();
      } catch (cause) {
        throwIfAborted();
        throw new Error(INTERRUPTED_MESSAGE, { cause });
      }
      throwIfAborted();
      const { done, value } = chunk;
      ended = done;
      buffer += decoder.decode(value, { stream: !done });

      let newline: number;
      while ((newline = buffer.indexOf('\n')) !== -1) {
        const line = buffer.slice(0, newline);
        buffer = buffer.slice(newline + 1);
        if (deliver(line)) return;
      }

      if (done) {
        if (buffer.trim()) {
          // A terminal event may be complete even without a trailing newline.
          // Invalid trailing JSON usually indicates a truncated connection.
          let event: StreamEvent;
          try {
            event = parseEvent(buffer);
          } catch (cause) {
            throw new Error(INTERRUPTED_MESSAGE, { cause });
          }
          onEvent(event);
          if (event.type !== 'status') return;
        }
        throwIfAborted();
        throw new Error(INTERRUPTED_MESSAGE);
      }
    }
  } finally {
    signal?.removeEventListener('abort', cancel);
    if (!ended) cancel();
    reader.releaseLock();
  }
}
