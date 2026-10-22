import { expect, it, vi } from 'vitest';
import type { Answer, StreamEvent } from './types';
import { readAnswerStream } from './answer-stream';

const encoder = new TextEncoder();
const status: StreamEvent = {
  type: 'status',
  stage: 'retrieving',
  message: 'Searching',
};
const answer: Answer = {
  kind: 'react_answer',
  message: 'React cafés ☕',
  sources: [
    {
      id: 'use-state',
      citation: 1,
      title: 'useState',
      section: null,
      source_type: 'reference',
      source_url: 'https://react.dev/reference/react/useState',
      excerpt: 'A source excerpt',
    },
  ],
  suggestions: ['How does state work?'],
};
const result: StreamEvent = { type: 'result', data: answer };

function line(event: StreamEvent): string {
  return `${JSON.stringify(event)}\n`;
}

function responseFromChunks(chunks: (string | Uint8Array)[]): Response {
  return new Response(
    new ReadableStream({
      start(stream) {
        for (const chunk of chunks) {
          stream.enqueue(
            typeof chunk === 'string' ? encoder.encode(chunk) : chunk,
          );
        }
        stream.close();
      },
    }),
  );
}

it('forwards a status before the answer is ready', async () => {
  let upstream!: ReadableStreamDefaultController<Uint8Array>;
  const response = new Response(
    new ReadableStream({
      start(stream) {
        upstream = stream;
        stream.enqueue(encoder.encode(line(status)));
      },
    }),
  );
  const events: StreamEvent[] = [];
  let observedStatus!: () => void;
  const statusReceived = new Promise<void>((resolve) => {
    observedStatus = resolve;
  });
  const reading = readAnswerStream(response, (event) => {
    events.push(event);
    if (event.type === 'status') observedStatus();
  });

  await statusReceived;
  expect(events).toEqual([status]);
  upstream.enqueue(encoder.encode(line(result)));
  await reading;
  expect(events).toEqual([status, result]);
  expect(response.body?.locked).toBe(false);
});

it('decodes split JSON and multibyte text across arbitrary network chunks', async () => {
  const bytes = encoder.encode(`\n${line(status)}\r\n${line(result)}`);
  const response = responseFromChunks(
    Array.from(bytes, (byte) => Uint8Array.of(byte)),
  );
  const events: StreamEvent[] = [];

  await readAnswerStream(response, (event) => events.push(event));

  expect(events).toEqual([status, result]);
  expect(response.body?.locked).toBe(false);
});

it('accepts a complete terminal event without a trailing newline', async () => {
  const onEvent = vi.fn();
  await readAnswerStream(responseFromChunks([JSON.stringify(result)]), onEvent);

  expect(onEvent).toHaveBeenCalledExactlyOnceWith(result);
});

it('normalizes source sections omitted by the streamed API serializer', async () => {
  const onEvent = vi.fn();
  const sourceWithoutSection = {
    id: 'use-state',
    citation: 1,
    title: 'useState',
    source_type: 'reference',
    source_url: 'https://react.dev/reference/react/useState',
    excerpt: 'A source excerpt',
  };
  const streamedResult = {
    type: 'result',
    data: { ...answer, sources: [sourceWithoutSection] },
  };

  await readAnswerStream(
    responseFromChunks([`${JSON.stringify(streamedResult)}\n`]),
    onEvent,
  );

  expect(onEvent).toHaveBeenCalledExactlyOnceWith(result);
});

it('treats an error event as terminal and cancels unread upstream data', async () => {
  const cancel = vi.fn();
  const error: StreamEvent = {
    type: 'error',
    message: 'The provider timed out.',
  };
  const response = new Response(
    new ReadableStream({
      start(stream) {
        stream.enqueue(encoder.encode(`${line(error)}not valid JSON\n`));
      },
      cancel,
    }),
  );
  const onEvent = vi.fn();

  await readAnswerStream(response, onEvent);

  expect(onEvent).toHaveBeenCalledExactlyOnceWith(error);
  expect(cancel).toHaveBeenCalledOnce();
  expect(response.body?.locked).toBe(false);
});

it('stops at the first result even when another event follows in the same chunk', async () => {
  const onEvent = vi.fn();
  await readAnswerStream(
    responseFromChunks([`${line(result)}${line(status)}`]),
    onEvent,
  );

  expect(onEvent).toHaveBeenCalledExactlyOnceWith(result);
});

it.each(['', '\n\r\n', line(status), JSON.stringify(status), '{"type":"res'])(
  'rejects premature EOF with a retryable interruption message: %j',
  async (text) => {
    const response = responseFromChunks([text]);
    await expect(readAnswerStream(response, () => undefined)).rejects.toThrow(
      'The answer stream was interrupted before completion. Please try again.',
    );
    expect(response.body?.locked).toBe(false);
  },
);

it('reports an upstream read failure as an interrupted answer', async () => {
  const response = new Response(
    new ReadableStream({
      start(stream) {
        stream.error(new Error('Connection reset'));
      },
    }),
  );

  await expect(readAnswerStream(response, () => undefined)).rejects.toThrow(
    'The answer stream was interrupted before completion. Please try again.',
  );
  expect(response.body?.locked).toBe(false);
});

it.each([
  'not JSON',
  'null',
  '[]',
  '{"type":"unknown"}',
  '{"type":"status","message":"Searching"}',
  '{"type":"status","stage":"retrieving","message":3}',
  '{"type":"error","message":null}',
  '{"type":"result","data":null}',
  JSON.stringify({ type: 'result', data: { ...answer, kind: 'unknown' } }),
  JSON.stringify({ type: 'result', data: { ...answer, sources: [null] } }),
  JSON.stringify({
    type: 'result',
    data: { ...answer, sources: [{ ...answer.sources[0], citation: '1' }] },
  }),
  JSON.stringify({ type: 'result', data: { ...answer, suggestions: [3] } }),
])(
  'rejects malformed event data before passing it to the UI: %s',
  async (text) => {
    const response = responseFromChunks([`${text}\n`]);
    const onEvent = vi.fn();

    await expect(readAnswerStream(response, onEvent)).rejects.toThrow(
      'The API returned an invalid streamed response. Please try again.',
    );
    expect(onEvent).not.toHaveBeenCalled();
    expect(response.body?.locked).toBe(false);
  },
);

it('rejects an empty response body', async () => {
  await expect(
    readAnswerStream(new Response(null), () => undefined),
  ).rejects.toThrow('The API returned an empty response.');
});

it('cancels without delivering queued events when already aborted', async () => {
  const controller = new AbortController();
  controller.abort();
  const cancel = vi.fn();
  const response = new Response(
    new ReadableStream({
      start(stream) {
        stream.enqueue(encoder.encode(line(result)));
      },
      cancel,
    }),
  );
  const onEvent = vi.fn();

  await expect(
    readAnswerStream(response, onEvent, controller.signal),
  ).rejects.toMatchObject({ name: 'AbortError' });
  expect(onEvent).not.toHaveBeenCalled();
  expect(cancel).toHaveBeenCalledOnce();
  expect(response.body?.locked).toBe(false);
});

it('cancels a stalled read without waiting for upstream cancellation', async () => {
  const controller = new AbortController();
  const cancel = vi.fn(() => new Promise<void>(() => undefined));
  const response = new Response(new ReadableStream({ cancel }));
  const removeListener = vi.spyOn(controller.signal, 'removeEventListener');
  const reading = readAnswerStream(
    response,
    () => undefined,
    controller.signal,
  );

  controller.abort();

  await expect(reading).rejects.toMatchObject({ name: 'AbortError' });
  expect(cancel).toHaveBeenCalledOnce();
  expect(response.body?.locked).toBe(false);
  expect(removeListener).toHaveBeenCalledWith('abort', expect.any(Function));
});

it('does not deliver another buffered event when a status callback aborts', async () => {
  const controller = new AbortController();
  const onEvent = vi.fn(() => controller.abort());
  const response = responseFromChunks([`${line(status)}${line(result)}`]);

  await expect(
    readAnswerStream(response, onEvent, controller.signal),
  ).rejects.toMatchObject({ name: 'AbortError' });
  expect(onEvent).toHaveBeenCalledExactlyOnceWith(status);
});

it('removes the abort listener and releases the reader after success', async () => {
  const controller = new AbortController();
  const removeListener = vi.spyOn(controller.signal, 'removeEventListener');
  const response = responseFromChunks([line(result)]);

  await readAnswerStream(response, () => undefined, controller.signal);

  expect(removeListener).toHaveBeenCalledWith('abort', expect.any(Function));
  expect(response.body?.locked).toBe(false);
});

it('cleans up the reader when an event callback fails', async () => {
  const cancel = vi.fn(() => Promise.reject(new Error('Upstream cancelled')));
  const response = new Response(
    new ReadableStream({
      start(stream) {
        stream.enqueue(encoder.encode(line(status)));
      },
      cancel,
    }),
  );
  const error = new Error('Callback failed');

  await expect(
    readAnswerStream(response, () => {
      throw error;
    }),
  ).rejects.toBe(error);
  expect(cancel).toHaveBeenCalledOnce();
  expect(response.body?.locked).toBe(false);
});
