const API_BASE_URL = process.env.API_BASE_URL ?? 'http://127.0.0.1:8000';

export async function POST(request: Request) {
  let payload: unknown;

  try {
    payload = await request.json();
  } catch {
    return Response.json({ message: 'Expected a JSON request body.' }, { status: 400 });
  }

  try {
    const response = await fetch(`${API_BASE_URL}/ask/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      cache: 'no-store',
      signal: request.signal,
    });

    if (!response.ok || !response.body) {
      const detail = await response.text();
      return Response.json(
        { message: detail || 'The documentation API returned an error.' },
        { status: response.status || 502 },
      );
    }

    const reader = response.body.getReader();
    const stream = new ReadableStream<Uint8Array>({
      async pull(controller) {
        try {
          const { done, value } = await reader.read();
          if (done) controller.close();
          else controller.enqueue(value);
        } catch (error) {
          controller.error(error);
        }
      },
      cancel(reason) {
        return reader.cancel(reason);
      },
    });

    return new Response(stream, {
      status: response.status,
      headers: {
        'Content-Type': 'application/x-ndjson; charset=utf-8',
        'Cache-Control': 'no-cache, no-transform',
        'X-Content-Type-Options': 'nosniff',
      },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      return new Response(null, { status: 499 });
    }
    return Response.json(
      { message: 'Could not reach the documentation API. Is it running on port 8000?' },
      { status: 502 },
    );
  }
}
