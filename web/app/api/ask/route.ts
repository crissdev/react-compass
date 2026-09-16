import { revalidateTag } from 'next/cache';
import { answerCacheTag, getCachedAnswer } from '@/lib/answer-cache';
import { normalizeQuestion } from '@/lib/questions';
import type { StreamEvent } from '@/lib/types';

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

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      if (!cancelled) {
        controller.enqueue(
          encodeEvent({
            type: 'status',
            stage: 'cache',
            message: 'Checking saved answers and React docs',
          }),
        );
      }

      try {
        const answer = await getCachedAnswer(question);
        if (!cancelled) controller.enqueue(encodeEvent({ type: 'result', data: answer }));
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
        request.signal.removeEventListener('abort', markCancelled);
        if (!cancelled) controller.close();
      }
    },
    cancel() {
      cancelled = true;
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
