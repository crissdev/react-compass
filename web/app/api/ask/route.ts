import { revalidateTag } from 'next/cache';
import { answerCacheTag, getCachedAnswer } from '@/lib/answer-cache';
import { normalizeQuestion } from '@/lib/questions';
import type { StreamEvent } from '@/lib/types';

const CACHE_STATUS_DELAY_MS = 500;

function encodeEvent(event: StreamEvent): Uint8Array {
  return new TextEncoder().encode(`${JSON.stringify(event)}\n`);
}

async function readQuestion(request: Request): Promise<string | null> {
  try {
    const payload = (await request.json()) as { question?: unknown };
    if (typeof payload.question !== 'string') return null;
    const question = normalizeQuestion(payload.question);
    return question.length >= 2 ? question : null;
  } catch {
    return null;
  }
}

export async function POST(request: Request) {
  const question = await readQuestion(request);
  if (!question) {
    return Response.json(
      { message: 'A question with at least two characters is required.' },
      { status: 400 },
    );
  }

  let cancelled = request.signal.aborted;
  const markCancelled = () => {
    cancelled = true;
  };
  request.signal.addEventListener('abort', markCancelled, { once: true });
  let pendingStatusTimer: ReturnType<typeof setTimeout> | null = null;

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      if (!cancelled) {
        controller.enqueue(
          encodeEvent({
            type: 'status',
            stage: 'cache',
            message: 'Checking saved React answers',
          }),
        );
      }

      try {
        pendingStatusTimer = setTimeout(() => {
          if (!cancelled) {
            controller.enqueue(
              encodeEvent({
                type: 'status',
                stage: 'answering',
                message: 'Checking question scope and preparing an answer',
              }),
            );
          }
        }, CACHE_STATUS_DELAY_MS);

        const answer = await getCachedAnswer(question);
        if (pendingStatusTimer) clearTimeout(pendingStatusTimer);
        if (answer.kind !== 'react_answer') {
          revalidateTag(answerCacheTag(question), { expire: 0 });
        }
        if (!cancelled)
          controller.enqueue(encodeEvent({ type: 'result', data: answer }));
      } catch {
        if (!cancelled) {
          controller.enqueue(
            encodeEvent({
              type: 'error',
              message:
                'The search could not be completed. Check the API configuration and try again.',
            }),
          );
        }
      } finally {
        if (pendingStatusTimer) clearTimeout(pendingStatusTimer);
        request.signal.removeEventListener('abort', markCancelled);
        if (!cancelled) controller.close();
      }
    },
    cancel() {
      cancelled = true;
      if (pendingStatusTimer) clearTimeout(pendingStatusTimer);
      request.signal.removeEventListener('abort', markCancelled);
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
      { message: 'A question with at least two characters is required.' },
      { status: 400 },
    );
  }

  revalidateTag(answerCacheTag(question), { expire: 0 });
  return Response.json({ invalidated: true });
}
