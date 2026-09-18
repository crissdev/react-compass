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

  it('retains grounded answers with the weekly cache profile', async () => {
    const answer = {
      kind: 'react_answer' as const,
      message: 'State lets a component remember information.',
      sources: [],
    };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(answer)));

    await expect(getCachedAnswer('How does useState work?')).resolves.toEqual(answer);

    expect(mocks.cacheLife).toHaveBeenCalledWith('weeks');
    expect(mocks.cacheTag).toHaveBeenCalledTimes(1);
  });

  it('does not retain no-match suggestions', async () => {
    const answer = {
      kind: 'no_match' as const,
      message: 'No direct answer found.',
      sources: [],
      suggestions: ['How should I structure state in React?'],
    };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(answer)));

    await expect(getCachedAnswer('What are stateless components?')).resolves.toEqual(answer);

    expect(mocks.cacheLife).toHaveBeenCalledWith({ stale: 0, revalidate: 0, expire: 1 });
  });
});
