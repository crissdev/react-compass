import { afterEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  cacheLife: vi.fn(),
  cacheTag: vi.fn(),
}));

vi.mock('next/cache', () => mocks);

import { getCachedAnswer } from './answer-cache';

describe('getCachedAnswer', () => {
  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

  it('uses the guarded answer endpoint as its only upstream request', async () => {
    const answer = {
      kind: 'scope_notice' as const,
      message: 'React questions only.',
      sources: [],
    };
    const fetchMock = vi.fn().mockResolvedValue(Response.json(answer));
    vi.stubGlobal('fetch', fetchMock);

    await expect(getCachedAnswer('  What is the capital of France?  ')).resolves.toEqual(answer);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/ask',
      expect.objectContaining({
        body: JSON.stringify({ question: 'What is the capital of France?' }),
        cache: 'no-store',
        method: 'POST',
      }),
    );
    expect(mocks.cacheLife).toHaveBeenCalledWith({ stale: 0, revalidate: 0, expire: 1 });
  });
});
