import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Answer, StreamEvent } from '@/lib/types';

const mocks = vi.hoisted(() => ({
  getCachedAnswer: vi.fn(),
  cacheAnswer: vi.fn(),
  invalidateCachedAnswer: vi.fn(),
  fetch: vi.fn<typeof fetch>(),
}));

vi.mock('@/lib/answer-cache', () => ({
  getCachedAnswer: mocks.getCachedAnswer,
  cacheAnswer: mocks.cacheAnswer,
  invalidateCachedAnswer: mocks.invalidateCachedAnswer,
}));

import { DELETE, POST } from './route';

const question = 'How does useState work?';
const answer: Answer = {
  kind: 'react_answer',
  message: 'A grounded answer',
  sources: [],
};
const cacheEvent: StreamEvent = {
  type: 'status',
  stage: 'cache',
  message: 'Checking saved React answers',
};

function request(value: unknown = question, signal?: AbortSignal) {
  return new Request('http://localhost/api/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question: value }),
    signal,
  });
}

function upstreamStream() {
  let controller: ReadableStreamDefaultController<Uint8Array>;
  const cancel = vi.fn();
  const stream = new ReadableStream<Uint8Array>({
    start(value) {
      controller = value;
    },
    cancel,
  });
  return {
    response: new Response(stream),
    cancel,
    event(event: StreamEvent) {
      controller.enqueue(
        new TextEncoder().encode(`${JSON.stringify(event)}\n`),
      );
    },
    close() {
      controller.close();
    },
    fail() {
      controller.error(new Error('Connection lost'));
    },
  };
}

async function readEvent(reader: ReadableStreamDefaultReader<Uint8Array>) {
  const { done, value } = await reader.read();
  expect(done).toBe(false);
  return JSON.parse(new TextDecoder().decode(value)) as StreamEvent;
}

async function readEvents(response: Response): Promise<StreamEvent[]> {
  return (await response.text())
    .split('\n')
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

function fetchedSignal(index = 0): AbortSignal {
  return mocks.fetch.mock.calls[index][1]?.signal as AbortSignal;
}

function fetchUntilAborted() {
  mocks.fetch.mockImplementation(
    (_url, options) =>
      new Promise((_resolve, reject) => {
        options?.signal?.addEventListener(
          'abort',
          () => reject(options.signal?.reason),
          { once: true },
        );
      }),
  );
}

describe('/api/ask', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.stubGlobal('fetch', mocks.fetch);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('returns a cached answer without upstream work', async () => {
    mocks.getCachedAnswer.mockReturnValue(answer);

    const response = await POST(request(`  ${question}  `));

    expect(await readEvents(response)).toEqual([
      cacheEvent,
      { type: 'result', data: answer },
    ]);
    expect(mocks.getCachedAnswer).toHaveBeenCalledWith(question);
    expect(mocks.fetch).not.toHaveBeenCalled();
    expect(mocks.cacheAnswer).not.toHaveBeenCalled();
  });

  it('forwards each real stage before the result is available', async () => {
    const upstream = upstreamStream();
    mocks.fetch.mockResolvedValue(upstream.response);
    const response = await POST(request(`  ${question}  `));
    const reader = response.body!.getReader();

    expect(response.headers.get('Content-Type')).toContain(
      'application/x-ndjson',
    );
    expect(response.headers.get('Cache-Control')).toContain('no-transform');
    expect(await readEvent(reader)).toEqual(cacheEvent);
    for (const stage of ['classifying', 'retrieving', 'generating']) {
      const event: StreamEvent = { type: 'status', stage, message: stage };
      upstream.event(event);
      expect(await readEvent(reader)).toEqual(event);
      expect(mocks.cacheAnswer).not.toHaveBeenCalled();
    }

    upstream.event({ type: 'result', data: answer });
    expect(await readEvent(reader)).toEqual({ type: 'result', data: answer });
    expect((await reader.read()).done).toBe(true);
    expect(mocks.fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/ask\/stream$/),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ question }),
        cache: 'no-store',
        signal: expect.any(AbortSignal),
      }),
    );
    expect(mocks.cacheAnswer).toHaveBeenCalledExactlyOnceWith(question, answer);
  });

  it.each(['close', 'fail'] as const)(
    'reports interruption when the upstream %s happens before a result',
    async (termination) => {
      const upstream = upstreamStream();
      mocks.fetch.mockResolvedValue(upstream.response);
      const response = await POST(request());
      const reader = response.body!.getReader();
      expect(await readEvent(reader)).toEqual(cacheEvent);
      upstream.event({
        type: 'status',
        stage: 'generating',
        message: 'Writing an answer',
      });
      expect(await readEvent(reader)).toMatchObject({ stage: 'generating' });

      upstream[termination]();

      expect(await readEvent(reader)).toEqual({
        type: 'error',
        message:
          'The search was interrupted before an answer was ready. Please try again.',
      });
      expect((await reader.read()).done).toBe(true);
      expect(mocks.cacheAnswer).not.toHaveBeenCalled();
    },
  );

  it('forwards a terminal API error without caching it', async () => {
    const upstream = upstreamStream();
    mocks.fetch.mockResolvedValue(upstream.response);
    const response = await POST(request());
    const error: StreamEvent = {
      type: 'error',
      message: 'The search took too long. Please try again.',
    };
    upstream.event(error);

    expect(await readEvents(response)).toEqual([cacheEvent, error]);
    expect(mocks.cacheAnswer).not.toHaveBeenCalled();
    expect(upstream.cancel).toHaveBeenCalledOnce();
  });

  it('releases unsuccessful upstream responses and reports an error', async () => {
    const upstream = upstreamStream();
    mocks.fetch.mockResolvedValue(
      new Response(upstream.response.body, { status: 503 }),
    );

    const events = await readEvents(await POST(request()));

    expect(events).toHaveLength(2);
    expect(events[1]).toMatchObject({ type: 'error' });
    expect(upstream.cancel).toHaveBeenCalledOnce();
    expect(mocks.cacheAnswer).not.toHaveBeenCalled();
  });

  it('cancels an upstream fetch when the response consumer cancels', async () => {
    fetchUntilAborted();
    const response = await POST(request());
    const reader = response.body!.getReader();
    expect(await readEvent(reader)).toEqual(cacheEvent);

    await reader.cancel();

    expect(fetchedSignal().aborted).toBe(true);
    expect(mocks.cacheAnswer).not.toHaveBeenCalled();
  });

  it('cancels an active upstream body when the request disconnects', async () => {
    const upstream = upstreamStream();
    mocks.fetch.mockResolvedValue(upstream.response);
    const connection = new AbortController();
    const response = await POST(request(question, connection.signal));
    const reader = response.body!.getReader();
    expect(await readEvent(reader)).toEqual(cacheEvent);
    upstream.event({
      type: 'status',
      stage: 'generating',
      message: 'Writing an answer',
    });
    expect(await readEvent(reader)).toMatchObject({ stage: 'generating' });

    connection.abort();

    expect((await reader.read()).done).toBe(true);
    expect(fetchedSignal().aborted).toBe(true);
    expect(upstream.cancel).toHaveBeenCalledOnce();
    expect(mocks.cacheAnswer).not.toHaveBeenCalled();
  });

  it('does no upstream work for an already-disconnected request', async () => {
    const connection = new AbortController();
    connection.abort();

    const response = await POST(request(question, connection.signal));

    expect(await response.text()).toBe('');
    expect(mocks.fetch).not.toHaveBeenCalled();
    expect(mocks.cacheAnswer).not.toHaveBeenCalled();
  });

  it.each(['headers', 'body'] as const)(
    'aborts a stalled upstream %s after the deadline',
    async (phase) => {
      vi.useFakeTimers();
      const upstream = upstreamStream();
      if (phase === 'headers') fetchUntilAborted();
      else mocks.fetch.mockResolvedValue(upstream.response);
      const response = await POST(request());
      const completion = readEvents(response);

      await vi.advanceTimersByTimeAsync(129_999);
      expect(fetchedSignal().aborted).toBe(false);
      await vi.advanceTimersByTimeAsync(1);

      expect(await completion).toEqual([
        cacheEvent,
        {
          type: 'error',
          message: 'The search took too long. Please try again.',
        },
      ]);
      expect(fetchedSignal().aborted).toBe(true);
      expect(fetchedSignal().reason.name).toBe('TimeoutError');
      expect(mocks.cacheAnswer).not.toHaveBeenCalled();
      expect(vi.getTimerCount()).toBe(0);
      if (phase === 'body') expect(upstream.cancel).toHaveBeenCalledOnce();
    },
  );

  it('clears the deadline after a completed answer', async () => {
    vi.useFakeTimers();
    const upstream = upstreamStream();
    mocks.fetch.mockResolvedValue(upstream.response);
    const response = await POST(request());
    upstream.event({ type: 'result', data: answer });
    await readEvents(response);

    await vi.advanceTimersByTimeAsync(130_000);

    expect(fetchedSignal().aborted).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('keeps matching concurrent requests independent when one is cancelled', async () => {
    const first = upstreamStream();
    const second = upstreamStream();
    mocks.fetch
      .mockResolvedValueOnce(first.response)
      .mockResolvedValueOnce(second.response);
    const firstResponse = await POST(request());
    const secondResponse = await POST(request());
    const firstReader = firstResponse.body!.getReader();
    const secondReader = secondResponse.body!.getReader();
    expect(await readEvent(firstReader)).toEqual(cacheEvent);
    expect(await readEvent(secondReader)).toEqual(cacheEvent);

    await firstReader.cancel();
    expect(fetchedSignal(0).aborted).toBe(true);
    expect(fetchedSignal(1).aborted).toBe(false);
    second.event({ type: 'result', data: answer });

    expect(await readEvent(secondReader)).toEqual({
      type: 'result',
      data: answer,
    });
    expect((await secondReader.read()).done).toBe(true);
    expect(mocks.cacheAnswer).toHaveBeenCalledExactlyOnceWith(question, answer);
  });

  it.each(['', 'a', 'a'.repeat(1_001), null, 123])(
    'rejects invalid questions without starting work: %j',
    async (value) => {
      const response = await POST(request(value));

      expect(response.status).toBe(400);
      expect(mocks.getCachedAnswer).not.toHaveBeenCalled();
      expect(mocks.fetch).not.toHaveBeenCalled();
    },
  );

  it('accepts the maximum question length', async () => {
    mocks.getCachedAnswer.mockReturnValue(answer);

    const response = await POST(request('a'.repeat(1_000)));

    expect(response.status).toBe(200);
    expect((await readEvents(response)).at(-1)).toEqual({
      type: 'result',
      data: answer,
    });
  });

  it('invalidates the normalized question on DELETE', async () => {
    const response = await DELETE(request(`  ${question}  `));

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ invalidated: true });
    expect(mocks.invalidateCachedAnswer).toHaveBeenCalledExactlyOnceWith(
      question,
    );
    expect(mocks.fetch).not.toHaveBeenCalled();
  });

  it('rejects invalid DELETE requests without changing the cache', async () => {
    const response = await DELETE(request('a'.repeat(1_001)));

    expect(response.status).toBe(400);
    expect(mocks.invalidateCachedAnswer).not.toHaveBeenCalled();
  });
});
