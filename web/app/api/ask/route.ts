import {
  cacheAnswer,
  getCachedAnswer,
  invalidateCachedAnswer,
} from '@/lib/answer-cache';
import { readAnswerStream } from '@/lib/answer-stream';
import { normalizeQuestion } from '@/lib/questions';
import type { StreamEvent } from '@/lib/types';

const API_BASE_URL = process.env.API_BASE_URL ?? 'http://127.0.0.1:8000';
const API_REQUEST_TIMEOUT_MS = Number(
  process.env.API_REQUEST_TIMEOUT_MS ?? 130_000,
);

if (!Number.isFinite(API_REQUEST_TIMEOUT_MS) || API_REQUEST_TIMEOUT_MS <= 0) {
  throw new Error('API_REQUEST_TIMEOUT_MS must be a positive, finite number.');
}

function encodeEvent(event: StreamEvent): Uint8Array {
  return new TextEncoder().encode(`${JSON.stringify(event)}\n`);
}

async function readQuestion(request: Request): Promise<string | null> {
  try {
    const payload = (await request.json()) as { question?: unknown };
    if (typeof payload.question !== 'string') return null;
    const question = normalizeQuestion(payload.question);
    return question.length >= 2 && question.length <= 1_000 ? question : null;
  } catch {
    return null;
  }
}

export async function POST(request: Request) {
  const question = await readQuestion(request);
  if (!question) {
    return Response.json(
      { message: 'A question between 2 and 1,000 characters is required.' },
      { status: 400 },
    );
  }

  const upstream = new AbortController();
  let streamCancelled = false;

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      let timeout: ReturnType<typeof setTimeout> | undefined;
      const abortUpstream = () => upstream.abort(request.signal.reason);
      request.signal.addEventListener('abort', abortUpstream, { once: true });
      if (request.signal.aborted) abortUpstream();

      const send = (event: StreamEvent) => {
        if (!streamCancelled && !request.signal.aborted) {
          controller.enqueue(encodeEvent(event));
        }
      };

      try {
        if (upstream.signal.aborted) return;
        send({
          type: 'status',
          stage: 'cache',
          message: 'Checking saved React answers',
        });
        const cached = getCachedAnswer(question);
        if (cached) {
          send({ type: 'result', data: cached });
          return;
        }

        timeout = setTimeout(() => {
          upstream.abort(new DOMException('Search timed out', 'TimeoutError'));
        }, API_REQUEST_TIMEOUT_MS);

        const response = await fetch(`${API_BASE_URL}/ask/stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question }),
          cache: 'no-store',
          signal: upstream.signal,
        });
        if (!response.ok) {
          void response.body?.cancel().catch(() => undefined);
          throw new Error('The documentation API returned an error.');
        }

        await readAnswerStream(
          response,
          (event) => {
            if (upstream.signal.aborted) return;
            if (event.type === 'result') cacheAnswer(question, event.data);
            send(event);
          },
          upstream.signal,
        );
      } catch {
        send({
          type: 'error',
          message:
            upstream.signal.reason?.name === 'TimeoutError'
              ? 'The search took too long. Please try again.'
              : 'The search was interrupted before an answer was ready. Please try again.',
        });
      } finally {
        clearTimeout(timeout);
        request.signal.removeEventListener('abort', abortUpstream);
        if (!streamCancelled) controller.close();
      }
    },
    cancel() {
      streamCancelled = true;
      upstream.abort();
    },
  });

  return new Response(stream, {
    headers: {
      'Content-Type': 'application/x-ndjson; charset=utf-8',
      'Cache-Control': 'no-cache, no-transform',
      'X-Content-Type-Options': 'nosniff',
    },
  });
}

export async function DELETE(request: Request) {
  const question = await readQuestion(request);
  if (!question) {
    return Response.json(
      { message: 'A question between 2 and 1,000 characters is required.' },
      { status: 400 },
    );
  }

  invalidateCachedAnswer(question);
  return Response.json({ invalidated: true });
}
