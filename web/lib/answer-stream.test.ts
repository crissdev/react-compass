import { expect, it } from 'vitest';
import { decodeEventLines, readAnswerStream } from './answer-stream';

it('keeps an incomplete NDJSON line for the next network chunk', () => {
  const decoded = decodeEventLines(
    '{"type":"status","stage":"retrieving","message":"Searching"}\n{"type":"res',
  );

  expect(decoded.events).toHaveLength(1);
  expect(decoded.events[0].type).toBe('status');
  expect(decoded.remainder).toBe('{"type":"res');
});

it('cancels a reader that is waiting for the next streamed event', async () => {
  const encoder = new TextEncoder();
  const controller = new AbortController();
  const response = new Response(
    new ReadableStream({
      start(stream) {
        stream.enqueue(
          encoder.encode(
            '{"type":"status","stage":"retrieving","message":"Searching"}\n',
          ),
        );
      },
    }),
  );

  const reading = readAnswerStream(
    response,
    () => undefined,
    controller.signal,
  );
  await Promise.resolve();
  controller.abort();

  await expect(reading).rejects.toMatchObject({ name: 'AbortError' });
});
